"""Pre-POST validation engine for Tableau Next visualization JSON.

Runs 17 checks to catch errors locally before hitting the API.
Adapted from alaviron/tableau-skills validation engine.
"""

from typing import Any, Dict, List, Tuple

VALID_MARK_TYPES = {"Bar", "Line", "Donut", "Circle", "Text", "Square"}

REQUIRED_FONT_KEYS = {
    "actionableHeaders",
    "axisTickLabels",
    "fieldLabels",
    "headers",
    "legendLabels",
    "markLabels",
    "marks",
}

REQUIRED_LINE_KEYS = {"axisLine", "fieldLabelDividerLine", "separatorLine", "zeroLine"}


class ValidationResult:
    __slots__ = ("ok", "rule", "message", "fix")

    def __init__(self, ok: bool, rule: str, message: str = "", fix: str = ""):
        self.ok = ok
        self.rule = rule
        self.message = message
        self.fix = fix

    def __repr__(self) -> str:
        status = "PASS" if self.ok else "FAIL"
        return f"[{status}] {self.rule}: {self.message}"


def validate(payload: dict) -> List[ValidationResult]:
    results = []
    results.extend(_check_root_fields(payload))
    results.extend(_check_view(payload))
    results.extend(_check_visual_spec_fields(payload))
    results.extend(_check_marks_structure(payload))
    results.extend(_check_style(payload))
    results.extend(_check_encoding_fields(payload))
    results.extend(_check_size_encoding(payload))
    return results


def is_valid(payload: dict) -> Tuple[bool, List[ValidationResult]]:
    results = validate(payload)
    ok = all(r.ok for r in results)
    return ok, results


def print_results(results: List[ValidationResult]) -> None:
    for r in results:
        if not r.ok:
            print(f"  FAIL [{r.rule}]: {r.message}")
            if r.fix:
                print(f"       Fix: {r.fix}")


def _check_root_fields(p: dict) -> List[ValidationResult]:
    required = ["name", "label", "dataSource", "workspace", "fields", "visualSpecification", "interactions", "view"]
    missing = [k for k in required if k not in p]
    if missing:
        return [ValidationResult(False, "root_fields",
            f"Missing required root field(s): {', '.join(missing)}",
            "Add the missing keys to the top level of the payload.")]
    return [ValidationResult(True, "root_fields", "All required root fields present.")]


def _check_view(p: dict) -> List[ValidationResult]:
    view = p.get("view")
    if not isinstance(view, dict):
        return [ValidationResult(False, "view", "Missing or invalid 'view' object.")]
    missing = []
    for k in ("label", "name", "viewSpecification"):
        if k not in view:
            missing.append(k)
    vs = view.get("viewSpecification")
    if not isinstance(vs, dict):
        return [ValidationResult(False, "view", "viewSpecification is missing or not an object.")]
    if "sortOrders" not in vs:
        missing.append("viewSpecification.sortOrders")
    if "filters" in vs:
        return [ValidationResult(False, "view",
            "viewSpecification must not use legacy top-level 'filters' (rejected at API v66.12).",
            "Use viewSpecification.filter with nested filters array instead.")]
    if missing:
        return [ValidationResult(False, "view", f"view missing: {', '.join(missing)}")]
    return [ValidationResult(True, "view", "view structure is valid.")]


def _check_visual_spec_fields(p: dict) -> List[ValidationResult]:
    vs = p.get("visualSpecification", {})
    if not isinstance(vs, dict):
        return [ValidationResult(False, "vis_spec", "visualSpecification is missing or not an object.")]
    layout = vs.get("layout", "Vizql")
    if layout == "Table":
        required = ["marks", "style", "rows", "layout"]
    elif layout == "Map":
        required = ["marks", "style", "layout", "locations"]
    elif layout == "Flow":
        required = ["marks", "style", "layout", "levels", "link"]
    else:
        required = ["marks", "style", "measureValues", "referenceLines", "forecasts", "layout"]
    missing = [k for k in required if k not in vs]
    if missing:
        return [ValidationResult(False, "vis_spec",
            f"visualSpecification missing: {', '.join(missing)}",
            "Add the missing keys (even empty objects/arrays) to visualSpecification.")]
    return [ValidationResult(True, "vis_spec", "visualSpecification has all required keys.")]


def _check_marks_structure(p: dict) -> List[ValidationResult]:
    results = []
    layout = p.get("visualSpecification", {}).get("layout", "Vizql")
    marks = p.get("visualSpecification", {}).get("marks", {})

    if "ALL" in marks:
        results.append(ValidationResult(False, "marks_no_ALL",
            "marks.ALL found — this is the old v65.11 format.",
            "Replace marks.ALL with marks.panes + marks.headers."))
    else:
        results.append(ValidationResult(True, "marks_no_ALL", "No legacy marks.ALL key."))

    if layout in ("Flow", "Map"):
        has_panes = "panes" in marks
        if not has_panes:
            results.append(ValidationResult(False, "marks_panes", f"{layout} layout requires marks.panes."))
        else:
            results.append(ValidationResult(True, "marks_panes", "marks.panes present."))
        return results

    has_panes = "panes" in marks
    has_headers = "headers" in marks
    if not has_panes or not has_headers:
        missing = []
        if not has_panes:
            missing.append("panes")
        if not has_headers:
            missing.append("headers")
        results.append(ValidationResult(False, "marks_panes_headers",
            f"marks missing: {', '.join(missing)}",
            "marks must have both panes and headers."))
    else:
        results.append(ValidationResult(True, "marks_panes_headers", "marks.panes and marks.headers present."))

    panes = marks.get("panes", {})
    mark_type = panes.get("type")
    if mark_type and mark_type not in VALID_MARK_TYPES:
        results.append(ValidationResult(False, "mark_type",
            f"marks.panes.type '{mark_type}' is not valid. Must be one of: {', '.join(sorted(VALID_MARK_TYPES))}"))
    elif mark_type:
        results.append(ValidationResult(True, "mark_type", f"marks.panes.type '{mark_type}' is valid."))

    if has_panes and "stack" not in panes:
        results.append(ValidationResult(False, "marks_stack",
            "marks.panes.stack is missing.",
            'Add "stack": {"isAutomatic": true, "isStacked": false}.'))
    elif has_panes:
        results.append(ValidationResult(True, "marks_stack", "marks.panes.stack present."))

    headers = marks.get("headers", {})
    if has_headers and isinstance(headers, dict) and "stack" not in headers:
        results.append(ValidationResult(False, "marks_headers_stack",
            "marks.headers.stack is missing (required at API v66.12).",
            'Add "stack": {"isAutomatic": true, "isStacked": false} alongside type and encodings.'))
    elif has_headers and isinstance(headers, dict):
        results.append(ValidationResult(True, "marks_headers_stack", "marks.headers.stack present."))

    return results


def _check_style(p: dict) -> List[ValidationResult]:
    results = []
    style = p.get("visualSpecification", {}).get("style", {})
    layout = p.get("visualSpecification", {}).get("layout", "Vizql")

    marks_style = style.get("marks", {})
    panes_style = marks_style.get("panes", {})
    if "range" not in panes_style:
        results.append(ValidationResult(False, "style_range",
            "style.marks.panes.range is missing.",
            'Add "range": {"reverse": false}.'))
    else:
        results.append(ValidationResult(True, "style_range", "style.marks.panes.range present."))

    if layout in ("Vizql", "Table"):
        hdr_style = marks_style.get("headers", {})
        if not isinstance(hdr_style, dict) or "range" not in hdr_style:
            results.append(ValidationResult(False, "style_marks_headers_range",
                "style.marks.headers.range is missing (required at v66.12)."))
        else:
            results.append(ValidationResult(True, "style_marks_headers_range", "style.marks.headers.range present."))

    if layout == "Table":
        forbidden = {"axis", "referenceLines", "showDataPlaceholder"}
        present = forbidden & set(style.keys())
        if present:
            results.append(ValidationResult(False, "style_table_forbidden",
                f"Table style has forbidden key(s): {', '.join(sorted(present))}"))
        else:
            results.append(ValidationResult(True, "style_table_forbidden", "Table style has no forbidden keys."))
    elif layout not in ("Map", "Flow"):
        if "axis" not in style:
            results.append(ValidationResult(False, "style_axis",
                "style.axis is missing.",
                'Add "axis": {"fields": {}}.'))
        else:
            results.append(ValidationResult(True, "style_axis", "style.axis present."))

    fonts = style.get("fonts", {})
    missing_fonts = REQUIRED_FONT_KEYS - set(fonts.keys())
    if missing_fonts:
        results.append(ValidationResult(False, "style_fonts",
            f"style.fonts missing key(s): {', '.join(sorted(missing_fonts))}",
            "All 7 font keys are required."))
    else:
        results.append(ValidationResult(True, "style_fonts", "style.fonts has all required keys."))

    lines = style.get("lines", {})
    missing_lines = REQUIRED_LINE_KEYS - set(lines.keys())
    if missing_lines:
        results.append(ValidationResult(False, "style_lines",
            f"style.lines missing key(s): {', '.join(sorted(missing_lines))}",
            "All 4 line keys are required."))
    else:
        results.append(ValidationResult(True, "style_lines", "style.lines has all required keys."))

    return results


def _check_encoding_fields(p: dict) -> List[ValidationResult]:
    results = []
    fields = p.get("fields", {})
    vs = p.get("visualSpecification", {})
    style = vs.get("style", {})
    columns = vs.get("columns", [])
    rows = vs.get("rows", [])

    marks = vs.get("marks", {})
    panes = marks.get("panes", {})
    encodings = panes.get("encodings", [])
    encoding_keys = {e.get("fieldKey") for e in encodings if isinstance(e, dict) and e.get("fieldKey")}

    enc_style_fields = style.get("encodings", {}).get("fields", {})
    hdr_style_fields = style.get("headers", {}).get("fields", {})
    shelf_keys = set(columns) | set(rows)

    missing_enc = []
    for fk in encoding_keys:
        fdef = fields.get(fk, {})
        if fdef.get("role") == "Measure" and fk not in enc_style_fields:
            missing_enc.append(fk)
    if missing_enc:
        results.append(ValidationResult(False, "enc_measure_style",
            f"Measure field(s) in encodings missing from style.encodings.fields: {', '.join(missing_enc)}",
            'Add {"defaults": {"format": {}}} for each.'))
    else:
        results.append(ValidationResult(True, "enc_measure_style", "All encoded measures have style entries."))

    bad_dims = []
    for fk in enc_style_fields:
        fdef = fields.get(fk, {})
        if fdef.get("role") == "Dimension" and fdef.get("type", "Field") == "Field":
            enc_entry = enc_style_fields.get(fk, {})
            if "colors" not in enc_entry:
                bad_dims.append(fk)
    if bad_dims:
        results.append(ValidationResult(False, "enc_no_dims",
            f"Dimension field(s) in style.encodings.fields without color config: {', '.join(bad_dims)}",
            "Remove dimensions from style.encodings.fields unless they have color palette config."))
    else:
        results.append(ValidationResult(True, "enc_no_dims", "style.encodings.fields contains no invalid dimensions."))

    bad_hdrs = []
    for fk in hdr_style_fields:
        if fk not in shelf_keys:
            bad_hdrs.append(fk)
    if bad_hdrs:
        results.append(ValidationResult(False, "hdr_only_shelf_dims",
            f"style.headers.fields contains key(s) not on rows/columns: {', '.join(bad_hdrs)}",
            "Only dimensions on rows or columns belong in style.headers.fields."))
    else:
        results.append(ValidationResult(True, "hdr_only_shelf_dims", "style.headers.fields only has shelf dimensions."))

    shelf_and_encoding = shelf_keys & encoding_keys
    if shelf_and_encoding:
        results.append(ValidationResult(False, "shelf_and_encoding",
            f"Field(s) cannot be both on shelves AND in encodings: {', '.join(shelf_and_encoding)}",
            "Create duplicate field definitions — one on the shelf, one for encoding."))
    else:
        results.append(ValidationResult(True, "shelf_and_encoding", "No fields are both on shelves and in encodings."))

    mark_type = panes.get("type")
    if mark_type == "Donut":
        enc_types = {e.get("type"): e.get("fieldKey") for e in encodings if isinstance(e, dict) and "fieldKey" in e}
        has_color_dim = False
        has_angle_measure = False
        for enc_type, fk in enc_types.items():
            if enc_type == "Color" and fk in fields and fields[fk].get("role") == "Dimension":
                has_color_dim = True
            elif enc_type == "Angle" and fk in fields and fields[fk].get("role") == "Measure":
                has_angle_measure = True
        if not has_color_dim:
            results.append(ValidationResult(False, "donut_color_required",
                "Donut charts require a Color encoding with a dimension field."))
        if not has_angle_measure:
            results.append(ValidationResult(False, "donut_angle_required",
                "Donut charts require an Angle encoding with a measure field."))
        if has_color_dim and has_angle_measure:
            results.append(ValidationResult(True, "donut_encodings", "Donut has required Color+Angle encodings."))

    return results


def _check_size_encoding(p: dict) -> List[ValidationResult]:
    results = []
    vs = p.get("visualSpecification", {})
    marks = vs.get("marks", {})
    panes = marks.get("panes", {})
    encodings = panes.get("encodings", [])
    mark_type = panes.get("type")

    has_size = any(e.get("type") == "Size" for e in encodings if isinstance(e, dict))
    if has_size and mark_type in ("Line", "Donut"):
        results.append(ValidationResult(False, "size_encoding",
            f"Size encoding is not supported for {mark_type} charts.",
            "Remove Size encoding or use a different chart type."))
    return results
