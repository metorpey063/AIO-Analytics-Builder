# Build Specs — Q1–Q4 + Dashboard

Each spec is declarative: build it with your native authoring tools. `{braces}` are the story fields mapped in Step 1. Use the exact datasource field names, not the story's spelling.

## Shared formatting

| Item | Value |
|------|-------|
| Primary color | `#4472C4` |
| Culprit highlight | `#E74C3C` (red) |
| Counter-trend highlight | `#F39C12` (orange) |
| Other segments | `#95A5A6` (gray) |
| Text | `#2E2E2E` |
| Rate/percentage measures | Percentage, 1 decimal (values are stored as decimals, e.g. 0.62 = 62%) |
| Currency measures | Currency, 0 decimals, K/M units if values exceed 10,000 |
| Counts | Number, 0 decimals, thousands separator |
| Date axis | Month granularity, continuous, chronological |

If `demo-story.md` includes brand colors, use the brand primary in place of `#4472C4`. Keep the red, orange, and gray story colors as they are, because they carry the narrative.

---

## Q1 — What Is Wrong

**Purpose:** within 10 seconds the audience can see the primary metric moving the wrong way.

| Property | Spec |
|----------|------|
| Sheet name | `Q1 — What Is Wrong` |
| Mark | Line |
| Columns | `{date}` — continuous MONTH |
| Rows | `{primary_metric}` — AVG or SUM per Step 1 |
| Color | Single, primary color; line weight slightly thicker than default |
| Filter | None (all data) |
| Title | `{primary_metric} — {direction} since {onset month}` (e.g. "Revenue Realization Rate — declining since May"). If the onset is unknown, use `{primary_metric} Over Time` |
| Number format | Per shared formatting |

**Done when:** one line, roughly 24 monthly points, and the decline (or rise) toward the right edge is visible.

---

## Q2 — Where Is It Worst

**Purpose:** show the problem is concentrated in one segment, and that the counter-trend segment is masking it.

| Property | Spec |
|----------|------|
| Sheet name | `Q2 — Where Is It Worst` |
| Mark | Bar (horizontal) |
| Rows | `{segment_dimension}` |
| Columns | `{primary_metric}` — same aggregation as Q1 |
| Filter | `{date}` limited to the **most recent 3 months**, so the bars show the current state rather than a 24-month average that dilutes the signal |
| Sort | `{segment_dimension}` by `{primary_metric}`, worst first. For "up is good" metrics, worst = lowest, so sort ascending. For "down is good" metrics, sort descending |
| Color | Color by `{segment_dimension}`. Assign `{culprit}` = red, `{counter_trend}` = orange, every other value = gray |
| Labels | Show mark labels with the metric value |
| Title | `{primary_metric} by {segment_dimension} — {culprit} is worst` |

**Done when:** the culprit bar is red and at the top, the counter-trend bar is orange, and all others are gray.

---

## Q3 — Why Is It Happening

**Purpose:** the supporting (leading) metrics moved first, and that explains the cause.

**Variant A (default, when the story has supporting metrics):**

| Property | Spec |
|----------|------|
| Sheet name | `Q3 — Why Is It Happening` |
| Mark | Line |
| Columns | `{date}` — continuous MONTH |
| Rows | Up to 3 `{supporting_metrics}`. Use **Measure Values** with a Measure Names color legend if they share a scale (e.g. all rates). Otherwise use separate rows/axes |
| Filter | `{segment_dimension}` = `{culprit}` (the "why" for the worst segment) |
| Color | Measure Names, default categorical palette |
| Title | `What moved first — {culprit}` |

**Variant B (no supporting metrics, or they don't exist in the datasource):** a line chart of `{primary_metric}` by MONTH, colored by `{root_cause_dimension}`, filtered to `{culprit}`. Title: `{primary_metric} by {root_cause_dimension} — {culprit}`.

**Done when:** at least one supporting line starts falling before the primary metric did in Q1, or the root-cause lines visibly diverge.

---

## Q4 — Who Needs Action

**Purpose:** a concrete list the audience could act on tomorrow.

| Property | Spec |
|----------|------|
| Sheet name | `Q4 — Who Needs Action` |
| Mark | Square (highlight table) |
| Rows | `{entity_field}` (e.g. Account Name, Client, Location) |
| Columns | Measure Names: `{primary_metric}` plus up to 2 `{supporting_metrics}` |
| Text | Measure Values |
| Color | Measure Values, diverging red (worst) → green (best), oriented so that worst = red for the primary metric's direction |
| Filters | `{segment_dimension}` = `{culprit}`; `{date}` = most recent 3 months; **Top 20** `{entity_field}` by `{primary_metric}`, worst first |
| Sort | `{entity_field}` by `{primary_metric}`, worst first |
| Title | `Top 20 at-risk {entity_field} — {culprit}` |

**Done when:** at most 20 rows, all from the culprit segment, with the worst at the top in red.

---

## Dashboard

| Property | Spec |
|----------|------|
| Name | `{Company} — AiO Story` |
| Title | `{Company} — {story headline}` (from `demo-story.md`, or `{primary_metric}: what's wrong, where, why, who`) |
| Size | Automatic, or fixed 1200 × 800 |
| Layout | Tiled 2×2: top-left Q1, top-right Q2, bottom-left Q3, bottom-right Q4 |
| Background | `#F3F3F3`, with a small inner padding on each sheet |
| Worksheet titles | Show on each tile |
| Filter action (optional, nice-to-have) | Selecting a bar in Q2 filters Q3 and Q4 to that segment |

**Done when:** all four sheets render in reading order, none is blank, and nothing is cut off.
