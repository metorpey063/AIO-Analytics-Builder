"""Dashboard layout builder for Tableau Next.

Provides layout patterns (grid positions) and assembles complete
dashboard payloads from visualization and metric widget definitions.
"""

import uuid
from typing import Any, Dict, List, Optional

# Layout patterns define widget positions on a 72-column grid.
# Each pattern specifies slots for filters, metrics, and vizzes.

LAYOUT_PATTERNS = {
    "standard": {
        "description": "3 metrics top row, 2x2 viz grid below (our default)",
        "grid_columns": 72,
        "metric_row_height": 15,
        "viz_row_height": 30,
        "slots": {
            "metrics": [
                {"row": 0, "column": 0, "rowspan": 15, "colspan": 24},
                {"row": 0, "column": 24, "rowspan": 15, "colspan": 24},
                {"row": 0, "column": 48, "rowspan": 15, "colspan": 24},
            ],
            "vizzes": [
                {"row": 15, "column": 0, "rowspan": 30, "colspan": 36},
                {"row": 15, "column": 36, "rowspan": 30, "colspan": 36},
                {"row": 45, "column": 0, "rowspan": 30, "colspan": 36},
                {"row": 45, "column": 36, "rowspan": 30, "colspan": 36},
            ],
        },
    },

    "metrics_heavy": {
        "description": "6 metrics in 2 rows, 3 vizzes below",
        "grid_columns": 72,
        "metric_row_height": 15,
        "viz_row_height": 30,
        "slots": {
            "metrics": [
                {"row": 0, "column": 0, "rowspan": 15, "colspan": 24},
                {"row": 0, "column": 24, "rowspan": 15, "colspan": 24},
                {"row": 0, "column": 48, "rowspan": 15, "colspan": 24},
                {"row": 15, "column": 0, "rowspan": 15, "colspan": 24},
                {"row": 15, "column": 24, "rowspan": 15, "colspan": 24},
                {"row": 15, "column": 48, "rowspan": 15, "colspan": 24},
            ],
            "vizzes": [
                {"row": 30, "column": 0, "rowspan": 30, "colspan": 24},
                {"row": 30, "column": 24, "rowspan": 30, "colspan": 24},
                {"row": 30, "column": 48, "rowspan": 30, "colspan": 24},
            ],
        },
    },

    "story_flow": {
        "description": "3 metrics, then vizzes in narrative order (wide top, 2-up bottom)",
        "grid_columns": 72,
        "metric_row_height": 15,
        "viz_row_height": 30,
        "slots": {
            "metrics": [
                {"row": 0, "column": 0, "rowspan": 15, "colspan": 24},
                {"row": 0, "column": 24, "rowspan": 15, "colspan": 24},
                {"row": 0, "column": 48, "rowspan": 15, "colspan": 24},
            ],
            "vizzes": [
                {"row": 15, "column": 0, "rowspan": 30, "colspan": 72},
                {"row": 45, "column": 0, "rowspan": 30, "colspan": 36},
                {"row": 45, "column": 36, "rowspan": 30, "colspan": 36},
            ],
        },
    },

    "wide_viz": {
        "description": "3 metrics, 2 full-width vizzes stacked",
        "grid_columns": 72,
        "metric_row_height": 15,
        "viz_row_height": 30,
        "slots": {
            "metrics": [
                {"row": 0, "column": 0, "rowspan": 15, "colspan": 24},
                {"row": 0, "column": 24, "rowspan": 15, "colspan": 24},
                {"row": 0, "column": 48, "rowspan": 15, "colspan": 24},
            ],
            "vizzes": [
                {"row": 15, "column": 0, "rowspan": 30, "colspan": 72},
                {"row": 45, "column": 0, "rowspan": 30, "colspan": 72},
            ],
        },
    },
}


def select_layout(num_metrics: int, num_vizzes: int) -> str:
    """Auto-select best layout pattern based on widget counts."""
    if num_metrics > 3:
        return "metrics_heavy"
    if num_vizzes <= 2:
        return "wide_viz"
    if num_vizzes == 3:
        return "story_flow"
    return "standard"


def build_dashboard_payload(
    *,
    dash_name: str,
    dash_label: str,
    ws_api: str,
    sdm_api: str,
    metric_apis: List[str],
    viz_apis: List[str],
    layout: str = "auto",
    style_overrides: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """Build a complete dashboard payload.

    Args:
        dash_name: API name for the dashboard
        dash_label: Display label
        ws_api: Workspace apiName
        sdm_api: SDM apiName
        metric_apis: List of metric widget apiNames (from _mtc creation)
        viz_apis: List of visualization apiNames
        layout: Layout pattern name or "auto"
        style_overrides: Brand color overrides for background/gutter

    Returns:
        Complete dashboard payload for POST
    """
    style_overrides = style_overrides or {}

    if layout == "auto":
        layout = select_layout(len(metric_apis), len(viz_apis))

    pattern = LAYOUT_PATTERNS.get(layout, LAYOUT_PATTERNS["standard"])

    bg_color = style_overrides.get("dashboard_bg", "#F3F3F3")
    gutter_color = style_overrides.get("gutter_color", "#F3F3F3")

    widgets_dict = {}
    page_widgets = []

    metric_slots = pattern["slots"]["metrics"]
    for i, mtc_api in enumerate(metric_apis):
        if i >= len(metric_slots):
            break
        slot = metric_slots[i]
        wname = f"metric_{i}"
        widgets_dict[wname] = {
            "name": wname,
            "type": "metric",
            "source": {"name": mtc_api},
            "parameters": {
                "metricOption": {"sdmApiName": sdm_api},
            },
            "actions": [],
        }
        page_widgets.append({
            "name": wname,
            "row": slot["row"],
            "column": slot["column"],
            "rowspan": slot["rowspan"],
            "colspan": slot["colspan"],
        })

    viz_slots = pattern["slots"]["vizzes"]
    for i, vapi in enumerate(viz_apis):
        if i >= len(viz_slots):
            break
        slot = viz_slots[i]
        wname = f"viz_{i}"

        widgets_dict[wname] = {
            "name": wname,
            "type": "visualization",
            "source": {"name": vapi},
            "parameters": {},
            "actions": [],
        }
        page_widgets.append({
            "name": wname,
            "row": slot["row"],
            "column": slot["column"],
            "rowspan": slot["rowspan"],
            "colspan": slot["colspan"],
        })

    page_name = str(uuid.uuid4())

    payload = {
        "name": dash_name,
        "label": dash_label,
        "workspaceIdOrApiName": ws_api,
        "widgets": widgets_dict,
        "layouts": [
            {
                "name": "default",
                "columnCount": pattern["grid_columns"],
                "rowHeight": 10,
                "maxWidth": 1200,
                "style": {
                    "backgroundColor": bg_color,
                    "gutterColor": gutter_color,
                    "cellSpacingX": 8,
                    "cellSpacingY": 8,
                },
                "pages": [
                    {
                        "name": page_name,
                        "label": "Overview",
                        "widgets": page_widgets,
                    }
                ],
            }
        ],
    }

    return payload


def format_layout_preview(
    metric_labels: List[str],
    viz_labels: List[str],
    layout: str = "auto",
) -> str:
    """Generate a text preview of the dashboard layout for user confirmation.

    Returns an ASCII representation showing where metrics and vizzes
    will be placed.
    """
    if layout == "auto":
        layout = select_layout(len(metric_labels), len(viz_labels))

    pattern = LAYOUT_PATTERNS[layout]
    lines = []
    lines.append(f"  Layout: {layout} — {pattern['description']}")
    lines.append("")

    metric_slots = pattern["slots"]["metrics"]
    viz_slots = pattern["slots"]["vizzes"]

    lines.append("  ┌" + "─" * 70 + "┐")

    # Metrics row
    if metric_labels:
        row_parts = []
        for i, slot in enumerate(metric_slots):
            label = metric_labels[i] if i < len(metric_labels) else "—"
            width = int(slot["colspan"] / 72 * 66)
            row_parts.append(f" {label[:width-2]:^{width-2}} ")
        lines.append("  │" + "│".join(row_parts) + "│")
        lines.append("  │" + "│".join([" " * (int(s["colspan"]/72*66)) for s in metric_slots]) + "│")
        lines.append("  ├" + "┼".join(["─" * int(s["colspan"]/72*66) for s in metric_slots]) + "┤")

    # Viz rows
    current_row = None
    row_vizzes = []
    for i, slot in enumerate(viz_slots):
        label = viz_labels[i] if i < len(viz_labels) else "—"
        if current_row is not None and slot["row"] != current_row:
            # Print previous row
            parts = []
            for v in row_vizzes:
                width = int(v["colspan"] / 72 * 66)
                parts.append(f" {v['label'][:width-2]:^{width-2}} ")
            lines.append("  │" + "│".join(parts) + "│")
            lines.append("  ├" + "┼".join(["─" * int(v["colspan"]/72*66) for v in row_vizzes]) + "┤")
            row_vizzes = []
        current_row = slot["row"]
        row_vizzes.append({**slot, "label": label})

    if row_vizzes:
        parts = []
        for v in row_vizzes:
            width = int(v["colspan"] / 72 * 66)
            parts.append(f" {v['label'][:width-2]:^{width-2}} ")
        lines.append("  │" + "│".join(parts) + "│")

    lines.append("  └" + "─" * 70 + "┘")

    return "\n".join(lines)
