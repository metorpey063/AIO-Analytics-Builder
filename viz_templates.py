"""Visualization template definitions and chart type recommendation.

Templates define the structure of each chart type. The viz_builder module
uses these to produce complete API payloads.
"""

from typing import Any, Dict, List, Optional

TEMPLATES: Dict[str, Dict[str, Any]] = {
    "trend_over_time": {
        "description": "Line chart showing measure trend over time with Year+Month hierarchy",
        "chart_type": "line",
        "mark_type": "Line",
        "required_fields": {
            "date": {"role": "Dimension"},
            "measure": {"role": "Measure"},
        },
        "optional_fields": {
            "color_dim": {"role": "Dimension"},
        },
        "use_date_hierarchy": True,
        "fit": "Entire",
        "stacked": False,
    },

    "multi_series_line": {
        "description": "Multi-series line chart comparing trends across categories",
        "chart_type": "line",
        "mark_type": "Line",
        "required_fields": {
            "date": {"role": "Dimension"},
            "measure": {"role": "Measure"},
            "color_dim": {"role": "Dimension"},
        },
        "use_date_hierarchy": True,
        "fit": "Entire",
        "stacked": False,
    },

    "bar_by_category": {
        "description": "Bar chart showing measure by category, sorted descending",
        "chart_type": "bar",
        "mark_type": "Bar",
        "required_fields": {
            "category": {"role": "Dimension"},
            "amount": {"role": "Measure"},
        },
        "optional_fields": {
            "color_dim": {"role": "Dimension"},
        },
        "sort_descending": True,
        "fit": "Entire",
        "stacked": True,
    },

    "stacked_bar": {
        "description": "Stacked bar chart showing part-to-whole breakdown",
        "chart_type": "bar",
        "mark_type": "Bar",
        "required_fields": {
            "category": {"role": "Dimension"},
            "stack_dim": {"role": "Dimension"},
            "amount": {"role": "Measure"},
        },
        "sort_descending": False,
        "fit": "Entire",
        "stacked": True,
    },

    "horizontal_bar": {
        "description": "Horizontal bar chart (measure on columns, dimension on rows)",
        "chart_type": "bar",
        "mark_type": "Bar",
        "required_fields": {
            "category": {"role": "Dimension"},
            "amount": {"role": "Measure"},
        },
        "horizontal": True,
        "sort_descending": True,
        "fit": "Entire",
        "stacked": True,
    },

    "donut": {
        "description": "Donut chart showing distribution by category",
        "chart_type": "donut",
        "mark_type": "Donut",
        "required_fields": {
            "category": {"role": "Dimension"},
            "amount": {"role": "Measure"},
        },
        "fit": "Entire",
        "stacked": False,
    },

    "scatter": {
        "description": "Scatter plot showing relationship between two measures",
        "chart_type": "scatter",
        "mark_type": "Circle",
        "required_fields": {
            "x_measure": {"role": "Measure"},
            "y_measure": {"role": "Measure"},
        },
        "optional_fields": {
            "category": {"role": "Dimension"},
        },
        "fit": "Standard",
        "stacked": False,
    },

    "heatmap": {
        "description": "Heatmap showing two dimensions with color-encoded measure",
        "chart_type": "heatmap",
        "mark_type": "Square",
        "required_fields": {
            "row_dim": {"role": "Dimension"},
            "col_dim": {"role": "Dimension"},
            "measure": {"role": "Measure"},
        },
        "fit": "Entire",
        "stacked": False,
    },

    "funnel": {
        "description": "Funnel chart showing stages with decreasing values",
        "chart_type": "funnel",
        "mark_type": "Bar",
        "required_fields": {
            "stage": {"role": "Dimension"},
            "count": {"role": "Measure"},
        },
        "sort_descending": True,
        "fit": "Entire",
        "stacked": True,
        "is_funnel": True,
    },
}


def recommend_chart_type(metric_config: Dict[str, Any]) -> str:
    """Recommend a template name based on metric configuration.

    Uses heuristics from the metric's aggregation type, field name patterns,
    and whether supporting dimensions are available.
    """
    agg = metric_config.get("agg", "").lower()
    field = metric_config.get("field", "").lower()
    has_category = bool(metric_config.get("category_field"))

    if "rate" in field or "percent" in field or "ratio" in field or agg == "average":
        return "trend_over_time"

    if has_category and agg == "sum":
        return "stacked_bar"

    if agg == "sum":
        return "bar_by_category"

    return "trend_over_time"


def recommend_dashboard_vizzes(metric_configs: List[Dict[str, Any]], dimensions: List[str]) -> List[Dict[str, Any]]:
    """Recommend a set of visualizations for a dashboard.

    Returns a list of viz specs with template name, title, and field assignments.
    Ensures chart type diversity.
    """
    recommendations = []
    used_types = set()

    for i, mc in enumerate(metric_configs[:6]):
        template = recommend_chart_type(mc)

        if template in used_types and len(metric_configs) > 2:
            if "stacked_bar" not in used_types and dimensions:
                template = "stacked_bar"
            elif "bar_by_category" not in used_types:
                template = "bar_by_category"
            elif "donut" not in used_types and dimensions:
                template = "donut"

        used_types.add(template)
        recommendations.append({
            "template": template,
            "label": mc.get("label", f"Metric {i+1}"),
            "metric_field": mc.get("field"),
            "metric_config": mc,
        })

    return recommendations


def list_templates() -> List[str]:
    return list(TEMPLATES.keys())


def get_template(name: str) -> Optional[Dict[str, Any]]:
    return TEMPLATES.get(name)
