# /refresh-dates — Refresh Pulse Demo Dates

Re-generates data anchored to today and re-publishes the `.hyper` datasource. Pulse metrics survive the overwrite and automatically pick up the fresh data. No metric recreation needed.

**This is for Tableau Pulse demos only.** Tableau Next demos use a self-healing `Display Date` calculated dimension (`DATEADD("day", DATEDIFF("day", #build_date#, ...), TODAY())`) that evaluates at query time — their dates are always current automatically and never need refreshing.

**Use this when:** A Pulse demo was built days or weeks ago and the sparkline dates look stale. Running `/refresh-dates` makes the most recent data appear as "this week" again.

---

## How it works

1. Reads the demo's checkpoint to find the original build parameters (signal config, dimensions, metrics)
2. Regenerates the synthetic data with `TODAY` as the new anchor date
3. Writes a new `.hyper` file
4. Re-publishes to Tableau Cloud (overwrites the existing datasource — same name, same project)
5. Existing Pulse metrics automatically pick up the new data (no deletion/recreation)
6. Updates the checkpoint with the new `build_date`

**What stays the same:** metric definitions, group subscriptions, project, datasource name
**What changes:** the data (shifted to today), the `.hyper` file, the CSV export

---

## Step 0 — Update check

Run:
```bash
git fetch origin main 2>/dev/null && git rev-list HEAD..origin/main --count
```
- If `0` — skip silently.
- If **1 or more** — ask if they want to pull first.

---

## Step 1 — Select demo(s) to refresh

List all demos with a checkpoint:

```bash
python3 -c "
import os, json, glob
from datetime import date

demos_dir = 'demos'
today = date.today()
found = []
for cp_path in sorted(glob.glob(f'{demos_dir}/*_checkpoint.json', recursive=True)):
    # Handle both demos/slug/slug_checkpoint.json patterns
    pass
for cp_path in sorted(glob.glob(f'{demos_dir}/*/*_checkpoint.json')):
    with open(cp_path) as f:
        cp = json.load(f)
    if not cp.get('csv_done'):
        continue
    slug = os.path.basename(os.path.dirname(cp_path))
    build_date = cp.get('build_date', 'unknown')
    days_old = (today - date.fromisoformat(build_date)).days if build_date != 'unknown' else '?'
    pulse_status = '✓ Pulse' if cp.get('pulse_done') else ''
    next_status = '✓ Next' if cp.get('sdm_done') else ''
    print(f'  {slug:45} built: {build_date}  ({days_old}d ago)  {pulse_status}  {next_status}')
    found.append(slug)
if not found:
    print('  No demos found.')
"
```

Then ask:

> "Which demo would you like to refresh? Enter the slug name, or type **all** to refresh everything."

If the user provides a slug directly (e.g. `/refresh-dates biw` or `/refresh-dates bi_worldwide_sales_incentive`), match it against available demos and skip the selection prompt.

---

## Step 2 — Regenerate data

For each selected demo:

1. Read the checkpoint to get build parameters:
   - `SLUG`, `COMPANY`, `DEMO_DIR`
   - Signal parameters from the demo script header (these are constants in the `.py` file)

2. Run the demo script's data generation phase only:
   ```bash
   python3 -c "
   import sys, os, json
   sys.path.insert(0, os.path.join('demos', 'SLUG_HERE', '..', '..'))
   # Execute just the data generation portion of the demo script
   exec(open(os.path.join('demos', 'SLUG_HERE', 'SLUG_HERE_demo.py')).read())
   "
   ```

   **Important:** The demo scripts use `TODAY = date.today()` at the top — simply re-running the data generation produces data anchored to today. The signal onset, magnitude, and shape are all relative to `TODAY`.

3. The script's checkpoint logic will detect `csv_done: True` and skip regeneration. To force regeneration, temporarily set `csv_done: False` in the checkpoint before running:
   ```python
   cp['csv_done'] = False
   cp['pulse_done'] = False  # Force re-publish of .hyper
   # Keep all other flags (sdm_done, metrics_done, etc.) so Next isn't rebuilt
   save_checkpoint(cp)
   ```

---

## Step 3 — Re-publish .hyper

The demo script's Pulse phase handles this:
- Writes a new `.hyper` from the regenerated DataFrame
- Publishes to the SAME datasource name in the SAME project (Overwrite mode)
- Existing Pulse metrics automatically see the new data

**Do NOT recreate metrics, groups, or subscriptions.** They survive the datasource overwrite.

After publish, update the checkpoint:
```python
cp['build_date'] = date.today().isoformat()
cp['csv_path'] = new_csv_path
save_checkpoint(cp)
```

---

## Step 4 — Verify

> "Refresh complete. The data now runs through today. Open Pulse and verify the trend line shows recent data."

Print a summary:
```
  ✓ {slug}
    Data regenerated: {row_count} rows through {today}
    .hyper re-published to: {datasource_name}
    Pulse metrics: {N} (unchanged — using existing definitions)
    Build date updated: {old_date} → {today}
```

---

## Step 5 — Tableau Next (skip by default)

If the demo also has Tableau Next output (`sdm_done: True`), note in the summary:

> "This demo also has Tableau Next assets — those dates are self-healing via the Display Date formula and don't need refreshing."

Do NOT re-ingest to Data Cloud unless the user explicitly asks. The `Display Date` calculated dimension uses `TODAY()` at query time, so Tableau Next dates are always current automatically.

---

## Refreshing "all"

If the user selects **all**:
- Loop through each demo with a checkpoint
- For each: reset `csv_done` + `pulse_done`, run the script, let checkpoint resume handle the rest
- Print a summary table at the end

---

## Notes

- **Metrics survive `.hyper` overwrites** — Pulse definitions persist when the underlying datasource is re-published. No need to delete/recreate.
- **`use_dynamic_offset: true`** is set on all metrics as a safety net — Pulse anchors to the most recent data point even if the demo hasn't been refreshed recently.
- **Frequency:** Refresh before each demo. A demo built the same week is fine; a demo built 2+ weeks ago should be refreshed.
- **Speed:** Refresh is fast (~30 seconds for data gen + publish). No API calls to create/modify metrics.
- **Tableau Next refresh** is optional and takes longer (bulk ingest → DLO processing → ~2-5 min).
