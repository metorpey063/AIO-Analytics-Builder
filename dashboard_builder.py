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

# --- Tableau Next product templates (captured from UI) ---
# These match the built-in dashboard templates available in the
# Tableau Next "New Dashboard" dialog. They use a 72-col grid with
# cellSpacing=0, containers with rounded borders, and BAN-only metrics.
#
# IMPORTANT: MCP create_dashboard always creates a 48-col / rowHeight-20
# grid. These templates are defined in native 72-col / rowHeight-10.
# Use scale_slots_for_grid() to adapt positions before sending operations.

PRODUCT_TEMPLATES = ["z_layout", "perf_overview"]


def scale_slots_for_grid(
    slots: Dict[str, Any],
    source_cols: int = 72,
    source_row_height: int = 10,
    target_cols: int = 48,
    target_row_height: int = 20,
) -> Dict[str, Any]:
    """Scale template slot positions from one grid to another.

    MCP create_dashboard produces 48-col / rowHeight-20 grids, but the
    Tableau Next product templates use 72-col / rowHeight-10. This
    function rescales all positions proportionally.
    """
    col_ratio = target_cols / source_cols
    row_ratio = source_row_height / target_row_height

    def _scale(slot: Dict[str, int]) -> Dict[str, int]:
        return {
            "row": max(0, round(slot["row"] * row_ratio)),
            "column": max(0, round(slot["column"] * col_ratio)),
            "rowspan": max(1, round(slot["rowspan"] * row_ratio)),
            "colspan": max(1, round(slot["colspan"] * col_ratio)),
        }

    result = {}
    for k, v in slots.items():
        if isinstance(v, list):
            result[k] = [_scale(s) for s in v]
        elif isinstance(v, dict) and "row" in v:
            result[k] = _scale(v)
        else:
            result[k] = v
    return result

Z_LAYOUT = {
    "description": "Tableau Next Z-layout: filters → 6 KPIs → hero viz → 3-up detail → full-width bottom",
    "grid": {
        "columnCount": 72,
        "rowHeight": 10,
        "style": {
            "backgroundColor": "#f3f3f3",
            "gutterColor": "#ffffff",
            "cellSpacingX": 0,
            "cellSpacingY": 0,
        },
    },
    "widget_styles": {
        "metric": {
            "borderColor": "#C9C9C9",
            "borderEdges": ["all"],
            "borderRadius": 20,
        },
        "viz_container": {
            "borderColor": "#c9c9c9",
            "borderEdges": ["all"],
            "borderRadius": 16,
        },
        "filter": {
            "backgroundColor": "#f3f3f3",
            "borderEdges": [],
        },
    },
    "metric_layout": {
        "componentVisibility": {
            "details": True,
            "title": True,
            "value": True,
            "comparison": True,
            "chart": False,
            "insights": True,
        },
    },
    "text_styles": {
        "section_title": {"color": "#03234d", "size": "24px"},
        "section_sub": {"color": "#2e2e2e", "size": "16px"},
        "viz_title": {"color": "#2e2e2e", "size": "18px"},
    },
    "slots": {
        "filters": [
            {"row": 1, "column": 1, "rowspan": 5, "colspan": 11},
            {"row": 1, "column": 13, "rowspan": 5, "colspan": 11},
            {"row": 1, "column": 25, "rowspan": 5, "colspan": 11},
            {"row": 1, "column": 37, "rowspan": 5, "colspan": 11},
            {"row": 1, "column": 49, "rowspan": 5, "colspan": 11},
            {"row": 1, "column": 61, "rowspan": 5, "colspan": 10},
        ],
        "metrics_row1": [
            {"row": 8, "column": 1, "rowspan": 19, "colspan": 22},
            {"row": 8, "column": 24, "rowspan": 19, "colspan": 23},
            {"row": 8, "column": 48, "rowspan": 19, "colspan": 23},
        ],
        "metrics_row2": [
            {"row": 29, "column": 1, "rowspan": 19, "colspan": 22},
            {"row": 29, "column": 24, "rowspan": 19, "colspan": 23},
            {"row": 29, "column": 48, "rowspan": 19, "colspan": 23},
        ],
        "hero_container": {"row": 50, "column": 1, "rowspan": 47, "colspan": 70},
        "hero_title": {"row": 51, "column": 2, "rowspan": 5, "colspan": 45},
        "hero_viz": {"row": 56, "column": 1, "rowspan": 41, "colspan": 70},
        "detail_header": {"row": 101, "column": 1, "rowspan": 6, "colspan": 70},
        "detail_containers": [
            {"row": 110, "column": 1, "rowspan": 41, "colspan": 23},
            {"row": 110, "column": 25, "rowspan": 41, "colspan": 23},
            {"row": 110, "column": 49, "rowspan": 41, "colspan": 22},
        ],
        "detail_titles": [
            {"row": 111, "column": 2, "rowspan": 3, "colspan": 22},
            {"row": 111, "column": 26, "rowspan": 3, "colspan": 21},
            {"row": 111, "column": 50, "rowspan": 3, "colspan": 20},
        ],
        "detail_vizzes": [
            {"row": 114, "column": 1, "rowspan": 37, "colspan": 23},
            {"row": 114, "column": 25, "rowspan": 37, "colspan": 23},
            {"row": 114, "column": 49, "rowspan": 37, "colspan": 22},
        ],
        "bottom_container": {"row": 153, "column": 1, "rowspan": 57, "colspan": 70},
        "bottom_viz": {"row": 155, "column": 2, "rowspan": 53, "colspan": 68},
    },
}


def build_z_layout_ops(
    *,
    page_name: str,
    title: str,
    subtitle: str,
    sdm_api: str,
    sdm_id: str,
    metric_apis: List[str],
    metric_labels: List[str],
    viz_apis: List[str],
    viz_labels: List[str],
    viz_ids: Optional[List[str]] = None,
    filter_fields: Optional[List[Dict[str, str]]] = None,
    detail_header: str = "Details",
    detail_sub: str = "",
    brand_colors: Optional[Dict[str, str]] = None,
    grid_columns: int = 48,
) -> List[Dict[str, Any]]:
    """Build MCP edit_dashboard operations for a Z-layout dashboard.

    Returns a list of operations ready for the edit_dashboard MCP tool.
    Fills as many slots as provided; unused slots are skipped.

    Args:
        page_name: UUID page name from create_dashboard response
        title: Dashboard title text
        subtitle: Subtitle/description text
        sdm_api: SDM apiName
        sdm_id: SDM Salesforce ID (2SM...)
        metric_apis: List of metric _mtc apiNames (up to 6)
        metric_labels: Display labels for metrics
        viz_apis: List of visualization apiNames (hero + up to 3 detail + bottom)
        viz_labels: Display labels for vizzes
        viz_ids: Optional list of viz Salesforce IDs (1AK...) matching viz_apis order.
                 Always pass both id+name for reliable rendering.
        filter_fields: List of dicts with keys: fieldName, objectName, label
        detail_header: Section header text for the detail row
        detail_sub: Section subheader text
        brand_colors: Optional overrides for title_color, sub_color
        grid_columns: Target grid column count (48 for MCP-created dashboards)
    """
    ops: List[Dict[str, Any]] = []
    z = Z_LAYOUT
    bc = brand_colors or {}
    title_color = bc.get("title_color", z["text_styles"]["section_title"]["color"])
    sub_color = bc.get("sub_color", z["text_styles"]["section_sub"]["color"])
    viz_ids = viz_ids or []

    # Scale slots if target grid differs from template's native 72-col grid
    slots = z["slots"]
    if grid_columns != z["grid"]["columnCount"]:
        slots = scale_slots_for_grid(
            slots,
            source_cols=z["grid"]["columnCount"],
            source_row_height=z["grid"]["rowHeight"],
            target_cols=grid_columns,
            target_row_height=20 if grid_columns == 48 else 10,
        )
    m_style = z["widget_styles"]["metric"]
    c_style = z["widget_styles"]["viz_container"]

    def _viz_source(idx):
        src = {"name": viz_apis[idx]}
        if idx < len(viz_ids) and viz_ids[idx]:
            src["id"] = viz_ids[idx]
        return src

    # --- Filters (up to 6) ---
    filter_fields = filter_fields or []
    for i, ff in enumerate(filter_fields[:6]):
        slot = slots["filters"][i]
        fname = f"filter_{i+1}"
        ops.append({
            "operation": "upsert_filter_widget",
            "widget": {
                "type": "filter",
                "name": fname,
                "label": ff.get("label", ff["fieldName"]),
                "source": {"name": sdm_api},
                "parameters": {
                    "viewType": "list",
                    "isLabelHidden": False,
                    "filterOption": {
                        "fieldName": ff["fieldName"],
                        "objectName": ff["objectName"],
                        "dataType": ff.get("dataType", "Text"),
                        "selectionType": "multiple",
                    },
                    "widgetStyle": z["widget_styles"]["filter"],
                },
            },
        })
        ops.append({
            "operation": "place_widget_on_page",
            "pageName": page_name,
            "placement": {"name": fname, **slot},
        })

    # --- Metrics (up to 6, two rows of 3) ---
    all_metric_slots = slots["metrics_row1"] + slots["metrics_row2"]
    for i, (mapi, mlabel) in enumerate(zip(metric_apis[:6], metric_labels[:6])):
        slot = all_metric_slots[i]
        mname = f"metric_{i+1}"
        ops.append({
            "operation": "upsert_metric_widget",
            "widget": {
                "type": "metric",
                "name": mname,
                "label": mlabel,
                "source": {"name": mapi},
                "parameters": {
                    "metricOption": {
                        "sdmApiName": sdm_api,
                        "sdmId": sdm_id,
                    },
                    "receiveFilterSource": {"filterMode": "all", "publishers": [], "widgetIds": []},
                    "widgetStyle": m_style,
                },
            },
        })
        ops.append({
            "operation": "place_widget_on_page",
            "pageName": page_name,
            "placement": {"name": mname, **slot},
        })

    # --- Hero section (container + title + viz) ---
    if viz_apis:
        ops.append({
            "operation": "upsert_container_widget",
            "widget": {
                "type": "container",
                "name": "container_hero",
                "parameters": {"widgetStyle": c_style},
            },
        })
        ops.append({
            "operation": "place_widget_on_page",
            "pageName": page_name,
            "placement": {"name": "container_hero", **slots["hero_container"]},
        })
        ops.append({
            "operation": "upsert_text_widget",
            "widget": {
                "type": "text",
                "name": "text_hero_title",
                "parameters": {
                    "content": [
                        {"attributes": {"color": title_color, "size": "20px"}, "insert": title},
                        {"insert": "\n"},
                        {"attributes": {"color": "#5c5c5c", "size": "14px"}, "insert": subtitle},
                        {"attributes": {"align": "left"}, "insert": "\n"},
                    ],
                    "lineSpacing": 1.5,
                    "widgetStyle": {"borderColor": "#C9C9C9", "borderEdges": []},
                },
            },
        })
        ops.append({
            "operation": "place_widget_on_page",
            "pageName": page_name,
            "placement": {"name": "text_hero_title", **slots["hero_title"]},
        })
        ops.append({
            "operation": "upsert_visualization_widget",
            "widget": {
                "type": "visualization",
                "name": "viz_hero",
                "source": _viz_source(0),
                "parameters": {
                    "receiveFilterSource": {"filterMode": "all", "publishers": [], "widgetIds": []},
                },
            },
        })
        ops.append({
            "operation": "place_widget_on_page",
            "pageName": page_name,
            "placement": {"name": "viz_hero", **slots["hero_viz"]},
        })

    # --- Detail section header ---
    detail_vizzes = viz_apis[1:4]
    detail_labels = viz_labels[1:4] if len(viz_labels) > 1 else []
    if detail_vizzes:
        ops.append({
            "operation": "upsert_text_widget",
            "widget": {
                "type": "text",
                "name": "text_detail_header",
                "parameters": {
                    "content": [
                        {"attributes": {"color": title_color, "size": "24px"}, "insert": detail_header},
                        {"insert": "\n"},
                        {"attributes": {"color": sub_color, "size": "16px"}, "insert": detail_sub},
                        {"attributes": {"align": "left"}, "insert": "\n"},
                    ],
                    "lineSpacing": 1.5,
                    "widgetStyle": {"backgroundColor": "#f3f3f3", "borderEdges": []},
                },
            },
        })
        ops.append({
            "operation": "place_widget_on_page",
            "pageName": page_name,
            "placement": {"name": "text_detail_header", **slots["detail_header"]},
        })

    # --- Detail row (up to 3 containers with titled vizzes) ---
    for i, (vapi, vlabel) in enumerate(zip(detail_vizzes, detail_labels)):
        cname = f"container_detail_{i+1}"
        tname = f"text_detail_{i+1}"
        vname = f"viz_detail_{i+1}"
        ops.append({
            "operation": "upsert_container_widget",
            "widget": {"type": "container", "name": cname, "parameters": {"widgetStyle": c_style}},
        })
        ops.append({
            "operation": "place_widget_on_page",
            "pageName": page_name,
            "placement": {"name": cname, **slots["detail_containers"][i]},
        })
        ops.append({
            "operation": "upsert_text_widget",
            "widget": {
                "type": "text",
                "name": tname,
                "parameters": {
                    "content": [
                        {"attributes": {"color": sub_color, "size": "18px"}, "insert": vlabel},
                        {"attributes": {"align": "left"}, "insert": "\n"},
                    ],
                    "lineSpacing": 1.5,
                    "widgetStyle": {"borderColor": "#C9C9C9", "borderEdges": []},
                },
            },
        })
        ops.append({
            "operation": "place_widget_on_page",
            "pageName": page_name,
            "placement": {"name": tname, **slots["detail_titles"][i]},
        })
        detail_idx = i + 1
        ops.append({
            "operation": "upsert_visualization_widget",
            "widget": {
                "type": "visualization",
                "name": vname,
                "source": _viz_source(detail_idx),
                "parameters": {
                    "receiveFilterSource": {"filterMode": "all", "publishers": [], "widgetIds": []},
                },
            },
        })
        ops.append({
            "operation": "place_widget_on_page",
            "pageName": page_name,
            "placement": {"name": vname, **slots["detail_vizzes"][i]},
        })

    # --- Bottom full-width viz ---
    if len(viz_apis) > 4:
        ops.append({
            "operation": "upsert_container_widget",
            "widget": {"type": "container", "name": "container_bottom", "parameters": {"widgetStyle": c_style}},
        })
        ops.append({
            "operation": "place_widget_on_page",
            "pageName": page_name,
            "placement": {"name": "container_bottom", **slots["bottom_container"]},
        })
        ops.append({
            "operation": "upsert_visualization_widget",
            "widget": {
                "type": "visualization",
                "name": "viz_bottom",
                "source": _viz_source(4),
                "parameters": {
                    "receiveFilterSource": {"filterMode": "all", "publishers": [], "widgetIds": []},
                },
            },
        })
        ops.append({
            "operation": "place_widget_on_page",
            "pageName": page_name,
            "placement": {"name": "viz_bottom", **slots["bottom_viz"]},
        })

    return ops


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


# --- Performance Overview template (captured from Tableau Next UI) ---
# Multi-page dashboard with Week/Month/Day navigation buttons,
# hero metric with sparkline, 4 supporting BANs, 2 mid vizzes, 1 bottom viz.

PERF_OVERVIEW = {
    "description": "Tableau Next Performance Overview: title + filters → hero metric + 4 BANs → 2 mid vizzes → full-width bottom viz, with Week/Month/Day page navigation",
    "grid": {
        "columnCount": 72,
        "rowHeight": 10,
        "style": {
            "backgroundColor": "#f3f3f3",
            "gutterColor": "#ffffff",
            "cellSpacingX": 0,
            "cellSpacingY": 8,
        },
    },
    "widget_styles": {
        "metric_hero": {
            "borderColor": "#C9C9C9",
            "borderEdges": ["all"],
            "borderRadius": 12,
        },
        "metric_ban": {
            "borderColor": "#c9c9c9",
            "borderEdges": ["all"],
            "borderRadius": 12,
        },
        "viz": {
            "borderColor": "#c9c9c9",
            "borderEdges": ["all"],
            "borderRadius": 12,
        },
        "container": {
            "borderEdges": [],
            "borderRadius": 16,
        },
        "filter": {
            "backgroundColor": "#f3f3f3",
            "borderColor": "#f3f3f3",
            "borderEdges": [],
        },
        "nav_active": {
            "backgroundColor": "#066AFE",
            "borderColor": "#c9c9c9",
            "borderEdges": ["all"],
            "fontColor": "#ffffff",
        },
        "nav_inactive": {
            "borderColor": "#c9c9c9",
            "borderEdges": ["all"],
            "fontColor": "#0250D9",
        },
        "nav_inactive_left": {
            "borderColor": "#c9c9c9",
            "borderEdges": ["left", "top", "bottom"],
            "fontColor": "#0250D9",
        },
        "nav_inactive_right": {
            "borderColor": "#c9c9c9",
            "borderEdges": ["right", "top", "bottom"],
            "fontColor": "#0250D9",
        },
    },
    "metric_layout_hero": {
        "componentVisibility": {
            "details": True, "title": True, "value": True,
            "comparison": True, "chart": True, "insights": False,
        },
    },
    "metric_layout_ban": {
        "componentVisibility": {
            "details": True, "title": True, "value": True,
            "comparison": True, "chart": False, "insights": False,
        },
    },
    "text_styles": {
        "title": {"color": "#042339", "size": "42px"},
        "section_header": {"color": "#03234d", "size": "20px"},
        "viz_label": {"color": "#1e1e1e", "size": "20px"},
    },
    "slots": {
        "title": {"row": 1, "column": 1, "rowspan": 5, "colspan": 25},
        "filters": [
            {"row": 1, "column": 33, "rowspan": 4, "colspan": 12},
            {"row": 1, "column": 46, "rowspan": 4, "colspan": 12},
            {"row": 1, "column": 59, "rowspan": 4, "colspan": 12},
        ],
        "container_top": {"row": 6, "column": 1, "rowspan": 47, "colspan": 70},
        "section_header_top": {"row": 7, "column": 2, "rowspan": 2, "colspan": 15},
        "metric_hero": {"row": 10, "column": 2, "rowspan": 19, "colspan": 24},
        "metrics_ban": [
            {"row": 10, "column": 27, "rowspan": 9, "colspan": 21},
            {"row": 10, "column": 49, "rowspan": 9, "colspan": 21},
            {"row": 20, "column": 27, "rowspan": 9, "colspan": 21},
            {"row": 20, "column": 49, "rowspan": 9, "colspan": 21},
        ],
        "viz_left_label": {"row": 30, "column": 2, "rowspan": 2, "colspan": 18},
        "viz_right_label": {"row": 30, "column": 27, "rowspan": 2, "colspan": 18},
        "nav_buttons": [
            {"row": 30, "column": 57, "rowspan": 2, "colspan": 4},
            {"row": 30, "column": 61, "rowspan": 2, "colspan": 4},
            {"row": 30, "column": 65, "rowspan": 2, "colspan": 4},
        ],
        "viz_left": {"row": 32, "column": 2, "rowspan": 20, "colspan": 24},
        "viz_right": {"row": 32, "column": 27, "rowspan": 20, "colspan": 43},
        "container_bottom": {"row": 54, "column": 1, "rowspan": 29, "colspan": 70},
        "section_header_bottom": {"row": 55, "column": 2, "rowspan": 2, "colspan": 15},
        "viz_bottom": {"row": 58, "column": 2, "rowspan": 24, "colspan": 68},
    },
}


def build_perf_overview_ops(
    *,
    page_name: str,
    title: str,
    sdm_api: str,
    sdm_id: str,
    hero_metric_api: str,
    hero_metric_label: str,
    ban_metric_apis: List[str],
    ban_metric_labels: List[str],
    viz_left_api: str,
    viz_left_label: str,
    viz_left_id: Optional[str] = None,
    viz_right_api: str,
    viz_right_label: str,
    viz_right_id: Optional[str] = None,
    viz_bottom_api: str,
    viz_bottom_label: str,
    viz_bottom_id: Optional[str] = None,
    section_header_top: str = "Key Metrics",
    section_header_bottom: str = "Trend Analysis",
    filter_fields: Optional[List[Dict[str, str]]] = None,
    nav_labels: Optional[List[str]] = None,
    brand_colors: Optional[Dict[str, str]] = None,
    grid_columns: int = 48,
) -> List[Dict[str, Any]]:
    """Build MCP edit_dashboard operations for a Performance Overview dashboard.

    Single-page version (no page navigation). For multi-page with nav buttons,
    call this once per page and add nav button ops manually.

    Args:
        page_name: UUID page name from create_dashboard response
        title: Dashboard title (large, 42px)
        sdm_api: SDM apiName
        sdm_id: SDM Salesforce ID
        hero_metric_api: The primary metric (large card with sparkline)
        hero_metric_label: Display label for hero metric
        ban_metric_apis: Up to 4 supporting metrics (BAN only)
        ban_metric_labels: Display labels for BAN metrics
        viz_left_api: Left viz apiName ("Metric Breakdown")
        viz_left_label: Left viz section label
        viz_left_id: Optional Salesforce ID for the left viz
        viz_right_api: Right viz apiName ("Records Leaderboard")
        viz_right_label: Right viz section label
        viz_right_id: Optional Salesforce ID for the right viz
        viz_bottom_api: Bottom full-width viz apiName
        viz_bottom_label: Bottom section label
        viz_bottom_id: Optional Salesforce ID for the bottom viz
        filter_fields: Up to 3 filter dicts with fieldName, objectName, label
        nav_labels: Optional 3 navigation button labels (e.g. ["Day", "Week", "Month"])
        brand_colors: Optional overrides for title_color, accent_color
        grid_columns: Target grid column count (48 for MCP-created dashboards)
    """
    ops: List[Dict[str, Any]] = []
    p = PERF_OVERVIEW
    bc = brand_colors or {}
    title_color = bc.get("title_color", p["text_styles"]["title"]["color"])
    header_color = bc.get("header_color", p["text_styles"]["section_header"]["color"])
    label_color = bc.get("label_color", p["text_styles"]["viz_label"]["color"])

    # Scale slots if target grid differs from template's native 72-col grid
    slots = p["slots"]
    if grid_columns != p["grid"]["columnCount"]:
        slots = scale_slots_for_grid(
            slots,
            source_cols=p["grid"]["columnCount"],
            source_row_height=p["grid"]["rowHeight"],
            target_cols=grid_columns,
            target_row_height=20 if grid_columns == 48 else 10,
        )

    def _viz_src(name, vid):
        src = {"name": name}
        if vid:
            src["id"] = vid
        return src
    m_hero = p["widget_styles"]["metric_hero"]
    m_ban = p["widget_styles"]["metric_ban"]
    v_style = p["widget_styles"]["viz"]
    c_style = p["widget_styles"]["container"]
    f_style = p["widget_styles"]["filter"]
    _recv = {"filterMode": "all", "publishers": [], "widgetIds": []}
    _recv_p = {"parameterMode": "all", "publishers": []}

    # --- Title ---
    ops.append({
        "operation": "upsert_text_widget",
        "widget": {
            "type": "text", "name": "text_title",
            "parameters": {
                "content": [
                    {"attributes": {"color": title_color, "size": "42px"}, "insert": title},
                    {"attributes": {"align": "left"}, "insert": "\n"},
                ],
                "lineSpacing": 1.5,
                "verticalAlignment": "top",
                "widgetStyle": {"backgroundColor": "#f3f3f3", "borderColor": "#f3f3f3", "borderEdges": ["all"]},
            },
        },
    })
    ops.append({"operation": "place_widget_on_page", "pageName": page_name,
                "placement": {"name": "text_title", **slots["title"]}})

    # --- Filters (up to 3) ---
    filter_fields = filter_fields or []
    for i, ff in enumerate(filter_fields[:3]):
        fname = f"list_{i+3}"
        ops.append({
            "operation": "upsert_filter_widget",
            "widget": {
                "type": "filter", "name": fname,
                "label": ff.get("label", ff["fieldName"]),
                "source": {"name": sdm_api},
                "parameters": {
                    "viewType": "list", "isLabelHidden": False,
                    "filterOption": {
                        "fieldName": ff["fieldName"],
                        "objectName": ff["objectName"],
                        "dataType": ff.get("dataType", "Text"),
                        "selectionType": "multiple",
                    },
                    "receiveFilterSource": _recv,
                    "widgetStyle": f_style,
                },
            },
        })
        ops.append({"operation": "place_widget_on_page", "pageName": page_name,
                    "placement": {"name": fname, **slots["filters"][i]}})

    # --- Top container ---
    ops.append({
        "operation": "upsert_container_widget",
        "widget": {"type": "container", "name": "container_1", "parameters": {"widgetStyle": c_style}},
    })
    ops.append({"operation": "place_widget_on_page", "pageName": page_name,
                "placement": {"name": "container_1", **slots["container_top"]}})

    # --- Section header (top) ---
    ops.append({
        "operation": "upsert_text_widget",
        "widget": {
            "type": "text", "name": "text_section_top",
            "parameters": {
                "content": [
                    {"attributes": {"color": header_color, "size": "20px"}, "insert": section_header_top},
                    {"attributes": {"align": "left"}, "insert": "\n"},
                ],
                "lineSpacing": 1.5, "verticalAlignment": "top",
                "receiveFilterSource": _recv, "receiveParameterSource": _recv_p,
            },
        },
    })
    ops.append({"operation": "place_widget_on_page", "pageName": page_name,
                "placement": {"name": "text_section_top", **slots["section_header_top"]}})

    # --- Hero metric (large, with chart) ---
    ops.append({
        "operation": "upsert_metric_widget",
        "widget": {
            "type": "metric", "name": "metric_1", "label": hero_metric_label,
            "source": {"name": hero_metric_api},
            "parameters": {
                "metricOption": {"sdmApiName": sdm_api, "sdmId": sdm_id},
                "receiveFilterSource": _recv, "widgetStyle": m_hero,
            },
        },
    })
    ops.append({"operation": "place_widget_on_page", "pageName": page_name,
                "placement": {"name": "metric_1", **slots["metric_hero"]}})

    # --- BAN metrics (up to 4, 2x2 grid) ---
    for i, (mapi, mlabel) in enumerate(zip(ban_metric_apis[:4], ban_metric_labels[:4])):
        mname = f"metric_{i+2}"
        ops.append({
            "operation": "upsert_metric_widget",
            "widget": {
                "type": "metric", "name": mname, "label": mlabel,
                "source": {"name": mapi},
                "parameters": {
                    "metricOption": {"sdmApiName": sdm_api, "sdmId": sdm_id},
                    "receiveFilterSource": _recv, "widgetStyle": m_ban,
                },
            },
        })
        ops.append({"operation": "place_widget_on_page", "pageName": page_name,
                    "placement": {"name": mname, **slots["metrics_ban"][i]}})

    # --- Viz section labels ---
    ops.append({
        "operation": "upsert_text_widget",
        "widget": {
            "type": "text", "name": "text_viz_left_label",
            "parameters": {
                "content": [
                    {"attributes": {"color": label_color, "size": "20px"}, "insert": viz_left_label},
                    {"attributes": {"align": "left"}, "insert": "\n"},
                ],
                "lineSpacing": 1.5, "verticalAlignment": "top",
                "receiveFilterSource": _recv, "receiveParameterSource": _recv_p,
            },
        },
    })
    ops.append({"operation": "place_widget_on_page", "pageName": page_name,
                "placement": {"name": "text_viz_left_label", **slots["viz_left_label"]}})

    ops.append({
        "operation": "upsert_text_widget",
        "widget": {
            "type": "text", "name": "text_viz_right_label",
            "parameters": {
                "content": [
                    {"attributes": {"color": label_color, "size": "20px"}, "insert": viz_right_label},
                    {"attributes": {"align": "left"}, "insert": "\n"},
                ],
                "lineSpacing": 1.5, "verticalAlignment": "top",
                "receiveFilterSource": _recv, "receiveParameterSource": _recv_p,
            },
        },
    })
    ops.append({"operation": "place_widget_on_page", "pageName": page_name,
                "placement": {"name": "text_viz_right_label", **slots["viz_right_label"]}})

    # --- Navigation buttons (optional, single-page shows them as static labels) ---
    if nav_labels and len(nav_labels) == 3:
        for i, nlabel in enumerate(nav_labels):
            bname = f"button_{i+1}"
            is_active = (i == 0)
            style = p["widget_styles"]["nav_active"] if is_active else (
                p["widget_styles"]["nav_inactive_left"] if i == 0 else
                p["widget_styles"]["nav_inactive_right"] if i == 2 else
                p["widget_styles"]["nav_inactive"]
            )
            ops.append({
                "operation": "upsert_button_widget",
                "widget": {
                    "type": "button", "name": bname,
                    "parameters": {
                        "alignmentX": "center", "alignmentY": "center",
                        "fontSize": 16, "text": nlabel,
                        "widgetStyle": style,
                    },
                },
            })
            ops.append({"operation": "place_widget_on_page", "pageName": page_name,
                        "placement": {"name": bname, **slots["nav_buttons"][i]}})

    # --- Mid vizzes (left + right) ---
    ops.append({
        "operation": "upsert_visualization_widget",
        "widget": {
            "type": "visualization", "name": "viz_left",
            "source": _viz_src(viz_left_api, viz_left_id),
            "parameters": {
                "legendPosition": "Bottom",
                "receiveFilterSource": _recv, "receiveParameterSource": _recv_p,
                "widgetStyle": v_style,
            },
        },
    })
    ops.append({"operation": "place_widget_on_page", "pageName": page_name,
                "placement": {"name": "viz_left", **slots["viz_left"]}})

    ops.append({
        "operation": "upsert_visualization_widget",
        "widget": {
            "type": "visualization", "name": "viz_right",
            "source": _viz_src(viz_right_api, viz_right_id),
            "parameters": {
                "legendPosition": "Bottom",
                "receiveFilterSource": _recv, "receiveParameterSource": _recv_p,
                "widgetStyle": v_style,
            },
        },
    })
    ops.append({"operation": "place_widget_on_page", "pageName": page_name,
                "placement": {"name": "viz_right", **slots["viz_right"]}})

    # --- Bottom container + viz ---
    ops.append({
        "operation": "upsert_container_widget",
        "widget": {"type": "container", "name": "container_2", "parameters": {"widgetStyle": c_style}},
    })
    ops.append({"operation": "place_widget_on_page", "pageName": page_name,
                "placement": {"name": "container_2", **slots["container_bottom"]}})

    ops.append({
        "operation": "upsert_text_widget",
        "widget": {
            "type": "text", "name": "text_section_bottom",
            "parameters": {
                "content": [
                    {"attributes": {"color": header_color, "size": "20px"}, "insert": section_header_bottom},
                    {"attributes": {"align": "left"}, "insert": "\n"},
                ],
                "lineSpacing": 1.5, "verticalAlignment": "top",
                "receiveFilterSource": _recv, "receiveParameterSource": _recv_p,
            },
        },
    })
    ops.append({"operation": "place_widget_on_page", "pageName": page_name,
                "placement": {"name": "text_section_bottom", **slots["section_header_bottom"]}})

    ops.append({
        "operation": "upsert_visualization_widget",
        "widget": {
            "type": "visualization", "name": "viz_bottom",
            "source": _viz_src(viz_bottom_api, viz_bottom_id),
            "parameters": {
                "legendPosition": "Right",
                "receiveFilterSource": _recv, "receiveParameterSource": _recv_p,
            },
        },
    })
    ops.append({"operation": "place_widget_on_page", "pageName": page_name,
                "placement": {"name": "viz_bottom", **slots["viz_bottom"]}})

    return ops
