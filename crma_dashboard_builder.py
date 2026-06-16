"""CRM Analytics dashboard builder.

Builds a complete dashboard state JSON with SAQL steps, chart widgets,
text headers, filter widgets, and grid layout. Designed to match brand
colors and produce a demo-ready dashboard in one API call.
"""

import json
import uuid
from typing import Any, Dict, List, Optional

import requests


# Chart type mapping from our template system to CRMA visualizationType
CHART_TYPE_MAP = {
    "trend_over_time": "time",
    "multi_series_line": "time",
    "bar_by_category": "hbar",
    "stacked_bar": "bar",
    "horizontal_bar": "hbar",
    "donut": "donut",
    "scatter": "scatter",
    "heatmap": "matrix",
    "funnel": "hbar",
}


def _uid() -> str:
    return str(uuid.uuid4())


def _is_dark(hex_color: str) -> bool:
    """Check if a hex color is dark (luminance < 50%)."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return True
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return luminance < 0.5


def _text_widget(text: str, color: str = "#FFFFFF", size: str = "24px", align: str = "left", bold: bool = True) -> dict:
    attrs = {"color": color, "size": size}
    if bold:
        attrs["bold"] = True
    return {
        "parameters": {
            "content": {
                "richTextContent": [
                    {"attributes": attrs, "insert": text},
                    {"attributes": {"align": align}, "insert": "\n"},
                ]
            },
            "showActionMenu": False,
        },
        "type": "text",
    }


def _number_widget(step_name: str, measure_field: str, label: str, compact: bool = True) -> dict:
    return {
        "parameters": {
            "step": step_name,
            "measureField": measure_field,
            "compact": compact,
        },
        "type": "number",
    }


def _chart_widget(step_name: str, viz_type: str, theme: str = "dark", **kwargs) -> dict:
    params = {
        "step": step_name,
        "visualizationType": viz_type,
        "theme": theme,
        "autoFitMode": "keepLabels",
    }
    if viz_type == "line":
        params["showPoints"] = True
    params.update(kwargs)
    return {"parameters": params, "type": "chart"}


def _listselector_widget(step_name: str, display_mode: str = "dropdown") -> dict:
    return {
        "parameters": {
            "step": step_name,
            "instant": True,
            "expanded": display_mode == "list",
        },
        "type": "listselector",
    }


def _container_widget(bg_color: str = "#1a1a1a") -> dict:
    return {
        "parameters": {
            "alignmentX": "left",
            "alignmentY": "top",
            "fit": "original",
        },
        "type": "container",
    }


def build_saql_step(
    dataset_name: str,
    measure_field: str,
    aggregation: str = "avg",
    group_by: Optional[List[str]] = None,
    time_field: str = "date",
    time_grain: str = "month",
    limit: int = 2000,
    filters: Optional[List[str]] = None,
) -> dict:
    """Build a SAQL query step for a metric.

    Args:
        dataset_name: Name of the CRMA dataset
        measure_field: Field to aggregate
        aggregation: "avg", "sum", "count", "min", "max"
        group_by: Dimension fields to group by (None = time series)
        time_field: Date field name
        time_grain: "month", "week", "quarter", "year"
        limit: Max rows
        filters: Optional list of SAQL filter expressions
    """
    lines = [f'q = load "{dataset_name}";']

    if filters:
        for f in filters:
            lines.append(f"q = filter q by {f};")

    if group_by:
        cols = ", ".join(f"'{c}'" for c in group_by)
        lines.append(f"q = group q by ({cols});")
        gen_cols = ", ".join(f"'{c}'" for c in group_by)
        lines.append(f"q = foreach q generate {gen_cols}, {aggregation}('{measure_field}') as 'value';")
        lines.append("q = order q by 'value' desc;")
    else:
        lines.append(f"q = group q by ('{time_field}_Year', '{time_field}_Month');")
        lines.append(f"q = foreach q generate '{time_field}_Year' as '{time_field}_Year', '{time_field}_Month' as '{time_field}_Month', {aggregation}('{measure_field}') as 'value';")
        lines.append(f"q = order q by ('{time_field}_Year' asc, '{time_field}_Month' asc);")

    lines.append(f"q = limit q {limit};")
    query = "\n".join(lines)

    step = {
        "broadcastFacet": True,
        "groups": [],
        "numbers": [],
        "query": query,
        "receiveFacetSource": {"mode": "all", "steps": []},
        "selectMode": "none",
        "strings": [],
        "type": "saql",
        "useGlobal": True,
    }
    return step


def build_filter_step(dataset_name: str, dimension_field: str) -> dict:
    """Build a SAQL step for a dimension filter (listselector)."""
    query = (
        f'q = load "{dataset_name}";\n'
        f"q = group q by '{dimension_field}';\n"
        f"q = foreach q generate '{dimension_field}' as '{dimension_field}', count() as 'count';\n"
        f"q = order q by '{dimension_field}' asc;\n"
        f"q = limit q 200;"
    )
    return {
        "broadcastFacet": True,
        "groups": [dimension_field],
        "numbers": [],
        "query": query,
        "receiveFacetSource": {"mode": "all", "steps": []},
        "selectMode": "multi",
        "strings": [dimension_field],
        "type": "saql",
        "useGlobal": True,
    }


def build_kpi_step(dataset_name: str, measure_field: str, aggregation: str = "avg") -> dict:
    """Build a SAQL step for a single KPI number."""
    query = (
        f'q = load "{dataset_name}";\n'
        f"q = group q by all;\n"
        f"q = foreach q generate {aggregation}('{measure_field}') as 'value';\n"
    )
    return {
        "broadcastFacet": False,
        "groups": [],
        "numbers": ["value"],
        "query": query,
        "receiveFacetSource": {"mode": "all", "steps": []},
        "selectMode": "none",
        "strings": [],
        "type": "saql",
        "useGlobal": True,
    }


def build_dashboard_state(
    *,
    dataset_name: str,
    dashboard_label: str,
    metric_configs: List[Dict[str, Any]],
    dimensions: List[str],
    time_field: str = "date",
    time_grain: str = "week",
    brand: Optional[Dict[str, str]] = None,
    max_kpis: int = 5,
    max_charts: int = 4,
    max_filters: int = 2,
) -> dict:
    """Build a complete CRMA dashboard state using the golden template pattern.

    Uses aggregateflex steps (visually editable in the UI), 10-column grid,
    dark theme, and the exact widget styling from the tested template.

    Args:
        dataset_name: CRMA dataset API name
        dashboard_label: Dashboard display title
        metric_configs: List of METRIC_CONFIG dicts
        dimensions: Dimension field names for filters/grouping
        time_field: Date field name in the dataset
        time_grain: "week", "month", "quarter"
        brand: Brand color dict (primary, secondary, chart_bg, text)
        max_kpis: Max KPI number widgets (default 5)
        max_charts: Max chart widgets (default 4, arranged 2x2)
        max_filters: Max filter dropdowns (default 2)

    Returns:
        Complete dashboard state dict ready for POST
    """
    brand = brand or {"primary": "#032D60", "secondary": "#1B5297", "chart_bg": "#16325C", "text": "#FFFFFF"}
    bg_color = brand.get("dashboard_bg", brand.get("primary", "#032D60"))

    steps = {}
    widgets = {}
    page_widgets = []

    # ── Helper: aggregateflex step for charts/filters ─────────────────────────
    def _agg_step(measures, groups, label):
        query_obj = json.dumps({"measures": measures, "groups": groups, "filters": []})
        return {
            "broadcastFacet": True,
            "datasets": [{"name": dataset_name}],
            "isGlobal": False,
            "label": label,
            "query": {"query": query_obj, "version": -1.0},
            "receiveFacetSource": {"mode": "all", "steps": []},
            "selectMode": "single",
            "type": "aggregateflex",
            "useGlobal": True,
        }

    # ── Helper: lens step for KPI numbers ─────────────────────────────────────
    def _kpi_step(agg, field, label):
        return {
            "broadcastFacet": False,
            "datasets": [{"name": dataset_name}],
            "isGlobal": False,
            "label": label,
            "query": {
                "aggregateFilters": [], "columnGroups": [], "columnTotals": [],
                "limit": 2000, "orders": [], "rowTotals": [], "sourceFilters": {},
                "sources": [{
                    "columns": [{"field": [agg, field], "name": "A"}],
                    "filters": [], "groups": ["all"], "joins": [], "name": dataset_name,
                }],
            },
            "receiveFacetSource": {"mode": "all", "steps": []},
            "selectMode": "none",
            "type": "aggregateflex",
            "useGlobal": True,
        }

    # ── Row 0: Title + Date selector + Filters ────────────────────────────────
    widgets["title"] = _text_widget(dashboard_label, color="#FFFFFF", size="20px", bold=True)
    page_widgets.append({"name": "title", "row": 0, "column": 0, "colspan": 4, "rowspan": 3})

    # Date selector
    steps["date_1"] = {
        "broadcastFacet": True,
        "datasets": [{"name": dataset_name}],
        "isGlobal": False,
        "label": "",
        "query": {"query": json.dumps({"measures": [["count", "*"]], "groups": [time_field]}), "version": -1.0},
        "receiveFacetSource": {"mode": "all", "steps": []},
        "selectMode": "single",
        "type": "aggregateflex",
        "useGlobal": True,
    }
    widgets["dateselector_1"] = {
        "parameters": {
            "absoluteModeEnabled": True,
            "calendarTypeSwitchingAllowed": True,
            "defaultFiscalMode": False,
            "displayMode": "filter",
            "filterStyle": {"titleColor": "#FFFFFF", "valueColor": "#FFFFFF"},
            "instant": False,
            "presetsEnabled": True,
            "relativeModeEnabled": True,
            "showActionMenu": True,
            "step": "date_1",
            "title": "Date",
        },
        "type": "dateselector",
    }
    page_widgets.append({"name": "dateselector_1", "row": 0, "column": 4, "colspan": 2, "rowspan": 3})

    # Dimension filters
    filter_dims = dimensions[:max_filters]
    for i, dim in enumerate(filter_dims):
        step_name = f"filter_{dim}"
        steps[step_name] = _agg_step([["count", "*"]], [[dim]], dim.replace("_", " ").title())
        steps[step_name]["selectMode"] = "multi"
        widget_name = f"w_filter_{dim}"
        widgets[widget_name] = {"parameters": {"step": step_name, "instant": True, "expanded": False, "filterStyle": {}}, "type": "listselector"}
        page_widgets.append({"name": widget_name, "row": 0, "column": 6 + (i * 2), "colspan": 2, "rowspan": 3})

    # ── Row 3: KPI number widgets ─────────────────────────────────────────────
    kpi_metrics = metric_configs[:max_kpis]
    kpi_colspan = 10 // max(len(kpi_metrics), 1)
    for i, mc in enumerate(kpi_metrics):
        agg = "avg" if mc.get("agg") == "Average" else "sum"
        step_name = f"lens_{i+1}"
        steps[step_name] = _kpi_step(agg, mc["field"], mc["label"])
        widget_name = f"number_{i+1}"
        widgets[widget_name] = {
            "parameters": {
                "compact": False,
                "exploreLink": True,
                "measureField": "A",
                "numberColor": "#FFFFFF",
                "numberSize": 32,
                "showActionMenu": True,
                "step": step_name,
                "textAlignment": "center",
                "title": mc["label"].split()[0] if len(mc["label"]) > 15 else mc["label"],
                "titleColor": "#FFFFFF",
                "titleSize": 20,
            },
            "type": "number",
        }
        page_widgets.append({"name": widget_name, "row": 3, "column": i * kpi_colspan, "colspan": kpi_colspan, "rowspan": 6})

    # ── Row 10+: Charts (2x2 grid) ───────────────────────────────────────────
    chart_metrics = metric_configs[:max_charts]
    row = 10
    for i, mc in enumerate(chart_metrics):
        agg = "avg" if mc.get("agg") == "Average" else "sum"
        col = (i % 2) * 5

        if i % 2 == 0:
            # Line chart (time trend)
            step_name = f"trend_{mc['field']}"
            groups = [[f"{time_field}_Year", f"{time_field}_Month"]]
            if dimensions:
                groups.append(dimensions[0])
            steps[step_name] = _agg_step([[agg, mc["field"]]], groups, f"{mc['label']} Trend")
            viz_type = "line"
        else:
            # Horizontal bar (by dimension)
            step_name = f"bar_{mc['field']}"
            dim = dimensions[i % len(dimensions)] if dimensions else "region"
            steps[step_name] = _agg_step([[agg, mc["field"]]], [[dim]], f"{mc['label']} by {dim.replace('_', ' ').title()}")
            viz_type = "hbar"

        widget_name = f"chart_{i}"
        widgets[widget_name] = {
            "parameters": {
                "autoFitMode": "keepLabels",
                "exploreLink": True,
                "legend": {"descOrder": False, "show": True, "showHeader": False, "customSize": "auto", "position": "bottom-center", "inside": False},
                "step": step_name,
                "theme": "dark",
                "title": {"fontSize": 14, "subtitleFontSize": 11, "label": mc["label"]},
                "visualizationType": viz_type,
            },
            "type": "chart",
        }
        page_widgets.append({"name": widget_name, "row": row, "column": col, "colspan": 5, "rowspan": 14})

        if i % 2 == 1:
            row += 15

    state = {
        "dataSourceLinksInfo": {"enableAutomaticLinking": True, "excludeRelationships": [], "links": []},
        "steps": steps,
        "widgets": widgets,
        "gridLayouts": [
            {
                "name": "default",
                "numColumns": 10,
                "rowHeight": "fine",
                "maxWidth": 1200,
                "pages": [
                    {
                        "label": "Overview",
                        "name": "page1",
                        "widgets": page_widgets,
                    }
                ],
                "selectors": [],
                "style": {
                    "alignmentX": "left",
                    "alignmentY": "top",
                    "backgroundColor": bg_color,
                    "cellSpacingX": 8,
                    "cellSpacingY": 8,
                    "fit": "original",
                    "gutterColor": bg_color,
                },
                "version": 1,
            }
        ],
        "filters": [],
        "widgetStyle": {"backgroundColor": "#16325C", "borderColor": "#747474", "borderEdges": [], "borderRadius": 0, "borderWidth": 1},
    }

    return state


def create_dashboard(
    sf_instance: str,
    sf_token: str,
    dashboard_label: str,
    state: dict,
    app_id: Optional[str] = None,
    description: str = "",
) -> Optional[str]:
    """Create a new CRMA dashboard via the Wave API.

    Args:
        sf_instance: Salesforce instance URL
        sf_token: Bearer token
        dashboard_label: Display name
        state: Dashboard state from build_dashboard_state()
        app_id: Optional CRMA app/folder ID to place the dashboard in
        description: Optional description

    Returns:
        Dashboard ID if created, None on failure
    """
    headers = {"Authorization": f"Bearer {sf_token}", "Content-Type": "application/json"}
    api_base = f"{sf_instance}/services/data/v61.0"

    payload = {
        "label": dashboard_label,
        "state": state,
        "description": description,
    }
    if app_id:
        payload["folder"] = {"id": app_id}

    r = requests.post(f"{api_base}/wave/dashboards", headers=headers, json=payload)
    if r.status_code in (200, 201):
        dash_id = r.json().get("id")
        print(f"  CRMA dashboard created: {dash_id}")
        return dash_id
    else:
        print(f"  CRMA dashboard FAILED ({r.status_code}): {r.text[:400]}")
        return None


def find_or_create_app(
    sf_instance: str,
    sf_token: str,
    app_label: str,
) -> Optional[str]:
    """Find an existing CRMA app by label, or create one.

    Returns the app/folder ID.
    """
    headers = {"Authorization": f"Bearer {sf_token}", "Content-Type": "application/json"}
    api_base = f"{sf_instance}/services/data/v61.0"

    r = requests.get(f"{api_base}/wave/folders", headers=headers, params={"q": app_label})
    if r.status_code == 200:
        for folder in r.json().get("folders", []):
            if folder.get("label") == app_label:
                return folder["id"]

    r = requests.post(f"{api_base}/wave/folders", headers=headers, json={"label": app_label})
    if r.status_code in (200, 201):
        return r.json().get("id")
    return None


# ═══════════════════════════════════════════════════════════════════════════════
# Template-Based Dashboard Creation (recommended — uses CRMA Smart Templates)
# ═══════════════════════════════════════════════════════════════════════════════

CRMA_TEMPLATES = {
    "metrics_trend": {
        "id": "sfdc_internal__MetricsTrendDashboard",
        "label": "Metrics Trend",
        "description": "Time-series charts showing how metrics change over time with filters (recommended)",
        "api_reliable": True,
    },
    "details": {
        "id": "sfdc_internal__Details_Dashboard",
        "label": "Details Dashboard",
        "description": "Charts + record-level details table with KPIs in sidebar",
        "api_reliable": True,
    },
    "summary": {
        "id": "sfdc_internal__Summary_Dashboard",
        "label": "Summary Dashboard",
        "description": "Horizontal sections with filters across the top",
        "api_reliable": True,
    },
    "three_column": {
        "id": "sfdc_internal__Three_Column_Dashboard",
        "label": "Three-Column Dashboard",
        "description": "Three columns with filters across the top",
        "api_reliable": True,
    },
    "table_expansion": {
        "id": "sfdc_internal__TableExpansionDashboard",
        "label": "Table Expansion",
        "description": "Metrics over time with expandable details table",
        "api_reliable": True,
    },
    "comparison": {
        "id": "sfdc_internal__Comparison_Dashboard",
        "label": "Comparison Dashboard",
        "description": "Compare metrics side-by-side, across a single dimension",
        "api_reliable": True,
    },
    "performance_summary": {
        "id": "sfdc_internal__PerfSummaryDashboard",
        "label": "Performance Summary",
        "description": "Side-by-side comparison (limited: single measure, 2 groupings, labels may not resolve)",
        "api_reliable": False,
    },
    "time_series": {
        "id": "sfdc_internal__TimeSeriesDashboard",
        "label": "Time Series",
        "description": "Forecasting/projections (requires complex Overrides variable — may need UI wizard)",
        "api_reliable": False,
    },
}


def list_crma_templates() -> List[Dict[str, str]]:
    """List available CRMA dashboard templates with descriptions."""
    return [
        {"key": k, "label": v["label"], "description": v["description"]}
        for k, v in CRMA_TEMPLATES.items()
    ]


def create_dashboard_from_template(
    sf_instance: str,
    sf_token: str,
    *,
    template_key: str,
    app_label: str,
    dataset_id: str,
    dataset_name: str,
    measure_fields: List[str],
    date_field: str,
    filter_fields: List[str],
) -> Optional[Dict[str, str]]:
    """Create a CRMA dashboard from a Smart Template.

    This is the recommended approach — produces polished, professional
    dashboards using Salesforce's built-in templates.

    Automatically discovers the template's variable schema and maps
    our standard inputs to the correct variable names.

    Args:
        sf_instance: Salesforce instance URL
        sf_token: Bearer token
        template_key: Key from CRMA_TEMPLATES (e.g. "metrics_trend")
        app_label: Label for the app/folder that will contain the dashboard
        dataset_id: CRMA dataset ID (0Fb...)
        dataset_name: Dataset API name
        measure_fields: List of numeric field names to visualize (max 4)
        date_field: Date field name for time axis
        filter_fields: Dimension field names for filter widgets (max 4)

    Returns:
        Dict with 'app_id', 'dashboard_id', 'dashboard_url' or None on failure
    """
    template = CRMA_TEMPLATES.get(template_key)
    if not template:
        print(f"  Unknown template: {template_key}. Available: {list(CRMA_TEMPLATES.keys())}")
        return None

    headers = {"Authorization": f"Bearer {sf_token}", "Content-Type": "application/json"}
    api_base = f"{sf_instance}/services/data/v61.0"

    # Discover variable schema for this template
    r = requests.get(f"{api_base}/wave/templates/{template['id']}/configuration", headers=headers)
    if r.status_code != 200:
        print(f"  Could not get template config ({r.status_code})")
        return None

    variables = r.json().get("variables", {})
    template_values = {}

    for var_name, var_def in variables.items():
        vtype = var_def.get("variableType", {}).get("type", "")
        required = var_def.get("required", False)

        if vtype == "DatasetType":
            template_values[var_name] = {"datasetId": dataset_id, "datasetAlias": dataset_name}
        elif vtype == "DatasetDateType":
            template_values[var_name] = {"datasetId": dataset_id, "dateAlias": date_field}
        elif vtype == "DatasetMeasureType":
            if measure_fields:
                template_values[var_name] = {"datasetId": dataset_id, "fieldName": measure_fields[0]}
        elif vtype == "ArrayType":
            items_type = var_def.get("variableType", {}).get("itemsType", {}).get("type", "")
            size_limit = var_def.get("variableType", {}).get("sizeLimit", {})
            max_items = size_limit.get("max", 4)

            if items_type == "DatasetMeasureType":
                template_values[var_name] = [
                    {"datasetId": dataset_id, "fieldName": f} for f in measure_fields[:max_items]
                ]
            elif items_type == "DatasetDimensionType":
                template_values[var_name] = [
                    {"datasetId": dataset_id, "fieldName": f} for f in filter_fields[:max_items]
                ]
            elif items_type == "ObjectType" or not items_type:
                # Generic groupings — try dimensions
                template_values[var_name] = [
                    {"datasetId": dataset_id, "fieldName": f} for f in filter_fields[:max_items]
                ]
        elif vtype == "BooleanType":
            template_values[var_name] = True
        elif vtype == "ObjectType" and not required:
            pass  # Skip optional complex objects

    payload = {
        "label": app_label,
        "templateSourceId": template["id"],
        "templateValues": template_values,
    }

    r = requests.post(f"{api_base}/wave/folders", headers=headers, json=payload)
    if r.status_code not in (200, 201):
        print(f"  Template creation FAILED ({r.status_code}): {r.text[:400]}")
        return None

    folder_id = r.json().get("id")
    print(f"  App created: {folder_id} ({app_label})")

    # Find the dashboard (may take a moment to materialize)
    import time as _time
    for _attempt in range(6):
        r2 = requests.get(f"{api_base}/wave/dashboards", headers=headers, params={"folderId": folder_id})
        if r2.status_code == 200:
            dashboards = r2.json().get("dashboards", [])
            if dashboards:
                dash_id = dashboards[0]["id"]
                dash_url = f"{sf_instance}/analytics/dashboard/{dash_id}"
                print(f"  Dashboard: {dash_id}")
                print(f"  URL: {dash_url}")
                return {"app_id": folder_id, "dashboard_id": dash_id, "dashboard_url": dash_url}
        _time.sleep(3)

    print("  Dashboard not found in folder (may still be generating).")
    return {"app_id": folder_id, "dashboard_id": None, "dashboard_url": None}
