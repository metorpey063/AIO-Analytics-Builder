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
    },
    "pharma_analytics": {
        "file": "pharma_analytics_package.json",
        "label": "Pharma Analytics",
        "description": "4 KPIs → stacked bar trend (YoY) → donut breakdown + horizontal bar ranking",
        "max_metrics": 4,
        "max_filters": 0,
        "viz_slots": ["trend_stacked_bar", "donut_breakdown", "entity_bar", "brand_bar"],
    },
    "multi_page_kpi": {
        "file": "multi_page_kpi_package.json",
        "label": "Multi-Page KPI",
        "description": "4-page tabbed dashboard: Executive KPIs, Sales, Customer & Product, Health & Coaching. 15 metrics, 8 vizzes, navigation.",
        "max_metrics": 15,
        "max_filters": 3,
        "viz_slots": ["8 vizzes across 4 pages"],
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

BAR_VIZZES = {"Horizontal_Bar", "Horizontal_Bar1", "Detail_Bar_2"}


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
    if donut_as_bar and "Donut_Chart" in vizzes and horiz_key:
        donut = vizzes["Donut_Chart"]
        donut_dim = next((fv["fieldName"] for fv in donut.get("fields", {}).values()
                          if fv.get("role") == "Dimension"), None)
        if donut_dim:
            bar = copy.deepcopy(vizzes[horiz_key])
            for fv in bar.get("fields", {}).values():
                if fv.get("role") == "Dimension":
                    fv["fieldName"] = donut_dim
                    break
            bar["label"] = donut.get("label", "Donut Chart")
            bar["name"] = donut.get("name", "Donut_Chart")
            vizzes["Donut_Chart"] = bar

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

        if percent_fields:
            _set_percent_format(payload, set(percent_fields))
        if viz_name == "Trend_Line":
            _month_grain_dates(payload)
        if viz_name == "Details_Table":
            if table_measures:
                _add_table_measures(payload, table_measures)
            # Fit to width: needs the Table layout (a Vizql table only takes
            # "Standard" or "Entire"); deploy_template posts it on v67.0
            _to_table_layout(payload)
        if viz_name == "Trend_Line" and not trend_include_zero:
            axis_fields = payload.get("visualSpecification", {}).get("style", {}).get("axis", {}).get("fields", {})
            for ax in axis_fields.values():
                if "range" in ax:
                    ax["range"]["includeZero"] = False
        if color_bars and (viz_name in BAR_VIZZES or (donut_as_bar and viz_name == "Donut_Chart")):
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
