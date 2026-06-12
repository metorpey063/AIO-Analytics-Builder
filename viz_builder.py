"""Visualization payload builder for Tableau Next.

Produces complete, validated JSON payloads from template definitions
and SDM field maps. Integrates with style_defaults and viz_validator.
"""

import copy
from typing import Any, Dict, List, Optional, Tuple

from style_defaults import (
    build_fonts, build_lines, build_shading, build_field_labels,
    resolve_fit, axis_field_entry, encoding_field_entry, header_field_entry,
    marks_headers_style, marks_panes_style, DEFAULT_PALETTE, num_fmt,
)
from viz_templates import TEMPLATES
from viz_validator import is_valid, print_results


VIZQL_MARK_HEADERS = {
    "encodings": [],
    "isAutomatic": True,
    "stack": {"isAutomatic": True, "isStacked": False},
    "type": "Text",
}

CHART_CONFIGS = {
    "line":    {"fit": "Entire",   "size_type": "Pixel",      "size_val": 3,   "reverse": False, "banding": False, "auto_size": False},
    "bar":     {"fit": "Entire",   "size_type": "Percentage", "size_val": 75,  "reverse": True,  "banding": True,  "auto_size": True},
    "donut":   {"fit": "Entire",   "size_type": "Percentage", "size_val": 80,  "reverse": True,  "banding": True,  "auto_size": True},
    "scatter": {"fit": "Standard", "size_type": "Pixel",      "size_val": 10,  "reverse": False, "banding": False, "auto_size": False},
    "heatmap": {"fit": "Entire",   "size_type": "Percentage", "size_val": 100, "reverse": True,  "banding": True,  "auto_size": True},
    "funnel":  {"fit": "Entire",   "size_type": "Percentage", "size_val": 75,  "reverse": True,  "banding": True,  "auto_size": True},
}


def _infer_format(field_name: str, agg: str = "") -> Tuple[str, int, str]:
    """Infer format type, decimal places, and suffix from field name."""
    fl = field_name.lower()
    if any(kw in fl for kw in ("rate", "percent", "ratio", "enrollment", "utilization", "retention", "optin")):
        return "Number", 1, "%"
    if any(kw in fl for kw in ("score", "satisfaction", "index")):
        return "Number", 2, ""
    if any(kw in fl for kw in ("revenue", "cost", "amount", "price", "salary")):
        return "Currency", 0, ""
    if any(kw in fl for kw in ("count", "volume", "quantity", "headcount")):
        return "Number", 0, ""
    return "Number", 2, ""


def build_viz_payload(
    *,
    template_name: str,
    viz_name: str,
    viz_label: str,
    sdm_api: str,
    ws_api: str,
    do_api: str,
    field_map: Dict[str, str],
    dim_field_map: Dict[str, str],
    measurements: Dict[str, str],
    style_overrides: Dict[str, Any] = None,
    palette: List[str] = None,
    validate: bool = True,
) -> Dict[str, Any]:
    """Build a complete visualization payload from a template.

    Args:
        template_name: Key in TEMPLATES (e.g. "trend_over_time")
        viz_name: API name for the visualization
        viz_label: Display label
        sdm_api: Semantic Data Model apiName
        ws_api: Workspace apiName
        do_api: Data Object apiName
        field_map: Maps template slot names to raw field names
                   e.g. {"measure": "benefits_enrollment_rate", "date": "date"}
        dim_field_map: Maps base field names to dimension apiNames
        measurements: Maps base field names to measurement apiNames
        style_overrides: Brand color overrides
        palette: Custom color palette
        validate: Whether to run pre-POST validation

    Returns:
        Complete viz payload dict ready for POST
    """
    template = TEMPLATES.get(template_name)
    if not template:
        raise ValueError(f"Unknown template: {template_name}. Available: {list(TEMPLATES.keys())}")

    style_overrides = style_overrides or {}
    palette = palette or DEFAULT_PALETTE
    chart_type = template["chart_type"]
    cfg = CHART_CONFIGS[chart_type]

    fields = {}
    columns = []
    rows = []
    encodings = []
    legends = {}
    axis_fields = {}
    enc_fields = {}
    hdr_fields = {}
    sort_orders = {"columns": [], "fields": {}, "rows": []}

    field_counter = 1

    def _add_field(role, display_cat, field_name, function=None) -> str:
        nonlocal field_counter
        fkey = f"F{field_counter}"
        field_counter += 1

        if role == "Measure":
            fapi = measurements.get(field_name, f"{field_name}__c")
            fn = function or "Avg" if any(kw in field_name.lower() for kw in ("rate", "percent", "score", "ratio")) else function or "Sum"
        else:
            fapi = dim_field_map.get(field_name, f"{field_name}1")
            fn = function

        entry = {
            "type": "Field",
            "displayCategory": display_cat,
            "role": role,
            "objectName": do_api,
            "fieldName": fapi,
        }
        if fn:
            entry["function"] = fn
        fields[fkey] = entry
        return fkey

    def _add_date_hierarchy(base_field_name: str) -> Tuple[str, str]:
        fapi = dim_field_map.get(base_field_name, "date1")
        nonlocal field_counter

        year_key = f"F{field_counter}"
        field_counter += 1
        fields[year_key] = {
            "type": "Field",
            "displayCategory": "Discrete",
            "role": "Dimension",
            "objectName": do_api,
            "fieldName": fapi,
            "function": "DatePartYear",
        }

        month_key = f"F{field_counter}"
        field_counter += 1
        fields[month_key] = {
            "type": "Field",
            "displayCategory": "Discrete",
            "role": "Dimension",
            "objectName": do_api,
            "fieldName": fapi,
            "function": "DatePartMonth",
        }
        return year_key, month_key

    # Build fields based on template type
    if template_name in ("trend_over_time", "multi_series_line"):
        date_field = field_map.get("date", "date")
        measure_field = field_map.get("measure", list(field_map.values())[0])

        year_key, month_key = _add_date_hierarchy(date_field)
        columns.extend([year_key, month_key])
        hdr_fields[year_key] = header_field_entry()
        hdr_fields[month_key] = header_field_entry()

        fmt_type, decimals, suffix = _infer_format(measure_field)
        meas_key = _add_field("Measure", "Continuous", measure_field)
        rows.append(meas_key)
        axis_fields[meas_key] = axis_field_entry(fmt_type, decimals, suffix)
        enc_fields[meas_key] = encoding_field_entry(fmt_type, decimals, suffix)

        color_field = field_map.get("color_dim")
        if color_field or template_name == "multi_series_line":
            color_field = color_field or field_map.get("color_dim", "")
            if color_field:
                color_key = _add_field("Dimension", "Discrete", color_field)
                columns.append(color_key)
                hdr_fields[color_key] = header_field_entry()
                enc_color_key = _add_field("Dimension", "Discrete", color_field)
                encodings.append({"fieldKey": enc_color_key, "type": "Color"})
                enc_fields[enc_color_key] = {
                    "defaults": {"format": {}},
                    "colors": {
                        "customColors": [],
                        "palette": {"colors": palette, "type": "Custom"},
                        "type": "Discrete",
                    }
                }
                legends[enc_color_key] = {"isVisible": True, "position": "Right", "title": {"isVisible": True}}

    elif template_name in ("bar_by_category", "stacked_bar", "horizontal_bar"):
        cat_field = field_map.get("category", list(field_map.values())[0])
        meas_field = field_map.get("amount", field_map.get("measure", list(field_map.values())[-1]))

        if template.get("horizontal"):
            cat_key = _add_field("Dimension", "Discrete", cat_field)
            rows.append(cat_key)
            hdr_fields[cat_key] = header_field_entry()

            fmt_type, decimals, suffix = _infer_format(meas_field)
            meas_key = _add_field("Measure", "Continuous", meas_field)
            columns.append(meas_key)
            axis_fields[meas_key] = axis_field_entry(fmt_type, decimals, suffix)
            enc_fields[meas_key] = encoding_field_entry(fmt_type, decimals, suffix)
        else:
            cat_key = _add_field("Dimension", "Discrete", cat_field)
            columns.append(cat_key)
            hdr_fields[cat_key] = header_field_entry()

            fmt_type, decimals, suffix = _infer_format(meas_field)
            meas_key = _add_field("Measure", "Continuous", meas_field)
            rows.append(meas_key)
            axis_fields[meas_key] = axis_field_entry(fmt_type, decimals, suffix)
            enc_fields[meas_key] = encoding_field_entry(fmt_type, decimals, suffix)

        label_key = _add_field("Measure", "Continuous", meas_field)
        encodings.append({"fieldKey": label_key, "type": "Label"})
        enc_fields[label_key] = encoding_field_entry(fmt_type, decimals, suffix)

        stack_field = field_map.get("stack_dim")
        if stack_field:
            stack_key = _add_field("Dimension", "Discrete", stack_field)
            enc_color_key = _add_field("Dimension", "Discrete", stack_field)
            encodings.append({"fieldKey": enc_color_key, "type": "Color"})
            enc_fields[enc_color_key] = {
                "defaults": {"format": {}},
                "colors": {
                    "customColors": [],
                    "palette": {"colors": palette, "type": "Custom"},
                    "type": "Discrete",
                }
            }
            legends[enc_color_key] = {"isVisible": True, "position": "Right", "title": {"isVisible": True}}

        if template.get("sort_descending"):
            sort_orders["fields"][cat_key] = {"byField": meas_key, "order": "Descending", "type": "Nested"}

    elif template_name == "donut":
        cat_field = field_map.get("category", list(field_map.values())[0])
        meas_field = field_map.get("amount", field_map.get("measure", list(field_map.values())[-1]))

        cat_key = _add_field("Dimension", "Discrete", cat_field)
        columns.append(cat_key)
        hdr_fields[cat_key] = header_field_entry()

        fmt_type, decimals, suffix = _infer_format(meas_field)
        color_key = _add_field("Dimension", "Discrete", cat_field)
        encodings.append({"fieldKey": color_key, "type": "Color"})
        enc_fields[color_key] = {
            "defaults": {"format": {}},
            "colors": {
                "customColors": [],
                "palette": {"colors": palette, "type": "Custom"},
                "type": "Discrete",
            }
        }
        legends[color_key] = {"isVisible": True, "position": "Right", "title": {"isVisible": True}}

        angle_key = _add_field("Measure", "Continuous", meas_field)
        encodings.append({"fieldKey": angle_key, "type": "Angle"})
        enc_fields[angle_key] = encoding_field_entry(fmt_type, decimals, suffix)

        label_key = _add_field("Measure", "Continuous", meas_field)
        encodings.append({"fieldKey": label_key, "type": "Label"})
        enc_fields[label_key] = encoding_field_entry(fmt_type, decimals, suffix)

    elif template_name == "heatmap":
        row_field = field_map.get("row_dim", list(field_map.values())[0])
        col_field = field_map.get("col_dim", list(field_map.values())[1] if len(field_map) > 1 else row_field)
        meas_field = field_map.get("measure", list(field_map.values())[-1])

        col_key = _add_field("Dimension", "Discrete", col_field)
        columns.append(col_key)
        hdr_fields[col_key] = header_field_entry()

        row_key = _add_field("Dimension", "Discrete", row_field)
        rows.append(row_key)
        hdr_fields[row_key] = header_field_entry()

        fmt_type, decimals, suffix = _infer_format(meas_field)
        color_meas_key = _add_field("Measure", "Continuous", meas_field)
        encodings.append({"fieldKey": color_meas_key, "type": "Color"})
        enc_fields[color_meas_key] = {
            "colors": {
                "palette": {"end": "#FF906E", "start": "#5867E8", "startToEndSteps": []},
                "type": "Continuous",
            }
        }

        label_key = _add_field("Measure", "Continuous", meas_field)
        encodings.append({"fieldKey": label_key, "type": "Label"})
        enc_fields[label_key] = encoding_field_entry(fmt_type, decimals, suffix)
        legends[color_meas_key] = {"isVisible": True, "position": "Right", "title": {"isVisible": True}}

    elif template_name == "scatter":
        x_field = field_map.get("x_measure", list(field_map.values())[0])
        y_field = field_map.get("y_measure", list(field_map.values())[1] if len(field_map) > 1 else x_field)

        fmt_x, dec_x, suf_x = _infer_format(x_field)
        x_key = _add_field("Measure", "Continuous", x_field)
        columns.append(x_key)
        axis_fields[x_key] = axis_field_entry(fmt_x, dec_x, suf_x)
        enc_fields[x_key] = encoding_field_entry(fmt_x, dec_x, suf_x)

        fmt_y, dec_y, suf_y = _infer_format(y_field)
        y_key = _add_field("Measure", "Continuous", y_field)
        rows.append(y_key)
        axis_fields[y_key] = axis_field_entry(fmt_y, dec_y, suf_y)
        enc_fields[y_key] = encoding_field_entry(fmt_y, dec_y, suf_y)

        cat_field = field_map.get("category")
        if cat_field:
            detail_key = _add_field("Dimension", "Discrete", cat_field)
            encodings.append({"fieldKey": detail_key, "type": "Detail"})
            color_key = _add_field("Dimension", "Discrete", cat_field)
            encodings.append({"fieldKey": color_key, "type": "Color"})
            enc_fields[color_key] = {
                "defaults": {"format": {}},
                "colors": {
                    "customColors": [],
                    "palette": {"colors": palette, "type": "Custom"},
                    "type": "Discrete",
                }
            }
            legends[color_key] = {"isVisible": True, "position": "Right", "title": {"isVisible": True}}

    elif template_name == "funnel":
        stage_field = field_map.get("stage", list(field_map.values())[0])
        count_field = field_map.get("count", field_map.get("amount", list(field_map.values())[-1]))

        stage_key = _add_field("Dimension", "Discrete", stage_field)
        columns.append(stage_key)
        hdr_fields[stage_key] = header_field_entry()

        fmt_type, decimals, suffix = _infer_format(count_field)
        count_key = _add_field("Measure", "Continuous", count_field)
        rows.append(count_key)
        axis_fields[count_key] = axis_field_entry(fmt_type, decimals, suffix)
        enc_fields[count_key] = encoding_field_entry(fmt_type, decimals, suffix)

        label_key = _add_field("Measure", "Continuous", count_field)
        encodings.append({"fieldKey": label_key, "type": "Label"})
        enc_fields[label_key] = encoding_field_entry(fmt_type, decimals, suffix)

        sort_orders["fields"][stage_key] = {"byField": count_key, "order": "Descending", "type": "Nested"}

    # Build the complete payload
    mark_type = template["mark_type"]
    is_stacked = template.get("stacked", False)
    is_funnel = template.get("is_funnel", False)

    style = {
        "axis": {"fields": axis_fields},
        "encodings": {"fields": enc_fields},
        "fieldLabels": build_field_labels(style_overrides),
        "fit": resolve_fit(style_overrides, cfg["fit"]),
        "fonts": build_fonts(style_overrides),
        "headers": {
            "columns": {"mergeRepeatedCells": True, "showIndex": False},
            "rows": {"mergeRepeatedCells": True, "showIndex": False},
            "fields": hdr_fields,
        },
        "lines": build_lines(style_overrides),
        "marks": {
            "fields": {},
            "headers": marks_headers_style(reverse=cfg["reverse"]),
            "panes": marks_panes_style(
                reverse=cfg["reverse"],
                size_type=cfg["size_type"],
                size_value=cfg["size_val"],
                auto_size=cfg["auto_size"],
                is_funnel=is_funnel,
            ),
        },
        "referenceLines": {},
        "shading": build_shading(style_overrides, with_banding=cfg["banding"]),
        "showDataPlaceholder": False,
        "title": {"isVisible": True},
    }

    payload = {
        "name": viz_name,
        "label": viz_label,
        "dataSource": {"name": sdm_api, "label": viz_label, "type": "SemanticModel"},
        "workspace": {"name": ws_api, "label": ws_api},
        "interactions": [],
        "fields": fields,
        "visualSpecification": {
            "layout": "Vizql",
            "columns": columns,
            "rows": rows,
            "forecasts": {},
            "measureValues": [],
            "referenceLines": {},
            "legends": legends,
            "marks": {
                "fields": {},
                "headers": copy.deepcopy(VIZQL_MARK_HEADERS),
                "panes": {
                    "encodings": encodings,
                    "isAutomatic": not bool(encodings),
                    "type": mark_type,
                    "stack": {"isAutomatic": True, "isStacked": is_stacked},
                },
            },
            "style": style,
        },
        "view": {
            "label": "default",
            "name": f"{viz_name}_default",
            "viewSpecification": {"sortOrders": sort_orders},
        },
    }

    if validate:
        ok, results = is_valid(payload)
        if not ok:
            print(f"\n  Validation FAILED for viz '{viz_label}':")
            print_results(results)
            print()

    return payload
