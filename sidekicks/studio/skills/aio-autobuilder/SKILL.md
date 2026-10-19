---
name: aio-autobuilder
description: Auto-build the complete four-question AiO demo (Q1–Q4 worksheets + story dashboard) on the connected datasource. Prompts: "build the demo", "auto-create Q1-Q4", "auto-build the story dashboard".
---

# AiO Auto-Builder

Build all four AiO story worksheets and the story dashboard in one pass, hands-off, on the datasource the user has connected. The user reviews the result; they do not click through each step.

**Scope:** this skill builds Studio worksheets and a dashboard only. It does not generate data or create Pulse metrics / Tableau Next assets — those come from `/build-demo` in Claude Code.

## Ground rules

- **Use your native worksheet, dashboard, and save tools.** Do NOT write Python, shell scripts, or raw HTTP calls to the External Client API to do this — your built-in authoring tools already do it faster and more reliably.
- **Never invent field names.** Every field you place must exist in the connected datasource (Step 1 mapping).
- **Verify every sheet before moving on** (see `references/verification.md`). A tool call that returns success is not proof the chart is right.
- **Don't stop to ask questions mid-build** unless Step 1 fails. Confirm once up front, then build all the way through.

## Step 0 — Load the story

Look for `references/demo-story.md` next to this skill.
- **If present:** read it. It defines the company, primary metric, dimensions, culprit segment(s), counter-trend segment, root-cause dimension, supporting metrics, and the at-risk entity field.
- **If absent:** standalone session. Ask the user once for: primary metric, the dimension where the problem concentrates, the culprit value, the counter-trend value, root-cause dimension, 1–3 supporting metrics, and the entity field for the at-risk list (e.g. Account Name). Offer your best guesses from the datasource fields so they can just confirm.

## Step 1 — Preflight (stop here if it fails)

1. Confirm a datasource is connected. If none, tell the user to connect one (e.g. the demo's CSV or published `.hyper`) and stop.
2. List the datasource fields. Map every story field (primary metric, supporting metrics, date, segment dimension, root-cause dimension, entity field) to an exact datasource field name. Match case-insensitively and ignore spaces/underscores (`approval_rate` ↔ `Approval Rate`).
3. Check that the culprit and counter-trend **values** exist in the segment dimension.
4. Decide each measure's aggregation: rates, percentages, scores, averages → **AVG**; counts, revenue, volumes → **SUM**. If `demo-story.md` states an aggregation, use it.
5. Print a one-screen build plan (mapped fields + aggregations + the four sheets) and say "Building now." If anything required is unmapped, list it and stop — do not guess.

## Steps 2–5 — Build Q1–Q4

Build each worksheet exactly per its spec in `references/build-specs.md`. For each one:
1. Create a new worksheet with the spec's name.
2. Place fields, set mark type, aggregation, colors, sort, filters, number format, and title per the spec.
3. Verify it (`references/verification.md`). Fix and re-verify once if needed.
4. Print a one-line status, e.g. `✓ Q2 — Where Is It Worst (bar, culprit highlighted)`.

| Step | Sheet | Chart |
|------|-------|-------|
| 2 | Q1 — What Is Wrong | Line: primary metric by month |
| 3 | Q2 — Where Is It Worst | Horizontal bar: primary metric by segment dimension, culprit red, counter-trend orange |
| 4 | Q3 — Why Is It Happening | Multi-line: supporting metrics by month (or primary metric by root-cause dimension if there are no supporting metrics) |
| 5 | Q4 — Who Needs Action | Highlight table: top 20 entities in the culprit segment, worst first |

## Step 6 — Dashboard

Create the dashboard per the **Dashboard** spec in `references/build-specs.md`: title `{Company} — {Story headline}`, 2×2 tiled grid in reading order Q1 → Q2 → Q3 → Q4. Verify that all four sheets are on it and none are blank.

## Step 7 — Save and report

Save the workbook. Then print:

```
✓ AiO demo built — {Company}
  Q1  {title}   (line)
  Q2  {title}   (bar — {culprit} red, {counter-trend} orange)
  Q3  {title}   (multi-line)
  Q4  {title}   (top 20 {entity} in {culprit})
  Dashboard: {dashboard name}

Anything skipped or adjusted: {list, or "none"}

Next: click into each sheet to tweak, then try "explain this chart" (aio-audience) to rehearse the story.
```

Be honest in "skipped or adjusted". If a sheet couldn't be built to spec, say what's different.

## References

- `references/demo-story.md` — this demo's story (only present for `/build-demo` installs)
- `references/build-specs.md` — exact spec for Q1–Q4 and the dashboard
- `references/verification.md` — how to check each sheet and recover from failures
