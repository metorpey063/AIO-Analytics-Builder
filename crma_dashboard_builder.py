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


def _text_widget(text: str, color: str = "#FFFFFF", size: str = "18px", align: str = "left") -> dict:
    return {
        "parameters": {
            "content": {
                "richTextContent": [
                    {"attributes": {"color": color, "size": size}, "insert": text},
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


def _chart_widget(step_name: str, viz_type: str, **kwargs) -> dict:
    params = {
        "step": step_name,
        "visualizationType": viz_type,
    }
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
        if time_grain == "week":
            lines.append(f"q = group q by ('{time_field}_Year', '{time_field}_Month', '{time_field}_Day');")
            lines.append(f"q = foreach q generate '{time_field}_Year' + \"-\" + '{time_field}_Month' + \"-\" + '{time_field}_Day' as 'date_label', {aggregation}('{measure_field}') as 'value';")
        elif time_grain == "month":
            lines.append(f"q = group q by ('{time_field}_Year', '{time_field}_Month');")
            lines.append(f"q = foreach q generate '{time_field}_Year' + \"-\" + '{time_field}_Month' as 'date_label', {aggregation}('{measure_field}') as 'value';")
        elif time_grain == "quarter":
            lines.append(f"q = group q by ('{time_field}_Year', '{time_field}_Quarter');")
            lines.append(f"q = foreach q generate '{time_field}_Year' + \"-Q\" + '{time_field}_Quarter' as 'date_label', {aggregation}('{measure_field}') as 'value';")
        else:
            lines.append(f"q = group q by '{time_field}_Year';")
            lines.append(f"q = foreach q generate '{time_field}_Year' as 'date_label', {aggregation}('{measure_field}') as 'value';")
        lines.append("q = order q by 'date_label' asc;")

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
    max_charts: int = 6,
    max_filters: int = 3,
) -> dict:
    """Build a complete CRMA dashboard state.

    Args:
        dataset_name: CRMA dataset API name
        dashboard_label: Dashboard display title
        metric_configs: List of METRIC_CONFIG dicts
        dimensions: Dimension field names for filters/grouping
        time_field: Date field name in the dataset
        time_grain: "week", "month", "quarter"
        brand: Brand color dict (primary, secondary, chart_bg, text)
        max_charts: Max number of chart widgets
        max_filters: Max number of filter dropdowns

    Returns:
        Complete dashboard state dict ready for POST/PATCH
    """
    brand = brand or {"primary": "#032D60", "secondary": "#1B5297", "chart_bg": "#FFFFFF", "text": "#2E2E2E"}
    bg_color = brand.get("dashboard_bg", brand.get("primary", "#032D60"))
    text_color = brand.get("text", "#FFFFFF")
    chart_theme = "wave"

    steps = {}
    widgets = {}
    page_widgets = []

    row = 0
    col_count = 50

    # Title
    title_name = "title_text"
    widgets[title_name] = _text_widget(dashboard_label, color=text_color, size="24px")
    page_widgets.append({"name": title_name, "row": row, "column": 0, "colspan": col_count, "rowspan": 4})
    row += 4

    # Filters row
    filter_dims = dimensions[:max_filters]
    filter_colspan = col_count // max(len(filter_dims), 1)
    for i, dim in enumerate(filter_dims):
        step_name = f"filter_{dim}"
        steps[step_name] = build_filter_step(dataset_name, dim)
        widget_name = f"w_filter_{dim}"
        widgets[widget_name] = _listselector_widget(step_name)
        page_widgets.append({"name": widget_name, "row": row, "column": i * filter_colspan, "colspan": filter_colspan, "rowspan": 5})
    row += 6

    # KPI row (top 3 metrics)
    kpi_metrics = metric_configs[:3]
    kpi_colspan = col_count // max(len(kpi_metrics), 1)
    for i, mc in enumerate(kpi_metrics):
        step_name = f"kpi_{mc['field']}"
        agg = "avg" if mc.get("agg") == "Average" else "sum"
        steps[step_name] = build_kpi_step(dataset_name, mc["field"], agg)
        widget_name = f"w_kpi_{i}"
        widgets[widget_name] = _number_widget(step_name, "value", mc["label"])
        page_widgets.append({"name": widget_name, "row": row, "column": i * kpi_colspan, "colspan": kpi_colspan, "rowspan": 8})
    row += 9

    # Chart grid (2 columns)
    chart_metrics = metric_configs[:max_charts]
    chart_colspan = col_count // 2
    chart_rowspan = 20
    col = 0
    for i, mc in enumerate(chart_metrics):
        agg = "avg" if mc.get("agg") == "Average" else "sum"

        # Alternate between time series and grouped bar
        if i % 3 == 0:
            step_name = f"trend_{mc['field']}"
            steps[step_name] = build_saql_step(dataset_name, mc["field"], agg, time_field=time_field, time_grain=time_grain)
            viz_type = "time"
        elif i % 3 == 1 and dimensions:
            step_name = f"bar_{mc['field']}"
            steps[step_name] = build_saql_step(dataset_name, mc["field"], agg, group_by=[dimensions[0]])
            viz_type = "hbar"
        else:
            step_name = f"trend2_{mc['field']}"
            steps[step_name] = build_saql_step(dataset_name, mc["field"], agg, time_field=time_field, time_grain=time_grain)
            viz_type = "time"

        widget_name = f"w_chart_{i}"
        widgets[widget_name] = _chart_widget(step_name, viz_type, theme=chart_theme)
        page_widgets.append({"name": widget_name, "row": row, "column": col, "colspan": chart_colspan, "rowspan": chart_rowspan})

        col += chart_colspan
        if col >= col_count:
            col = 0
            row += chart_rowspan

    # Background container (placed behind everything)
    bg_name = "bg_container"
    widgets[bg_name] = _container_widget(bg_color)
    total_height = row + (chart_rowspan if col > 0 else 0)
    page_widgets.insert(0, {"name": bg_name, "row": 0, "column": 0, "colspan": col_count, "rowspan": total_height})

    state = {
        "steps": steps,
        "widgets": widgets,
        "gridLayouts": [
            {
                "name": _uid(),
                "pages": [
                    {
                        "label": "Overview",
                        "name": _uid(),
                        "widgets": page_widgets,
                    }
                ],
                "selectors": [],
                "style": {
                    "backgroundColor": bg_color,
                    "cellSpacingX": 4,
                    "cellSpacingY": 4,
                    "gutterColor": bg_color,
                },
                "version": 1,
            }
        ],
        "filters": [],
        "widgetStyle": {"backgroundColor": brand.get("chart_bg", "#FFFFFF"), "borderEdges": []},
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
        "description": "Visualize how metrics change over a period of time with customized filters",
        "max_measures": 4,
        "max_filters": 4,
    },
    "performance_summary": {
        "id": "sfdc_internal__PerfSummaryDashboard",
        "label": "Performance Summary",
        "description": "Compare metrics side-by-side, across a single dimension with filters",
        "max_measures": 4,
        "max_filters": 4,
    },
    "comparison": {
        "id": "sfdc_internal__Comparison_Dashboard",
        "label": "Comparison Dashboard",
        "description": "Compare metrics side-by-side, across a single dimension",
        "max_measures": 4,
        "max_filters": 4,
    },
    "details": {
        "id": "sfdc_internal__Details_Dashboard",
        "label": "Details Dashboard",
        "description": "Charts + record-level details table with KPIs in sidebar",
        "max_measures": 4,
        "max_filters": 4,
    },
    "summary": {
        "id": "sfdc_internal__Summary_Dashboard",
        "label": "Summary Dashboard",
        "description": "Horizontal sections with filters across the top",
        "max_measures": 4,
        "max_filters": 4,
    },
    "three_column": {
        "id": "sfdc_internal__Three_Column_Dashboard",
        "label": "Three-Column Dashboard",
        "description": "Three columns with filters across the top",
        "max_measures": 4,
        "max_filters": 4,
    },
    "time_series": {
        "id": "sfdc_internal__TimeSeriesDashboard",
        "label": "Time Series",
        "description": "Future metrics trends based on historical data with forecasting",
        "max_measures": 4,
        "max_filters": 4,
    },
    "table_expansion": {
        "id": "sfdc_internal__TableExpansionDashboard",
        "label": "Table Expansion",
        "description": "Metrics over time with expandable details table",
        "max_measures": 4,
        "max_filters": 4,
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
