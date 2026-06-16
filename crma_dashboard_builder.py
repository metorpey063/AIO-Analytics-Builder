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
            "interactions": [],
            "showActionMenu": False,
        },
        "type": "text",
    }


def _number_widget(step_name: str, measure_field: str, label: str, compact: bool = True) -> dict:
    return {
        "parameters": {
            "step": step_name,
            "visualizationType": "number",
            "textAlignment": "left",
            "titleColumn": "",
            "measureField": measure_field,
            "compact": compact,
            "numberColor": "",
            "showActionMenu": True,
            "interactions": [],
        },
        "type": "number",
    }


def _chart_widget(step_name: str, viz_type: str, theme: str = "wave", **kwargs) -> dict:
    params = {
        "step": step_name,
        "visualizationType": viz_type,
        "theme": theme,
        "autoFitMode": "keepLabels",
        "showValues": True,
        "showActionMenu": True,
        "interactions": [],
    }
    if viz_type in ("time", "line"):
        params["fillArea"] = False
        params["showPoints"] = True
    if viz_type == "donut":
        params["legendPosition"] = "right"
    params.update(kwargs)
    return {"parameters": params, "type": "chart"}


def _listselector_widget(step_name: str, display_mode: str = "dropdown") -> dict:
    return {
        "parameters": {
            "step": step_name,
            "instant": True,
            "expanded": display_mode == "list",
            "visualizationType": "list" if display_mode == "list" else "dropdown",
            "interactions": [],
            "showActionMenu": False,
        },
        "type": "listselector",
    }


def _container_widget(bg_color: str = "#1a1a1a") -> dict:
    return {
        "parameters": {
            "alignmentX": "left",
            "alignmentY": "top",
            "fit": "original",
            "interactions": [],
            "backgroundColor": bg_color,
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
