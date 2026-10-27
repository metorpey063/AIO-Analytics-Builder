"""Story-driven dashboard composer for Tableau Next.

Maps the demo's story arc (what's wrong → where → why → who → counter-trend)
to chart components, generates narrative titles, produces an ASCII preview,
and emits a build plan that viz_builder + dashboard_builder consume.

This is the "premium" dashboard option alongside the template deployer.
Templates are pixel-perfect replicas of product layouts; the composer
creates bespoke dashboards tailored to each demo's specific story.
"""

from typing import Any, Dict, List, Optional, Tuple
import textwrap


# ── Chart component definitions ─────────────────────────────────────────────
# Each component answers one story question and maps to a viz template.

COMPONENTS = {
    "kpi_row": {
        "description": "Metric BAN tiles across the top",
        "widget_type": "metric",
        "story_role": "overview",
    },
    "trend_line": {
        "description": "Primary metric trend over time — the 'what's wrong' chart",
        "viz_template": "trend_over_time",
        "story_role": "whats_wrong",
        "default_width": "full",
    },
    "change_bar": {
        "description": "Period-over-period change by dimension — the 'where is it' chart",
        "viz_template": "horizontal_bar",
        "story_role": "where",
        "default_width": "half",
        "uses_change_values": True,
    },
    "breakdown_bar": {
        "description": "Stacked bar by category — the 'why' chart",
        "viz_template": "stacked_bar",
        "story_role": "why",
        "default_width": "half",
    },
    "multi_line": {
        "description": "Multi-series line showing segment divergence",
        "viz_template": "multi_series_line",
        "story_role": "where",
        "default_width": "half",
    },
    "ranking_bar": {
        "description": "Horizontal bar ranking entities — the 'who' chart",
        "viz_template": "horizontal_bar",
        "story_role": "who",
        "default_width": "half",
    },
    "donut": {
        "description": "Part-to-whole distribution by category",
        "viz_template": "donut",
        "story_role": "composition",
        "default_width": "half",
    },
    "dual_axis": {
        "description": "Two metrics on independent Y-axes — leading indicator relationship",
        "viz_template": "dual_axis",
        "story_role": "supporting",
        "default_width": "full",
    },
    "detail_table": {
        "description": "Detail text table for entity-level drill",
        "viz_template": "heatmap",
        "story_role": "who",
        "default_width": "full",
    },
}


# ── Story-to-component mapping ──────────────────────────────────────────────

def _pick_primary_metric(metrics: List[Dict]) -> Dict:
    """Find the primary metric (first one, or first rate metric)."""
    for m in metrics:
        if m.get("is_rate") or "rate" in m.get("field", "").lower():
            return m
    return metrics[0]


def _pick_supporting_metrics(metrics: List[Dict], primary: Dict) -> List[Dict]:
    """Return non-primary metrics in story order (rates first, then volumes)."""
    others = [m for m in metrics if m["field"] != primary["field"]]
    rates = [m for m in others if m.get("is_rate") or "rate" in m.get("field", "").lower()]
    volumes = [m for m in others if m not in rates]
    return rates + volumes


def _looks_like_rate(metric: Dict) -> bool:
    """Detect if a metric is a rate/percentage even without explicit is_rate flag."""
    if metric.get("is_rate"):
        return True
    field = metric.get("field", "").lower()
    label = metric.get("label", "").lower()
    agg = metric.get("agg", "").lower()
    rate_keywords = ("rate", "percent", "ratio", "conversion", "utilization",
                     "retention", "enrollment", "satisfaction", "score", "index")
    return any(kw in field or kw in label for kw in rate_keywords) or agg == "average"


def _infer_signal_direction(metric: Dict) -> str:
    """Return 'down' or 'up' based on sentiment + whether it's the problem."""
    sentiment = metric.get("sentiment", "").lower()
    if "upisbad" in sentiment or "up_is_bad" in sentiment:
        return "up"
    return "down"


def _pick_where_dimension(dimensions: List[str], dimension_values: Dict,
                          worst_segment: Optional[str] = None) -> Optional[str]:
    """Pick the dimension best suited for 'where is it worst?'

    If worst_segment is provided, find the dimension that contains it.
    Otherwise prefer geographic/segment dimensions.
    """
    if worst_segment:
        for d in dimensions:
            vals = dimension_values.get(d, [])
            if worst_segment in vals:
                return d

    geo_keywords = ["region", "state", "territory", "location", "market", "geography", "area"]
    segment_keywords = ["segment", "vertical", "industry", "sector", "type", "category", "tier", "band",
                        "line", "service"]

    for kw in geo_keywords:
        for d in dimensions:
            if kw in d.lower():
                return d
    for kw in segment_keywords:
        for d in dimensions:
            if kw in d.lower():
                return d
    return dimensions[0] if dimensions else None


def _pick_why_dimension(dimensions: List[str], where_dim: Optional[str]) -> Optional[str]:
    """Pick the dimension for 'why is it happening?' — different from the where dim."""
    candidates = [d for d in dimensions if d != where_dim]
    type_keywords = ["type", "category", "product", "line", "program", "plan", "class", "tier"]
    for kw in type_keywords:
        for d in candidates:
            if kw in d.lower():
                return d
    return candidates[0] if candidates else None


def _pick_who_dimension(dimensions: List[str], where_dim: Optional[str], why_dim: Optional[str]) -> Optional[str]:
    """Pick the dimension for 'who is at risk?' — entity-level or remaining dim."""
    used = {where_dim, why_dim}
    candidates = [d for d in dimensions if d not in used]
    entity_keywords = ["name", "client", "account", "agency", "company", "facility", "store", "site"]
    for kw in entity_keywords:
        for d in candidates:
            if kw in d.lower():
                return d
    return candidates[0] if candidates else where_dim


# ── Narrative title generator ────────────────────────────────────────────────

def _trend_title(metric_label: str, direction: str, months: int = 6) -> str:
    """Generate title like 'New Business Premium has fallen for six months'."""
    num_words = {2: "two", 3: "three", 4: "four", 5: "five", 6: "six",
                 7: "seven", 8: "eight", 9: "nine", 10: "ten", 12: "twelve"}
    months_str = num_words.get(months, str(months))
    verb = "fallen" if direction == "down" else "risen"
    return f"{metric_label} has {verb} for {months_str} months"


def _change_title(worst_segment: Optional[str], dim_name: str,
                  metric_label: str, direction: str) -> str:
    """Generate title like 'The Southeast drove last month's decline'."""
    if worst_segment:
        action = "decline" if direction == "down" else "increase"
        return f"{worst_segment} drove last month's {metric_label} {action}"
    return f"{metric_label} change by {dim_name}"


def _breakdown_title(metric_label: str, dim_name: str,
                     secondary_dim: Optional[str] = None) -> str:
    """Generate title like 'Premium by region and product line'."""
    if secondary_dim:
        return f"{metric_label} by {dim_name} and {secondary_dim}"
    return f"{metric_label} by {dim_name}"


def _pluralize(word: str) -> str:
    """Simple English pluralization for dimension names."""
    lower = word.lower()
    if lower.endswith(("s", "sh", "ch", "x", "z")):
        return word + "es"
    if lower.endswith("y") and lower[-2] not in "aeiou":
        return word[:-1] + "ies"
    return word + "s"


def _ranking_title(dim_name: str, metric_label: str) -> str:
    """Generate title like 'Top agencies by premium'."""
    return f"Top {_pluralize(dim_name)} by {metric_label}"


def _dual_axis_title(primary_label: str, secondary_label: str) -> str:
    """Generate title like 'Participation Rate vs Redemption Rate'."""
    return f"{primary_label} vs {secondary_label}"


# ── Dashboard plan ───────────────────────────────────────────────────────────

class DashboardComponent:
    """A single component in the composed dashboard."""

    def __init__(self, component_type: str, *, title: str, subtitle: str = "",
                 width: str = "half", story_role: str = "",
                 viz_template: str = "", field_map: Dict[str, str] = None,
                 metric_configs: List[Dict] = None, extra: Dict = None):
        self.component_type = component_type
        self.title = title
        self.subtitle = subtitle
        self.width = width  # "full", "half", "third"
        self.story_role = story_role
        self.viz_template = viz_template
        self.field_map = field_map or {}
        self.metric_configs = metric_configs or []
        self.extra = extra or {}

    def __repr__(self):
        w = {"full": "━" * 52, "half": "━" * 25, "third": "━" * 16}
        return f"[{self.component_type}:{self.width}] {self.title}"


class DashboardPlan:
    """Complete dashboard composition: rows of components + layout metadata."""

    def __init__(self, title: str, subtitle: str, rows: List[List[DashboardComponent]],
                 brand: Dict[str, str] = None, company: str = ""):
        self.title = title
        self.subtitle = subtitle
        self.rows = rows
        self.brand = brand or {}
        self.company = company

    @property
    def all_components(self) -> List[DashboardComponent]:
        return [c for row in self.rows for c in row]

    @property
    def viz_components(self) -> List[DashboardComponent]:
        return [c for c in self.all_components if c.component_type != "kpi_row"]

    @property
    def metric_components(self) -> List[DashboardComponent]:
        return [c for c in self.all_components if c.component_type == "kpi_row"]

    def ascii_preview(self, width: int = 72) -> str:
        """Render an ASCII grid preview of the dashboard layout."""
        lines = []
        border = "┌" + "─" * (width - 2) + "┐"
        bottom = "└" + "─" * (width - 2) + "┘"
        sep_full = "├" + "─" * (width - 2) + "┤"

        lines.append(border)
        # Title bar
        title_line = f"  {self.title}"
        lines.append(f"│{title_line:<{width-2}}│")
        if self.subtitle:
            sub_line = f"  {self.subtitle}"
            lines.append(f"│{sub_line:<{width-2}}│")
        lines.append(sep_full)

        for row_idx, row in enumerate(self.rows):
            row_lines = self._render_row(row, width - 2)
            for rl in row_lines:
                lines.append(f"│{rl}│")
            if row_idx < len(self.rows) - 1:
                lines.append(sep_full)

        lines.append(bottom)
        return "\n".join(lines)

    def _render_row(self, row: List[DashboardComponent], inner_width: int) -> List[str]:
        """Render one row of components as ASCII lines."""
        if not row:
            return []

        if len(row) == 1 and row[0].component_type == "kpi_row":
            return self._render_kpi_row(row[0], inner_width)

        # Calculate column widths
        widths = []
        gap = 2
        total_gaps = (len(row) - 1) * gap
        usable = inner_width - total_gaps
        for c in row:
            if c.width == "full":
                widths.append(usable)
            elif c.width == "third":
                widths.append(usable // 3)
            else:
                widths.append(usable // len(row))

        # Adjust last width to fill
        used = sum(widths) + total_gaps
        if used < inner_width:
            widths[-1] += inner_width - used

        lines = []

        # Component boxes
        top_parts = []
        for w in widths:
            top_parts.append("┌" + "─" * (w - 2) + "┐")
        lines.append(("  ").join(top_parts))

        # Icon + role
        role_parts = []
        icons = {
            "trend_line": "📉", "change_bar": "📊", "breakdown_bar": "📊",
            "multi_line": "📈", "ranking_bar": "📋", "donut": "🍩",
            "dual_axis": "📉📊", "detail_table": "📋",
        }
        for i, c in enumerate(row):
            icon = icons.get(c.component_type, "📊")
            role_label = c.story_role.replace("_", " ").title() if c.story_role else ""
            role_str = f" {icon} {role_label}"
            role_parts.append(f"│{role_str:<{widths[i]-2}}│")
        lines.append(("  ").join(role_parts))

        # Title (may wrap)
        title_parts = []
        for i, c in enumerate(row):
            tw = widths[i] - 4
            wrapped = textwrap.wrap(f'"{c.title}"', tw) if tw > 5 else [c.title[:tw]]
            title_parts.append((wrapped, widths[i]))

        max_title_lines = max(len(tp[0]) for tp in title_parts)
        for line_idx in range(max_title_lines):
            parts = []
            for wrapped_lines, w in title_parts:
                if line_idx < len(wrapped_lines):
                    text = wrapped_lines[line_idx]
                else:
                    text = ""
                parts.append(f"│ {text:<{w-3}}│")
            lines.append(("  ").join(parts))

        # Template/chart type
        tmpl_parts = []
        for i, c in enumerate(row):
            tmpl_str = f" [{c.viz_template or c.component_type}]"
            tmpl_parts.append(f"│{tmpl_str:<{widths[i]-2}}│")
        lines.append(("  ").join(tmpl_parts))

        # Bottom
        bot_parts = []
        for w in widths:
            bot_parts.append("└" + "─" * (w - 2) + "┘")
        lines.append(("  ").join(bot_parts))

        return lines

    def _render_kpi_row(self, comp: DashboardComponent, inner_width: int) -> List[str]:
        """Render the KPI metrics row."""
        metrics = comp.metric_configs
        n = len(metrics)
        if n == 0:
            return []

        gap = 2
        total_gaps = (n - 1) * gap
        tile_w = max(8, (inner_width - total_gaps) // n)

        lines = []
        # Top border
        tops = []
        for i in range(n):
            w = tile_w if i < n - 1 else inner_width - (n - 1) * (tile_w + gap)
            tops.append("┌" + "─" * (w - 2) + "┐")
        lines.append(("  ").join(tops))

        # Metric label
        labels = []
        for i, mc in enumerate(metrics):
            w = tile_w if i < n - 1 else inner_width - (n - 1) * (tile_w + gap)
            label = mc.get("label", "Metric")
            labels.append(f"│ {label[:w-4]:<{w-3}}│")
        lines.append(("  ").join(labels))

        # Placeholder value
        vals = []
        for i, mc in enumerate(metrics):
            w = tile_w if i < n - 1 else inner_width - (n - 1) * (tile_w + gap)
            placeholder = "XX.X%" if _looks_like_rate(mc) else "$X.XM"
            direction = _infer_signal_direction(mc)
            arrow = "▼" if direction == "down" else "▲"
            val_str = f" {placeholder}  {arrow} vs prior"
            vals.append(f"│{val_str[:w-2]:<{w-2}}│")
        lines.append(("  ").join(vals))

        # Bottom
        bots = []
        for i in range(n):
            w = tile_w if i < n - 1 else inner_width - (n - 1) * (tile_w + gap)
            bots.append("└" + "─" * (w - 2) + "┘")
        lines.append(("  ").join(bots))

        return lines


# ── Composer: story config → DashboardPlan ───────────────────────────────────

def compose_dashboard(
    *,
    company: str,
    use_case_label: str,
    metric_configs: List[Dict[str, Any]],
    dimensions: List[str],
    dimension_values: Dict[str, List[str]] = None,
    story: Dict[str, Any] = None,
    brand: Dict[str, str] = None,
    signal_direction: str = "down",
    signal_months: int = 6,
    max_kpi_metrics: int = 4,
    max_vizzes: int = 5,
) -> DashboardPlan:
    """Compose a story-driven dashboard plan from the demo configuration.

    Analyzes the story arc and selects chart components that answer:
    1. What's wrong? (KPI row + trend line)
    2. Where is it worst? (change bar or multi-line)
    3. Why is it happening? (stacked breakdown bar)
    4. Who is at risk? (ranking bar)
    5. How do metrics relate? (dual-axis, optional)

    Returns a DashboardPlan with ASCII preview and build specs.
    """
    dimension_values = dimension_values or {}
    story = story or {}
    brand = brand or {}

    primary = _pick_primary_metric(metric_configs)
    supporting = _pick_supporting_metrics(metric_configs, primary)
    direction = signal_direction

    worst_segment = story.get("worst_segment")
    where_dim = story.get("where_dimension") or _pick_where_dimension(dimensions, dimension_values, worst_segment)
    why_dim = story.get("why_dimension") or _pick_why_dimension(dimensions, where_dim)
    who_dim = story.get("who_dimension") or _pick_who_dimension(dimensions, where_dim, why_dim)

    if not worst_segment and where_dim and where_dim in dimension_values:
        worst_segment = dimension_values[where_dim][0] if dimension_values[where_dim] else None

    rows: List[List[DashboardComponent]] = []

    # ── Row 0: KPI stat tiles ────────────────────────────────────────────
    kpi_metrics = [primary] + supporting[:max_kpi_metrics - 1]
    rows.append([DashboardComponent(
        "kpi_row",
        title="Key Metrics",
        width="full",
        story_role="overview",
        metric_configs=kpi_metrics,
    )])

    # ── Row 1: Hero trend + where breakdown ──────────────────────────────
    hero = DashboardComponent(
        "trend_line",
        title=_trend_title(primary["label"], direction, signal_months),
        subtitle=f'{primary["label"]}, last {signal_months * 4} weeks' if primary.get("is_rate") else f'{primary["label"]} by month, last {signal_months * 4} weeks',
        width="half",
        story_role="whats_wrong",
        viz_template="trend_over_time",
        field_map={"measure": primary["field"], "date": "date"},
    )

    if where_dim:
        where_chart = DashboardComponent(
            "change_bar",
            title=_change_title(worst_segment, where_dim, primary["label"], direction),
            subtitle=f'Change in {primary["label"]} by {where_dim}, last month vs prior',
            width="half",
            story_role="where",
            viz_template="horizontal_bar",
            field_map={"category": where_dim, "amount": primary["field"]},
            extra={"show_change": True, "worst_segment": worst_segment},
        )
        rows.append([hero, where_chart])
    else:
        hero.width = "full"
        rows.append([hero])

    # ── Row 2: Why breakdown + ranking/composition ───────────────────────
    row2 = []
    viz_count = 2  # hero + where already

    if why_dim and viz_count < max_vizzes:
        row2.append(DashboardComponent(
            "breakdown_bar",
            title=_breakdown_title(primary["label"], where_dim or dimensions[0], why_dim),
            subtitle=f'{primary["label"]} last month',
            width="half",
            story_role="why",
            viz_template="stacked_bar",
            field_map={
                "category": where_dim or dimensions[0],
                "amount": primary["field"],
                "stack_dim": why_dim,
            },
        ))
        viz_count += 1

    if who_dim and viz_count < max_vizzes:
        row2.append(DashboardComponent(
            "ranking_bar",
            title=_ranking_title(who_dim, primary["label"]),
            subtitle=f'{primary["label"]} last month',
            width="half",
            story_role="who",
            viz_template="horizontal_bar",
            field_map={"category": who_dim, "amount": primary["field"]},
        ))
        viz_count += 1

    if not row2 and supporting and viz_count < max_vizzes:
        row2.append(DashboardComponent(
            "donut",
            title=f'{primary["label"]} distribution',
            width="half",
            story_role="composition",
            viz_template="donut",
            field_map={"category": dimensions[0] if dimensions else "", "amount": primary["field"]},
        ))
        viz_count += 1

    if len(row2) == 1:
        # Fill the other half with a supporting metric view
        if supporting and viz_count < max_vizzes:
            sec = supporting[0]
            row2.append(DashboardComponent(
                "multi_line" if where_dim else "trend_line",
                title=f'{sec["label"]} by {where_dim}' if where_dim else _trend_title(sec["label"], direction, signal_months),
                width="half",
                story_role="supporting",
                viz_template="multi_series_line" if where_dim else "trend_over_time",
                field_map={
                    "measure": sec["field"],
                    "date": "date",
                    **({"color_dim": where_dim} if where_dim else {}),
                },
            ))
            viz_count += 1

    if row2:
        rows.append(row2)

    # ── Row 3 (optional): Dual-axis leading indicator ────────────────────
    if len(supporting) >= 1 and viz_count < max_vizzes:
        lead = supporting[0]
        if lead.get("is_rate") or "rate" in lead.get("field", "").lower():
            rows.append([DashboardComponent(
                "dual_axis",
                title=_dual_axis_title(primary["label"], lead["label"]),
                subtitle="Leading indicator relationship",
                width="full",
                story_role="supporting",
                viz_template="dual_axis",
                field_map={
                    "date": "date",
                    "bar_measure": primary["field"],
                    "line_measure": lead["field"],
                },
            )])
            viz_count += 1

    # ── Build the plan ───────────────────────────────────────────────────
    dash_title = f"{company} — {use_case_label}"
    dash_subtitle = story.get("subtitle", f"What changed and where?")

    return DashboardPlan(
        title=dash_title,
        subtitle=dash_subtitle,
        rows=rows,
        brand=brand,
        company=company,
    )


# ── Grid layout calculator ──────────────────────────────────────────────────

def plan_to_grid_layout(
    plan: DashboardPlan,
    *,
    grid_columns: int = 72,
    row_height: int = 10,
    kpi_height: int = 19,
    viz_height: int = 40,
    gap_rows: int = 2,
    col_gap: int = 2,
) -> Dict[str, Any]:
    """Convert a DashboardPlan into a concrete grid layout (row/col/span positions).

    Returns a dict with:
      - 'grid': columnCount, rowHeight, style
      - 'components': list of {component, position: {row, column, rowspan, colspan}}
    """
    positioned = []
    current_row = 1  # start with a 1-row top margin

    for row_components in plan.rows:
        if not row_components:
            continue

        comp = row_components[0]

        if comp.component_type == "kpi_row":
            # KPI tiles
            n = len(comp.metric_configs)
            tile_width = (grid_columns - col_gap * 2 - (n - 1) * col_gap) // n
            for i, mc in enumerate(comp.metric_configs):
                col = col_gap + i * (tile_width + col_gap)
                w = tile_width
                if i == n - 1:
                    w = grid_columns - col_gap - col
                positioned.append({
                    "component": DashboardComponent(
                        "kpi_tile",
                        title=mc["label"],
                        width="tile",
                        story_role="overview",
                        metric_configs=[mc],
                    ),
                    "position": {
                        "row": current_row,
                        "column": col,
                        "rowspan": kpi_height,
                        "colspan": w,
                    },
                })
            current_row += kpi_height + gap_rows
        else:
            # Viz components
            n = len(row_components)
            usable_cols = grid_columns - col_gap * 2 - (n - 1) * col_gap
            if n == 1:
                widths = [usable_cols]
            elif n == 2:
                widths = [usable_cols // 2, usable_cols - usable_cols // 2]
            else:
                base = usable_cols // n
                widths = [base] * n
                widths[-1] = usable_cols - base * (n - 1)

            col_cursor = col_gap
            for i, c in enumerate(row_components):
                positioned.append({
                    "component": c,
                    "position": {
                        "row": current_row,
                        "column": col_cursor,
                        "rowspan": viz_height,
                        "colspan": widths[i],
                    },
                })
                col_cursor += widths[i] + col_gap

            current_row += viz_height + gap_rows

    bg_color = plan.brand.get("chart_bg", "#F3F3F3")
    gutter_color = plan.brand.get("gutter", "#FFFFFF")

    return {
        "grid": {
            "columnCount": grid_columns,
            "rowHeight": row_height,
            "maxWidth": 1200,
            "style": {
                "backgroundColor": bg_color,
                "gutterColor": gutter_color,
                "cellSpacingX": 0,
                "cellSpacingY": 0,
            },
        },
        "total_rows": current_row,
        "components": positioned,
    }


# ── Build spec emitter ──────────────────────────────────────────────────────

def plan_to_build_specs(plan: DashboardPlan) -> List[Dict[str, Any]]:
    """Convert a DashboardPlan into build specs.

    Returns a list of dicts, each with:
      - 'viz_name': API-safe name for the viz
      - 'viz_label': narrative display title
      - 'template_name': viz_templates key (trend_over_time, horizontal_bar, etc.)
      - 'field_map': {template_slot: raw_field_name_or_dim_label}
        The field_map uses the metric `field` names and dimension labels
        from METRIC_CONFIG/DIMENSIONS — the build script resolves these
        to SDM apiNames using its own dim_field_map / measurement_map.
      - 'story_role': which story question this viz answers
      - 'width': layout hint (full/half)
      - 'component': the original DashboardComponent
    """
    specs = []

    for comp in plan.viz_components:
        if not comp.viz_template:
            continue

        safe_name = comp.title.lower()
        for ch in " /&—–-'\"(),.!?":
            safe_name = safe_name.replace(ch, "_")
        safe_name = safe_name.strip("_")[:50]
        while "__" in safe_name:
            safe_name = safe_name.replace("__", "_")

        specs.append({
            "viz_name": safe_name,
            "viz_label": comp.title,
            "template_name": comp.viz_template,
            "field_map": dict(comp.field_map),
            "story_role": comp.story_role,
            "width": comp.width,
            "component": comp,
        })

    return specs


# ── Quick test / demo ────────────────────────────────────────────────────────

def demo_compose():
    """Run a demo composition with sample BIW-like config."""
    metrics = [
        {"label": "Participation Rate", "field": "participation_rate", "agg": "Average", "is_rate": True,
         "sentiment": "SentimentTypeUpIsGood"},
        {"label": "Goal Achievement Rate", "field": "goal_achievement_rate", "agg": "Average", "is_rate": True,
         "sentiment": "SentimentTypeUpIsGood"},
        {"label": "Redemption Rate", "field": "redemption_rate", "agg": "Average", "is_rate": True,
         "sentiment": "SentimentTypeUpIsGood"},
        {"label": "Points Per Rep", "field": "points_per_rep", "agg": "Average", "is_rate": False,
         "sentiment": "SentimentTypeUpIsGood"},
        {"label": "Active Reps", "field": "active_reps", "agg": "Sum", "is_rate": False,
         "sentiment": "SentimentTypeUpIsGood"},
    ]
    dims = ["Program Type", "Region", "Size Band", "Vertical"]
    dim_vals = {
        "Region": ["West", "Northeast", "Midwest", "South", "Southwest"],
        "Program Type": ["Sales Contest", "Quota Attainment", "Channel Partner", "President's Club"],
        "Size Band": ["Small Enterprise", "Mid-Market", "Large Enterprise", "Global"],
        "Vertical": ["Financial Services", "Automotive", "Technology", "Insurance"],
    }
    story = {
        "worst_segment": "Northeast",
        "subtitle": "What changed, and where?",
    }

    plan = compose_dashboard(
        company="BI Worldwide",
        use_case_label="Sales Incentive Performance",
        metric_configs=metrics,
        dimensions=dims,
        dimension_values=dim_vals,
        story=story,
        signal_direction="down",
        signal_months=6,
    )

    print(plan.ascii_preview())
    print()
    print(f"Components: {len(plan.all_components)}")
    print(f"  KPI tiles: {sum(len(c.metric_configs) for c in plan.metric_components)}")
    print(f"  Vizzes: {len(plan.viz_components)}")
    print()
    for spec in plan_to_build_specs(plan):
        print(f"  [{spec['story_role']:12s}] {spec['template_name']:20s} → {spec['viz_label']}")
        for slot, field in spec['field_map'].items():
            print(f"               {slot:15s} = {field}")


if __name__ == "__main__":
    demo_compose()
