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

    vizzes = package["components"]["visualizations"]
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
    do_api: str = "",
    api_version: str = "v66.0",
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
        api_version: Salesforce API version
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
    )

    viz_name_map = {}
    for template_viz_name, payload in viz_payloads.items():
        target_name = payload["name"]
        print(f"  Creating viz: {payload['label']} ({target_name})...")
        r = requests.post(viz_base, headers=headers, json=payload)
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
        )

        print(f"  Creating dashboard: {dash_label}...")
        r = requests.post(dash_base, headers=headers, json=dash_payload)
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
