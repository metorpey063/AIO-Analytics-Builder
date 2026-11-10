"""Deploy Tableau Next dashboard templates from Package & Deploy packages.

Uses the full VizQL specs captured by the Package & Deploy API to create
pixel-perfect replicas of the Z Layout and F Layout product templates.
Unlike the MCP slim-spec approach, this creates vizzes via REST with the
complete style scaffold, ensuring the output matches the template engine's
rendering exactly.

Templates are stored in demos/z_layout_package.json and demos/f_layout_package.json.
"""

import copy
import json
import os
import re
import requests
import uuid
from typing import Any, Dict, List, Optional, Tuple

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "demos")

AVAILABLE_TEMPLATES = {
    "z_layout": {
        "file": "z_layout_package.json",
        "label": "Z Layout",
        "description": "Filters → 6 KPIs → hero viz → 3-up detail → full-width bottom",
        "max_metrics": 6,
        "max_filters": 6,
        "viz_slots": ["hero_trend", "detail_donut", "detail_bar", "detail_bar_2", "detail_table"],
    },
    "f_layout": {
        "file": "f_layout_package.json",
        "label": "F Layout",
        "description": "Filters → 3 KPIs (left) + hero viz (right) → 3-up detail → full-width bottom",
        "max_metrics": 3,
        "max_filters": 6,
        "viz_slots": ["hero_trend", "detail_donut", "detail_bar", "detail_bar_2", "detail_table"],
    },
    "exec_summary": {
        "file": "exec_summary_package.json",
        "label": "Executive Summary",
        "description": "5 KPIs → stacked bar trend (YoY) → 2-up horizontal bar entity ranking",
        "max_metrics": 5,
        "max_filters": 0,
        "viz_slots": ["trend_stacked_bar", "entity_bar_1", "entity_bar_2", "entity_bar_3"],
        # Captured from one customer's demo: remapped by role (see prepare_role_viz_payloads)
        "roles": {
            "measures": ["measure_1", "measure_2"],
            "dims": ["dim_1", "dim_2"],
            "dates": ["date_1"],
            "remove": ["image_1"],
            "title": {"row": 1, "column": 1, "rowspan": 7, "colspan": 70},   # the band above the KPIs
            "bar_for_donut": None,
        },
    },
    "trend_breakdown": {
        "file": "trend_breakdown_package.json",
        "label": "Trend & Breakdown",
        "description": "Title → 4 KPIs → year-over-year trend → three breakdowns",
        "max_metrics": 4,
        "max_filters": 0,
        "viz_slots": ["trend_stacked_bar", "donut_breakdown", "entity_bar", "brand_bar"],
        "roles": {
            "measures": ["measure_1"],
            "dims": ["dim_1", "dim_2", "dim_3"],
            "dates": ["date_1"],
            "remove": ["image_1"],
            "kpi_text": ["text_1", "text_2", "text_3", "text_4"],   # static numbers in the capture -> metric tiles
            "title": {"widget": "text_5", "row": 0, "column": 1, "rowspan": 4, "colspan": 70},
            "bar_for_donut": "breakdown_2",
        },
    },
}


def load_template(template_name: str) -> Dict[str, Any]:
    """Load a template package from disk."""
    meta = AVAILABLE_TEMPLATES[template_name]
    path = os.path.join(TEMPLATE_DIR, meta["file"])
    with open(path) as f:
        return json.load(f)


def _substitute(obj: Any, replacements: Dict[str, str]) -> Any:
    """Recursively substitute {{PLACEHOLDER}} values in a nested structure."""
    if isinstance(obj, str):
        for placeholder, value in replacements.items():
            obj = obj.replace(placeholder, value)
        return obj
    elif isinstance(obj, dict):
        return {k: _substitute(v, replacements) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_substitute(item, replacements) for item in obj]
    return obj


def _strip_readonly(obj: Any) -> Any:
    """Strip read-only keys and problematic empty structures for POST."""
    strip_keys = {
        "id", "createdBy", "createdDate", "lastModifiedBy", "lastModifiedDate",
        "permissions", "sourceVersion", "templateSource", "creationSource",
        "url", "isOriginal", "semanticModel", "useInlineModel", "targetVersion",
        "stylesheet",
    }
    # Keys with empty arrays/objects that cause deserialization errors on POST
    strip_empty = {"publishers", "widgetIds"}
    # Keys accepted on viz/GET but rejected on dashboard widget POST
    strip_keys |= {
        "receiveFilterSource", "receiveParameterSource",
        "lineSpacing", "verticalAlignment", "conditionalFormattingRules",
    }
    if isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            if k in strip_keys:
                continue
            if k in strip_empty and isinstance(v, list) and len(v) == 0:
                continue
            result[k] = _strip_readonly(v)
        return result
    elif isinstance(obj, list):
        return [_strip_readonly(i) for i in obj]
    return obj


# Placeholder text in the template's text widgets. Any left after label_map
# substitution is blanked so it never shows on a live dashboard.
TEXT_PLACEHOLDERS = {"Section Subheader", "Title/ Time + Name"}

BAR_VIZZES = {"Horizontal_Bar", "Detail_Bar_2"}


def _role(viz_name: str) -> str:
    """A Z/F viz's role from its template name. F Layout's copies carry a number
    (`Donut_Chart1`, `Details_Table1`), so match on the name without it."""
    return re.sub(r"(?<![_\d])\d+$", "", viz_name)   # Donut_Chart1 -> Donut_Chart; Detail_Bar_2 stays


def _first_dimension_key(payload: Dict[str, Any]) -> Optional[str]:
    for fk, fv in payload.get("fields", {}).items():
        if fv.get("role") == "Dimension":
            return fk
    return None


def _set_percent_format(payload: Dict[str, Any], percent_fields: set) -> None:
    """Format measures whose fieldName is in percent_fields as percentages.

    The template ships every measure as Number with 2 decimals, so a rate
    reads 0.73 instead of 73%. Cell/label values use "Percentage", axis
    ticks use "PercentageShort" (same pairing as Number/NumberShort).
    """
    spec = payload.get("visualSpecification", {})
    style = spec.get("style", {})
    for fk, fv in payload.get("fields", {}).items():
        if fv.get("role") != "Measure" or fv.get("fieldName") not in percent_fields:
            continue
        enc = style.get("encodings", {}).get("fields", {}).get(fk)
        if enc:
            nfi = enc.setdefault("defaults", {}).setdefault("format", {}).setdefault("numberFormatInfo", {})
            nfi.update({"type": "Percentage", "decimalPlaces": 1})
        axis = style.get("axis", {}).get("fields", {}).get(fk)
        if axis:
            nfi = axis.setdefault("scale", {}).setdefault("format", {}).setdefault("numberFormatInfo", {})
            nfi.update({"type": "PercentageShort", "decimalPlaces": 0})


def _color_by_dimension(payload: Dict[str, Any]) -> None:
    """Color a bar chart's bars by its category dimension, so one partner/segment
    keeps the same color across every breakdown chart. The axis already names
    each bar, so the legend stays hidden (same as the template trend line)."""
    dim_key = _first_dimension_key(payload)
    spec = payload.get("visualSpecification", {})
    panes = spec.get("marks", {}).get("panes")
    if not dim_key or panes is None:
        return
    encodings = panes.setdefault("encodings", [])
    if any(e.get("type") == "Color" for e in encodings):
        return
    encodings.append({"fieldKey": dim_key, "type": "Color"})
    spec.setdefault("legends", {})[dim_key] = {
        "isVisible": False, "position": "Right", "title": {"isVisible": True}}


def _month_grain_dates(payload: Dict[str, Any]) -> None:
    """Group a trend line's date by month. With no function every daily date
    is its own header and the x-axis labels truncate ("12/..."). "Mdy" is the
    month-level date function the product's own line charts use."""
    for fv in payload.get("fields", {}).values():
        if fv.get("role") == "Dimension" and "date" in fv.get("fieldName", "").lower() and not fv.get("function"):
            fv["function"] = "Mdy"


def _add_table_measures(payload: Dict[str, Any], measures: List[Dict[str, Any]]) -> None:
    """Append metric columns to a details table (the template ships dimensions only).

    Each measure: {"fieldName": clc_api, "label": str, "percent": bool}. Same shape
    as the product's Leaderboard tables: discrete measures in `rows`, each with a
    number format and a header entry.
    """
    spec = payload.get("visualSpecification", {})
    style = spec.setdefault("style", {})
    fields = payload.setdefault("fields", {})
    used = [int(k[1:]) for k in fields if k[1:].isdigit()]
    nxt = max(used or [0]) + 1
    for m in measures:
        fk = f"F{nxt}"
        nxt += 1
        fields[fk] = {"displayCategory": "Discrete", "fieldName": m["fieldName"], "function": "UserAgg",
                      "label": m.get("label", m["fieldName"]), "role": "Measure", "type": "Field"}
        spec.setdefault("rows", []).append(fk)
        nfi = {"decimalPlaces": 1 if m.get("percent") else 0, "displayUnits": "Auto",
               "includeThousandSeparator": True, "negativeValuesFormat": "Auto",
               "prefix": "", "suffix": "", "type": "Percentage" if m.get("percent") else "Number"}
        style.setdefault("encodings", {}).setdefault("fields", {})[fk] = {"defaults": {"format": {"numberFormatInfo": nfi}}}
        style.setdefault("headers", {}).setdefault("fields", {})[fk] = {
            "hiddenValues": [], "isVisible": True, "showMissingValues": False}


_TABLE_MARK_STYLE = {"color": {"color": ""}, "isAutomaticSize": True,
                     "label": {"canOverlapLabels": False, "marksToLabel": {"type": "All"}, "showMarkLabels": False},
                     "range": {"reverse": True}, "size": {"isAutomatic": True, "type": "Pixel", "value": 12}}
_TABLE_MARK = {"encodings": [], "isAutomatic": True, "stack": {"isAutomatic": True, "isStacked": False}, "type": "Text"}


def _to_table_layout(payload: Dict[str, Any]) -> None:
    """Convert a Vizql-layout text table to the Table layout, fit to width.

    A Vizql table only accepts fit "Standard" or "Entire" (which squeezes every
    row into the widget). Fit-to-width ("RowHeadersWidth") needs the Table
    layout — the shape the product's own Leaderboard tables use, copied here
    key for key. Keeps the payload's fields, rows, number formats and fonts.
    """
    spec = payload["visualSpecification"]
    old_style = spec.get("style", {})
    fields = payload.get("fields", {})
    rows = spec.get("rows", [])
    enc = old_style.get("encodings", {}).get("fields", {})
    header_fields = {}
    for fk in rows:
        hf = {"hiddenValues": [], "isVisible": True, "showMissingValues": False}
        if fields.get(fk, {}).get("role") == "Measure" and fk in enc:
            hf["defaults"] = copy.deepcopy(enc[fk]["defaults"])
        header_fields[fk] = hf
    spec_new = {
        "layout": "Table",
        "groups": [],
        "legends": {},
        "rows": rows,
        "marks": {
            "fields": {fk: copy.deepcopy(_TABLE_MARK) for fk in rows},
            "headers": {**copy.deepcopy(_TABLE_MARK), "isAutomatic": False},
            "panes": {**copy.deepcopy(_TABLE_MARK), "isAutomatic": False},
        },
        "style": {
            "encodings": {"fields": {fk: e for fk, e in enc.items() if fk in rows}},
            "fieldLabels": {"columns": {"backgroundColor": "#E5E5E5", "showDividerLine": False, "showLabels": True},
                            "groups": {"showDividerLine": False, "showLabels": True},
                            "rows": {"backgroundColor": "#E5E5E5", "showDividerLine": False, "showLabels": True}},
            "fit": "RowHeadersWidth",
            "fonts": old_style.get("fonts", {}),
            "headers": {"columns": {"mergeRepeatedCells": False, "showIndex": False, "sizing": {"fieldHeight": {}}},
                        "fields": header_fields,
                        "groups": {"mergeRepeatedCells": True, "sizing": {"fieldWidth": {}}},
                        "rows": {"mergeRepeatedCells": False, "showIndex": False, "sizing": {"fieldWidth": {}}}},
            "lines": {"axisLine": {"color": "#C9C9C9"}, "fieldLabelDividerLine": {"color": "#C9C9C9"},
                      "separatorLine": {"color": "#C9C9C9"}, "zeroLine": {"color": "#E5E5E5"}},
            "marks": {"fields": {fk: copy.deepcopy(_TABLE_MARK_STYLE) for fk in rows},
                      "headers": copy.deepcopy(_TABLE_MARK_STYLE),
                      "panes": {**copy.deepcopy(_TABLE_MARK_STYLE), "range": {"reverse": False}}},
            "shading": {"backgroundColor": "#FFFFFF", "banding": {"rows": {"color": "#E5E5E5"}}},
            "title": old_style.get("title", {"isVisible": True}),
        },
    }
    payload["visualSpecification"] = spec_new


def remove_widget(dash_payload: Dict[str, Any], widget_name: str) -> None:
    """Remove a widget from a dashboard payload everywhere it's referenced.

    A widget lives in two places: the top-level `widgets` dict and each layout
    page's `widgets` position list. Removing it from only one makes the POST
    fail (an orphaned `{{VIZ_NAME_...}}` source returns 500 "Visualization Not
    Found"), so always remove widgets through this helper.
    """
    dash_payload.get("widgets", {}).pop(widget_name, None)
    for layout in dash_payload.get("layouts", []):
        for page in layout.get("pages", []):
            page["widgets"] = [w for w in page.get("widgets", []) if w.get("name") != widget_name]


def prepare_viz_payloads(
    package: Dict[str, Any],
    *,
    sdm_api: str,
    sdm_label: str,
    sdm_id: str,
    ws_api: str,
    ws_label: str,
    ws_id: str,
    do_api: str = "",
    slug: str,
    field_map: Optional[Dict[str, str]] = None,
    label_map: Optional[Dict[str, str]] = None,
    percent_fields: Optional[List[str]] = None,
    donut_as_bar: bool = False,
    trend_include_zero: bool = False,
    color_bars: bool = True,
    table_measures: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Prepare viz creation payloads from a template package.

    Substitutes placeholders and renames vizzes for the target demo.
    Returns {viz_template_name: payload} ready for POST.

    Args:
        package: Loaded template package
        sdm_api: Target SDM apiName
        sdm_label: Target SDM label
        sdm_id: Target SDM Salesforce ID
        ws_api: Target workspace apiName
        ws_label: Target workspace label
        ws_id: Target workspace Salesforce ID
        do_api: Target data object apiName (replaces all objectName references)
        slug: Demo slug for naming (e.g. "d16")
        field_map: Optional mapping of template field names to target field names.
                   Keys are template fieldNames, values are target fieldNames.
                   Only needed if the target SDM has different field apiNames.
        percent_fields: Target measure fieldNames (e.g. `_clc` apiNames) to format
                   as percentages. Only pass rate metrics (viz_templates.is_percent_metric).
        donut_as_bar: Replace the donut with a horizontal bar on the same dimension.
                   Use when the donut's measure is an Average — slices of an average
                   (e.g. Days Until Renewal) don't add up to anything.
        trend_include_zero: Start the trend line's Y axis at zero. Off by default:
                   rates in a narrow band (0.71-0.92) look flat on a 0-100% axis.
        color_bars: Color bar charts by their category dimension.
        table_measures: Metric columns for the details table, e.g.
                   [{"fieldName": "win_rate_clc", "label": "Win Rate", "percent": True}].
                   Without them the table lists dimension combinations only.
    """
    replacements = {
        "{{SDM_API_NAME}}": sdm_api,
        "{{SDM_LABEL}}": sdm_label,
        "{{WORKSPACE_API_NAME}}": ws_api,
        "{{WORKSPACE_LABEL}}": ws_label,
    }

    # Discover the template's DO name so we can replace it with the target's
    template_do_names = set()
    for viz_def in package["components"]["visualizations"].values():
        for fv in viz_def.get("fields", {}).values():
            on = fv.get("objectName", "")
            if on and not on.startswith("{{"):
                template_do_names.add(on)

    vizzes = dict(package["components"]["visualizations"])

    # Generate Detail_Bar_2 for the empty 3rd detail slot (Z Layout / F Layout)
    horiz_key = "Horizontal_Bar" if "Horizontal_Bar" in vizzes else "Horizontal_Bar1" if "Horizontal_Bar1" in vizzes else None
    if "Detail_Bar_2" not in vizzes and horiz_key:
        bar2 = copy.deepcopy(vizzes[horiz_key])
        for fk, fv in bar2.get("fields", {}).items():
            if fv.get("role") == "Dimension":
                fv["fieldName"] = "team1"
                break
        bar2["label"] = "Detail Bar 2"
        vizzes["Detail_Bar_2"] = bar2

    # Swap the donut for a bar on the donut's own dimension (keeps its slot and label)
    donut_key = next((k for k in vizzes if _role(k) == "Donut_Chart"), None)
    if donut_as_bar and donut_key and horiz_key:
        donut = vizzes[donut_key]
        donut_dim = next((fv["fieldName"] for fv in donut.get("fields", {}).values()
                          if fv.get("role") == "Dimension"), None)
        if donut_dim:
            bar = copy.deepcopy(vizzes[horiz_key])
            for fv in bar.get("fields", {}).values():
                if fv.get("role") == "Dimension":
                    fv["fieldName"] = donut_dim
                    break
            bar["label"] = donut.get("label", "Donut Chart")
            bar["name"] = donut.get("name", donut_key)
            vizzes[donut_key] = bar

    payloads = {}

    for viz_name, viz_def in vizzes.items():
        payload = copy.deepcopy(viz_def)
        payload = _substitute(payload, replacements)
        payload = _strip_readonly(payload)

        # Rename for the target demo
        payload["name"] = f"{slug}_{viz_name.lower()}"
        payload["label"] = payload.get("label", viz_name.replace("_", " "))

        # Set workspace
        payload["workspace"] = {"name": ws_api, "label": ws_label}

        # Remap fields: both fieldName and objectName
        for fk, fv in payload.get("fields", {}).items():
            # Replace objectName from template DO to target DO
            if do_api and fv.get("objectName") in template_do_names:
                fv["objectName"] = do_api
            # Replace fieldName via field_map
            if field_map and fv.get("fieldName") in field_map:
                fv["fieldName"] = field_map[fv["fieldName"]]
            # Note: keep 'role' and 'type' — the REST API needs both for field validation

        # Also substitute field names in the DO-qualified expressions throughout the payload
        if do_api and template_do_names:
            for old_do in template_do_names:
                payload = _substitute(payload, {old_do: do_api})

        # Substitute display labels (axis titles, viz titles, etc.)
        if label_map:
            payload = _substitute(payload, label_map)

        role = _role(viz_name)
        if percent_fields:
            _set_percent_format(payload, set(percent_fields))
        if role == "Trend_Line":
            _month_grain_dates(payload)
        if role == "Details_Table":
            if table_measures:
                _add_table_measures(payload, table_measures)
            # Fit to width: needs the Table layout (a Vizql table only takes
            # "Standard" or "Entire"); deploy_template posts it on v67.0
            _to_table_layout(payload)
        if role == "Trend_Line" and not trend_include_zero:
            axis_fields = payload.get("visualSpecification", {}).get("style", {}).get("axis", {}).get("fields", {})
            for ax in axis_fields.values():
                if "range" in ax:
                    ax["range"]["includeZero"] = False
        if color_bars and (role in BAR_VIZZES or (donut_as_bar and role == "Donut_Chart")):
            _color_by_dimension(payload)

        payloads[viz_name] = payload

    return payloads


def _clean_widget_for_post(widget: Dict[str, Any]) -> Dict[str, Any]:
    """Strip widget parameters to only what the REST dashboard POST accepts.

    The package/GET returns many fields (receiveFilterSource, lineSpacing,
    conditionalFormattingRules, etc.) that POST rejects. This whitelists
    only the accepted keys per widget type.
    """
    w = copy.deepcopy(widget)
    wtype = w.get("type", "")

    if wtype == "metric":
        params = w.get("parameters", {})
        clean_params = {}
        if "metricOption" in params:
            mo = params["metricOption"]
            clean_params["metricOption"] = {
                k: v for k, v in mo.items()
                if k in ("sdmApiName", "sdmId", "layout")
            }
        if "widgetStyle" in params:
            clean_params["widgetStyle"] = params["widgetStyle"]
        w["parameters"] = clean_params

    elif wtype == "filter":
        params = w.get("parameters", {})
        clean_params = {}
        for k in ("viewType", "isLabelHidden", "filterOption", "widgetStyle"):
            if k in params:
                clean_params[k] = params[k]
        w["parameters"] = clean_params

    elif wtype == "text":
        params = w.get("parameters", {})
        clean_params = {}
        for k in ("content", "widgetStyle"):
            if k in params:
                clean_params[k] = params[k]
        w["parameters"] = clean_params

    elif wtype == "visualization":
        params = w.get("parameters", {})
        clean_params = {}
        for k in ("legendPosition", "widgetStyle"):
            if k in params:
                clean_params[k] = params[k]
        w["parameters"] = clean_params

    elif wtype == "container":
        params = w.get("parameters", {})
        clean_params = {}
        if "widgetStyle" in params:
            clean_params["widgetStyle"] = params["widgetStyle"]
        w["parameters"] = clean_params

    # Ensure required fields
    w.setdefault("actions", [])
    return w


def prepare_dashboard_payload(
    package: Dict[str, Any],
    *,
    sdm_api: str,
    sdm_id: str,
    ws_api: str,
    slug: str,
    dash_label: str,
    metric_apis: List[str],
    viz_name_map: Dict[str, str],
    filter_fields: Optional[List[Dict[str, str]]] = None,
    title_text: Optional[str] = None,
    detail_header: Optional[str] = None,
    label_map: Optional[Dict[str, str]] = None,
    detail_headers: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Prepare a dashboard payload from a template package.

    Args:
        package: Loaded template package
        sdm_api: Target SDM apiName
        sdm_id: Target SDM Salesforce ID
        ws_api: Target workspace apiName
        slug: Demo slug for naming
        dash_label: Dashboard display label
        metric_apis: Ordered list of metric _mtc apiNames to assign to metric slots
        viz_name_map: Maps template viz names to created viz apiNames
                      e.g. {"Trend_Line": "d16_trend_line", "Donut_Chart": "d16_donut_chart"}
        filter_fields: List of dicts with fieldName, objectName, label, dataType
        title_text: Override for the hero title text
        detail_header: Override for the detail section header text
        label_map: Optional text substitutions for dashboard text widget content
        detail_headers: Optional chart section headers for text_6, text_7, text_8
    """
    dash_def = copy.deepcopy(package["components"]["dashboard"])

    # Build replacement map
    replacements = {
        "{{SDM_API_NAME}}": sdm_api,
    }
    for template_name, target_name in viz_name_map.items():
        replacements[f"{{{{VIZ_NAME_{template_name}}}}}"] = target_name

    dash_def = _substitute(dash_def, replacements)
    dash_def = _strip_readonly(dash_def)

    # Set dashboard name and label
    dash_def["name"] = f"{slug}_dashboard"
    dash_def["label"] = dash_label
    dash_def["workspaceIdOrApiName"] = ws_api

    widgets = dash_def.get("widgets", {})

    # Assign metrics to slots
    metric_slots = sorted([k for k in widgets if k.startswith("metric_")])
    for i, slot_name in enumerate(metric_slots):
        w = widgets[slot_name]
        if i < len(metric_apis):
            w["source"] = {"name": metric_apis[i]}
            w["parameters"]["metricOption"]["sdmApiName"] = sdm_api
            w["parameters"]["metricOption"]["sdmId"] = sdm_id
        else:
            # Empty slot — remove source so it shows as placeholder
            w.pop("source", None)

    # Assign filters
    filter_fields = filter_fields or []
    filter_slots = sorted([k for k in widgets if k.startswith("filter_")])
    for i, slot_name in enumerate(filter_slots):
        w = widgets[slot_name]
        if i < len(filter_fields):
            ff = filter_fields[i]
            w["source"] = {"name": sdm_api}
            w["label"] = ff.get("label", ff["fieldName"])
            w["parameters"]["filterOption"] = {
                "fieldName": ff["fieldName"],
                "objectName": ff["objectName"],
                "dataType": ff.get("dataType", "Text"),
                "selectionType": "multiple",
            }
        # Leave unconfigured filter slots as-is (empty placeholders)

    # Wire Detail_Bar_2 into any empty viz slot
    for wname, w in widgets.items():
        if w.get("type") == "visualization" and not w.get("source", {}).get("name"):
            if "Detail_Bar_2" in viz_name_map:
                w["source"] = {"name": viz_name_map["Detail_Bar_2"]}

    # Override text widgets
    if title_text:
        for wname in ["text_1"]:
            if wname in widgets and widgets[wname]["type"] == "text":
                content = widgets[wname]["parameters"].get("content", [])
                if content:
                    content[0]["insert"] = title_text

    if detail_header:
        for wname in ["text_2"]:
            if wname in widgets and widgets[wname]["type"] == "text":
                content = widgets[wname]["parameters"].get("content", [])
                if content:
                    content[0]["insert"] = detail_header

    # Set detail chart section headers (text_6, text_7, text_8)
    detail_text_slots = ["text_6", "text_7", "text_8"]
    for i, slot_name in enumerate(detail_text_slots):
        if slot_name in widgets and widgets[slot_name]["type"] == "text":
            content = widgets[slot_name]["parameters"].get("content", [])
            if detail_headers and i < len(detail_headers):
                if content:
                    content[0]["insert"] = detail_headers[i]
            elif label_map and content:
                for entry in content:
                    if "insert" in entry and isinstance(entry["insert"], str):
                        for old, new in label_map.items():
                            entry["insert"] = entry["insert"].replace(old, new)

    # Apply label_map to remaining text widgets (Section Subheader etc.)
    if label_map:
        for wname, w in widgets.items():
            if w.get("type") == "text" and wname not in detail_text_slots:
                for entry in w.get("parameters", {}).get("content", []):
                    if "insert" in entry and isinstance(entry["insert"], str):
                        for old, new in label_map.items():
                            entry["insert"] = entry["insert"].replace(old, new)

    # Blank any template placeholder text nothing replaced
    for w in widgets.values():
        if w.get("type") == "text":
            for entry in w.get("parameters", {}).get("content", []):
                if isinstance(entry.get("insert"), str) and entry["insert"].strip() in TEXT_PLACEHOLDERS:
                    entry["insert"] = ""

    # Clean all widgets for REST POST compatibility
    dash_def["widgets"] = {
        wname: _clean_widget_for_post(w)
        for wname, w in widgets.items()
    }

    return dash_def


# ---- captured templates: remap by role ----------------------------------------------------------
#
# Executive Summary and Trend & Breakdown were captured from customer demos, so
# their vizzes reference that demo's own object and fields. They're remapped by role: each source
# field is a date, measure N or dimension N (AVAILABLE_TEMPLATES[...]["roles"]), and becomes the
# target demo's Display_Date, Nth metric calc or Nth dimension. A template that asks for more
# measures or dimensions than the demo has reuses them in order (source field k -> target k mod n),
# so a source metric always maps to the same demo metric.
#
# role_target (built by the caller):
#   {"measures": [{"field": "<x>_clc", "label": str, "percent": bool, "sum": bool}],
#    "dims": [{"field": dim_api, "label": str}], "date": display_date_api,
#    "metrics": [mtc_api, ...], "title": str}

_KPI_LAYOUT = {"componentVisibility": {"comparison": True, "insights": False, "details": False,
                                       "title": True, "value": True, "chart": False, "goals": False}}


def _pick(items: List[Any], i: int) -> Any:
    return items[i % len(items)]


def _map_role_field(fv: Dict[str, Any], roles: Dict[str, Any], target: Dict[str, Any], do_api: str) -> Dict[str, Any]:
    src = fv.get("fieldName")
    if src in roles["measures"]:
        m = _pick(target["measures"], roles["measures"].index(src))
        return {"displayCategory": fv.get("displayCategory", "Continuous"), "fieldName": m["field"],
                "function": "UserAgg", "role": "Measure", "type": "Field"}
    if src in roles["dims"]:
        d = _pick(target["dims"], roles["dims"].index(src))
        out = {k: v for k, v in fv.items() if k != "function"}
        out.update(fieldName=d["field"], objectName=do_api)
        return out
    if src in roles["dates"]:
        out = {k: v for k, v in fv.items() if k != "objectName"}
        out["fieldName"] = target["date"]
        return out
    raise ValueError(f"template field {src!r} has no role; add it to the template's roles")


def _role_title(payload: Dict[str, Any], labels: Dict[str, str]) -> str:
    """Title from what the viz shows: '<M> by Month, Year over Year', '<M> vs <M2> by <D>', '<M> by <D>'."""
    spec = payload.get("visualSpecification", {})
    shown = list(dict.fromkeys((spec.get("columns") or []) + (spec.get("rows") or [])
                               + [e["fieldKey"] for e in spec.get("marks", {}).get("panes", {}).get("encodings", [])
                                  if e.get("type") in ("Color", "Detail", "Angle")]))
    fields = payload.get("fields", {})
    measures, dims, dated = [], [], False
    for fk in shown or list(fields):
        fv = fields.get(fk, {})
        name = labels.get(fv.get("fieldName"), fv.get("fieldName"))
        if fv.get("role") == "Measure" and name not in measures:
            measures.append(name)
        elif fv.get("role") == "Dimension":
            if fv.get("fieldName") == labels.get("__date__"):
                dated = True
            elif name not in dims:
                dims.append(name)
    if not measures:
        return payload.get("label", "")
    head = measures[0] if len(measures) == 1 else f"{measures[0]} vs {measures[1]}"
    if dated:
        return f"{head} by Month, Year over Year"
    return f"{head} by {dims[0]}" if dims else head


def _reset_number_formats(payload: Dict[str, Any], percent_fields: set) -> None:
    """Drop the source's currency/units formatting; numbers (or percentages for rate metrics)."""
    style = payload.get("visualSpecification", {}).get("style", {})
    for fk, fv in payload.get("fields", {}).items():
        if fv.get("role") != "Measure":
            continue
        for path in (("encodings", "fields", fk, "defaults", "format", "numberFormatInfo"),
                     ("axis", "fields", fk, "scale", "format", "numberFormatInfo")):
            node = style
            for p in path[:-1]:
                node = node.get(p) if isinstance(node, dict) else None
                if node is None:
                    break
            if isinstance(node, dict) and isinstance(node.get(path[-1]), dict):
                node[path[-1]].update(prefix="", suffix="", displayUnits="Auto",
                                      type="Number" if fv.get("fieldName") not in percent_fields else node[path[-1]].get("type", "Number"))
    if percent_fields:
        _set_percent_format(payload, percent_fields)


def prepare_role_viz_payloads(package: Dict[str, Any], roles: Dict[str, Any], target: Dict[str, Any], *,
                              sdm_api: str, sdm_label: str, ws_api: str, ws_label: str, do_api: str,
                              slug: str, color_bars: bool = True) -> Dict[str, Dict[str, Any]]:
    vizzes = copy.deepcopy(package["components"]["visualizations"])
    # A donut is share of a whole: rebuild donuts on non-summed metrics from the template's own bar chart
    bar_src = roles.get("bar_for_donut")
    for name, v in list(vizzes.items()):
        if v["visualSpecification"].get("marks", {}).get("panes", {}).get("type") != "Donut" or not bar_src:
            continue
        m_src = next((f["fieldName"] for f in v["fields"].values() if f.get("role") == "Measure"), None)
        d_src = next((f["fieldName"] for f in v["fields"].values() if f.get("role") == "Dimension"), None)
        m_tgt = _pick(target["measures"], roles["measures"].index(m_src)) if m_src in roles["measures"] else None
        if m_tgt and m_tgt.get("sum"):
            continue
        bar = copy.deepcopy(package["components"]["visualizations"][bar_src])
        for f in bar["fields"].values():
            if f.get("role") == "Measure":
                f["fieldName"] = m_src
            elif f.get("role") == "Dimension":
                f["fieldName"] = d_src
        bar["label"], bar["name"] = v.get("label"), v.get("name", name)
        vizzes[name] = bar

    labels = {m["field"]: m["label"] for m in target["measures"]}
    labels.update({d["field"]: d["label"] for d in target["dims"]})
    labels["__date__"] = target["date"]
    percent = {m["field"] for m in target["measures"] if m.get("percent")}
    replacements = {"{{SDM_API_NAME}}": sdm_api, "{{SDM_LABEL}}": sdm_label,
                    "{{WORKSPACE_API_NAME}}": ws_api, "{{WORKSPACE_LABEL}}": ws_label}
    payloads = {}
    for name, v in vizzes.items():
        p = _strip_readonly(_substitute(copy.deepcopy(v), replacements))
        p["fields"] = {fk: _map_role_field(fv, roles, target, do_api) if fv.get("type") == "Field" else fv
                       for fk, fv in p.get("fields", {}).items()}
        p["name"] = f"{slug}_{name.lower()}"[:80]
        p["label"] = _role_title(p, labels)
        p["workspace"] = {"name": ws_api, "label": ws_label}
        # axis/field titles captured from the source would name its fields; let the engine use field labels
        for ax in p.get("visualSpecification", {}).get("style", {}).get("axis", {}).get("fields", {}).values():
            ax.pop("titleText", None)
        _reset_number_formats(p, percent)
        if color_bars and p["visualSpecification"].get("marks", {}).get("panes", {}).get("type") == "Bar" \
                and not any(f.get("function", "").startswith("DatePart") for f in p["fields"].values()):
            _color_by_dimension(p)
        payloads[name] = p
    return payloads


def _set_text(widget: Dict[str, Any], text: str) -> None:
    content = widget.get("parameters", {}).get("content") or []
    first = next((b for b in content if isinstance(b, dict) and str(b.get("insert", "")).strip()), None)
    if first is None:
        widget.setdefault("parameters", {})["content"] = [{"attributes": {"bold": True, "size": "16px"}, "insert": text}]
        return
    first["insert"] = text
    for b in content:   # blank any further captured text in the same widget
        if b is not first and isinstance(b, dict) and str(b.get("insert", "")).strip():
            b["insert"] = ""


def _place_title(dash: Dict[str, Any], spec: Dict[str, Any], title: str) -> None:
    """Large, left-aligned dashboard title in the band above the KPIs (where the source logo sat)."""
    name = spec.get("widget", "title_1")
    dash["widgets"][name] = {
        "name": name, "type": "text", "actions": [],
        "parameters": {"content": [{"attributes": {"bold": True, "size": "24px", "color": "#2E2E2E"}, "insert": title},
                                   {"attributes": {"align": "left"}, "insert": "\n"}],
                       "widgetStyle": {"borderColor": "#C9C9C9", "borderEdges": []}}}
    page = dash["layouts"][0]["pages"][0]
    page["widgets"] = [w for w in page["widgets"] if w.get("name") != name]
    page["widgets"].insert(0, {"name": name, "row": spec["row"], "column": spec["column"],
                               "rowspan": spec["rowspan"], "colspan": spec["colspan"]})


def prepare_role_dashboard_payload(package: Dict[str, Any], roles: Dict[str, Any], target: Dict[str, Any], *,
                                   sdm_api: str, sdm_id: str, ws_api: str, do_api: str, slug: str, dash_label: str,
                                   viz_name_map: Dict[str, str], viz_titles: Dict[str, str]) -> Dict[str, Any]:
    dash = copy.deepcopy(package["components"]["dashboard"])
    repl = {"{{SDM_API_NAME}}": sdm_api, "{{SDM_ID}}": sdm_id}
    repl.update({f"{{{{VIZ_NAME_{k}}}}}": v for k, v in viz_name_map.items()})
    dash = _strip_readonly(_substitute(dash, repl))
    dash.update(name=f"{slug}_dashboard", label=dash_label, workspaceIdOrApiName=ws_api)
    for w in roles.get("remove", []):
        remove_widget(dash, w)
    widgets = dash["widgets"]
    order = [w["name"] for l in dash.get("layouts", []) for p in l.get("pages", []) for w in p.get("widgets", [])]
    order += [n for n in widgets if n not in order]

    # Metric tiles: each source metric -> the demo's metric in order of first appearance
    seen = []
    for n in order:
        w = widgets.get(n)
        if not w or w.get("type") != "metric":
            continue
        src = (w.get("source") or {}).get("name")
        if src not in seen:
            seen.append(src)
        w["source"] = {"name": _pick(target["metrics"], seen.index(src))}
        mo = w.setdefault("parameters", {}).setdefault("metricOption", {})
        mo.update(sdmApiName=sdm_api, sdmId=sdm_id)
    # Static KPI text (the capture's own numbers) -> metric tiles in the same positions
    for i, n in enumerate(roles.get("kpi_text", [])):
        if n in widgets:
            widgets[n] = {"name": n, "type": "metric", "actions": [], "source": {"name": _pick(target["metrics"], i)},
                          "parameters": {"metricOption": {"sdmApiName": sdm_api, "sdmId": sdm_id,
                                                          "layout": copy.deepcopy(_KPI_LAYOUT)}}}
    if roles.get("title"):
        _place_title(dash, roles["title"], target["title"])
    # Section headers repeat the title of the viz below them
    for text_w, viz_w in roles.get("viz_headers", {}).items():
        src = (widgets.get(viz_w, {}).get("source") or {}).get("name")
        if text_w in widgets and src in viz_titles:
            _set_text(widgets[text_w], viz_titles[src])
    # Filters: same role mapping as the vizzes
    for w in widgets.values():
        fo = (w.get("parameters") or {}).get("filterOption")
        if w.get("type") != "filter" or not fo:
            continue
        mapped = _map_role_field({"fieldName": fo.get("fieldName"), "objectName": fo.get("objectName")}, roles, target, do_api)
        fo["fieldName"] = mapped["fieldName"]
        if mapped.get("objectName"):
            fo["objectName"] = mapped["objectName"]
        else:
            fo.pop("objectName", None)
        w["label"] = next((d["label"] for d in target["dims"] if d["field"] == mapped["fieldName"]), "Date")
        w["source"] = {"name": sdm_api}
    for l in dash.get("layouts", []):
        for p in l.get("pages", []):
            p["label"] = roles.get("pages", {}).get(p.get("label"), p.get("label"))
    dash["widgets"] = {n: _clean_widget_for_post(w) for n, w in widgets.items()}
    return dash


def deploy_template(
    *,
    template_name: str,
    sf_token: str,
    sf_instance: str,
    sdm_api: str,
    sdm_label: str,
    sdm_id: str,
    ws_api: str,
    ws_label: str,
    ws_id: str,
    slug: str,
    dash_label: str,
    metric_apis: List[str],
    filter_fields: List[Dict[str, str]],
    title_text: Optional[str] = None,
    detail_header: Optional[str] = None,
    field_map: Optional[Dict[str, str]] = None,
    label_map: Optional[Dict[str, str]] = None,
    detail_headers: Optional[List[str]] = None,
    do_api: str = "",
    api_version: str = "v66.0",
    percent_fields: Optional[List[str]] = None,
    donut_as_bar: bool = False,
    trend_include_zero: bool = False,
    color_bars: bool = True,
    table_measures: Optional[List[Dict[str, Any]]] = None,
    role_target: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Deploy a complete template dashboard to an org via REST API.

    Creates all vizzes then the dashboard in a single flow.
    Returns a dict with created asset names and IDs.

    Args:
        template_name: "z_layout" or "f_layout"
        sf_token: Valid Salesforce access token
        sf_instance: Salesforce instance URL
        sdm_api, sdm_label, sdm_id: Target SDM identifiers
        ws_api, ws_label, ws_id: Target workspace identifiers
        slug: Demo slug for naming assets
        dash_label: Dashboard display label
        metric_apis: Ordered list of metric _mtc apiNames
        filter_fields: List of filter field dicts
        title_text: Optional hero title override
        detail_header: Optional detail section header override
        field_map: Optional field name remapping
        label_map: Optional text substitutions for viz titles and dashboard text
        detail_headers: Optional chart section headers [text_6, text_7, text_8]
        api_version: Salesforce API version
        percent_fields, donut_as_bar, trend_include_zero, color_bars, table_measures:
            story-driven styling, see prepare_viz_payloads()
    """
    package = load_template(template_name)
    roles = AVAILABLE_TEMPLATES[template_name].get("roles")
    if roles:
        if not role_target:
            raise ValueError(f"{template_name} is remapped by role and needs role_target")
        return _deploy_role_template(package, roles, role_target, template_name=template_name, sf_token=sf_token,
                                     sf_instance=sf_instance, sdm_api=sdm_api, sdm_label=sdm_label, sdm_id=sdm_id,
                                     ws_api=ws_api, ws_label=ws_label, do_api=do_api, slug=slug, dash_label=dash_label,
                                     color_bars=color_bars)
    headers = {
        "Authorization": f"Bearer {sf_token}",
        "Content-Type": "application/json",
    }
    viz_base = f"{sf_instance}/services/data/{api_version}/tableau/visualizations?minorVersion=12"
    dash_base = f"{sf_instance}/services/data/{api_version}/tableau/dashboards?minorVersion=12"

    results = {
        "template": template_name,
        "vizzes_created": {},
        "dashboard": None,
        "errors": [],
    }

    # Step 1: Create vizzes
    viz_payloads = prepare_viz_payloads(
        package,
        sdm_api=sdm_api, sdm_label=sdm_label, sdm_id=sdm_id,
        ws_api=ws_api, ws_label=ws_label, ws_id=ws_id,
        do_api=do_api, slug=slug, field_map=field_map, label_map=label_map,
        percent_fields=percent_fields, donut_as_bar=donut_as_bar,
        trend_include_zero=trend_include_zero, color_bars=color_bars,
        table_measures=table_measures,
    )

    # Table-layout vizzes (fit-to-width tables) need v67.0 — v66.0 rejects their
    # "groups" key ("setterless property 'groups'")
    table_viz_base = f"{sf_instance}/services/data/v67.0/tableau/visualizations?minorVersion=14"

    viz_name_map = {}
    for template_viz_name, payload in viz_payloads.items():
        target_name = payload["name"]
        print(f"  Creating viz: {payload['label']} ({target_name})...")
        is_table_layout = payload.get("visualSpecification", {}).get("layout") == "Table"
        r = requests.post(table_viz_base if is_table_layout else viz_base, headers=headers, json=payload)
        if r.status_code == 201:
            resp = r.json()
            created_name = resp.get("name", target_name)
            viz_name_map[template_viz_name] = created_name
            results["vizzes_created"][template_viz_name] = {
                "name": created_name,
                "id": resp.get("id", ""),
                "label": resp.get("label", payload["label"]),
            }
            print(f"    Created: {created_name} (id={resp.get('id', '?')})")
        else:
            err = f"Failed to create viz {template_viz_name}: {r.status_code} {r.text[:200]}"
            results["errors"].append(err)
            print(f"    ERROR: {err}")

    # Step 2: Create dashboard
    if viz_name_map:
        dash_payload = prepare_dashboard_payload(
            package,
            sdm_api=sdm_api, sdm_id=sdm_id, ws_api=ws_api,
            slug=slug, dash_label=dash_label,
            metric_apis=metric_apis,
            viz_name_map=viz_name_map,
            filter_fields=filter_fields,
            title_text=title_text,
            detail_header=detail_header,
            label_map=label_map,
            detail_headers=detail_headers,
        )

        print(f"  Creating dashboard: {dash_label}...")
        # A dashboard holding a Table-layout viz must be posted on v67.0 too —
        # v66.0 fails with "Can't display visualization because it uses features…"
        has_table_layout = any(p.get("visualSpecification", {}).get("layout") == "Table" for p in viz_payloads.values())
        dash_url = f"{sf_instance}/services/data/v67.0/tableau/dashboards?minorVersion=14" if has_table_layout else dash_base
        r = requests.post(dash_url, headers=headers, json=dash_payload)
        if r.status_code == 201:
            resp = r.json()
            results["dashboard"] = {
                "name": resp.get("name", dash_payload["name"]),
                "id": resp.get("id", ""),
                "label": resp.get("label", dash_label),
            }
            print(f"    Created: {resp.get('name', '?')} (id={resp.get('id', '?')})")
        else:
            err = f"Failed to create dashboard: {r.status_code} {r.text[:300]}"
            results["errors"].append(err)
            print(f"    ERROR: {err}")

    return results


def _deploy_role_template(package, roles, target, *, template_name, sf_token, sf_instance, sdm_api, sdm_label, sdm_id,
                          ws_api, ws_label, do_api, slug, dash_label, color_bars=True):
    """Deploy a captured template remapped by role. Posted on v67.0 / minorVersion 14: the captures
    carry newer keys (e.g. textDirection) that v66.0 rejects."""
    headers = {"Authorization": f"Bearer {sf_token}", "Content-Type": "application/json"}
    base = f"{sf_instance}/services/data/v67.0/tableau"
    results = {"template": template_name, "vizzes_created": {}, "dashboard": None, "errors": []}
    payloads = prepare_role_viz_payloads(package, roles, target, sdm_api=sdm_api, sdm_label=sdm_label, ws_api=ws_api,
                                         ws_label=ws_label, do_api=do_api, slug=slug, color_bars=color_bars)
    viz_name_map, viz_titles = {}, {}
    for name, p in payloads.items():
        print(f"  Creating viz: {p['label']} ({p['name']})...")
        r = requests.post(f"{base}/visualizations?minorVersion=14", headers=headers, json=p)
        if r.status_code == 201:
            created = r.json().get("name", p["name"])
            viz_name_map[name] = created
            viz_titles[created] = p["label"]
            results["vizzes_created"][name] = {"name": created, "id": r.json().get("id", ""), "label": p["label"]}
        else:
            results["errors"].append(f"Failed to create viz {name}: {r.status_code} {r.text[:200]}")
            print(f"    ERROR: {results['errors'][-1]}")
    if len(viz_name_map) == len(payloads):
        dash = prepare_role_dashboard_payload(package, roles, target, sdm_api=sdm_api, sdm_id=sdm_id, ws_api=ws_api,
                                              do_api=do_api, slug=slug, dash_label=dash_label,
                                              viz_name_map=viz_name_map, viz_titles=viz_titles)
        print(f"  Creating dashboard: {dash_label}...")
        r = requests.post(f"{base}/dashboards?minorVersion=14", headers=headers, json=dash)
        if r.status_code == 201:
            results["dashboard"] = {"name": r.json().get("name", dash["name"]), "id": r.json().get("id", ""), "label": dash_label}
        else:
            results["errors"].append(f"Failed to create dashboard: {r.status_code} {r.text[:300]}")
            print(f"    ERROR: {results['errors'][-1]}")
    return results
