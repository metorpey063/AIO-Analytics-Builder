# /refresh-demo — Keep Demo Data Current

Updates the date offset on an existing Tableau Next demo so the signal always appears to be happening "right now", regardless of when the demo was originally built.

---

## How it works

When a demo is built, all dates are generated up to today. Three months later, the most recent data point is three months in the past — the signal looks stale. This skill fixes that by updating a single calculated dimension (`Display Date`) on the Semantic Data Model:

```
DATEADD("day", <offset>, [FactTable].[date])
```

The offset is the number of days between the original build date and today. Updating it takes one API call and requires no data re-ingestion.

**Result:** The signal always looks like it started declining in the last few weeks, no matter when the demo is shown.

---

## Step 0 — Update check

Run:
```bash
git fetch origin main 2>/dev/null && git rev-list HEAD..origin/main --count
```
- If result is `0` — skip silently.
- If result is **1 or more** — tell the user an update is available and ask if they want to pull before continuing.

---

## Step 1 — Select a demo to refresh

List all demos that have a checkpoint file with a `display_date_api` key (meaning they were built with date-offset support):

```bash
python3 -c "
import os, json, glob

demos_dir = 'demos'
found = []
for cp_path in glob.glob(f'{demos_dir}/*/*.json'):
    if not cp_path.endswith('_checkpoint.json'):
        continue
    with open(cp_path) as f:
        cp = json.load(f)
    if cp.get('display_date_api') and cp.get('sdm_api'):
        slug = os.path.basename(os.path.dirname(cp_path))
        build_date = cp.get('build_date', 'unknown')
        offset = cp.get('display_date_offset_days', 0)
        print(f'  [{slug}]  built: {build_date}  current offset: +{offset}d  sdm: {cp[\"sdm_api\"]}')
        found.append(slug)
if not found:
    print('  No refreshable demos found.')
    print('  Demos must be built with display_date support to use /refresh-demo.')
"
```

- If no demos are found, tell the user: *"No refreshable demos found. Demos need to be built (or rebuilt) after this feature is added to gain date-offset support."*
- If one demo is found, proceed with it automatically.
- If multiple are found, ask the user which one to refresh.

---

## Step 2 — Compute the new offset

```bash
python3 -c "
import json, os, glob
from datetime import date

slug = 'SLUG_HERE'
cp_path = f'demos/{slug}/{slug}_checkpoint.json'
with open(cp_path) as f:
    cp = json.load(f)

build_date_str = cp.get('build_date')
if not build_date_str:
    print('ERROR: no build_date in checkpoint')
else:
    build_date = date.fromisoformat(build_date_str)
    today = date.today()
    new_offset = (today - build_date).days
    old_offset = cp.get('display_date_offset_days', 0)
    print(f'Build date:   {build_date_str}')
    print(f'Today:        {today}')
    print(f'Old offset:   {old_offset} days')
    print(f'New offset:   {new_offset} days')
    print(f'OFFSET:{new_offset}')
"
```

Parse `OFFSET:<n>` from the output. Tell the user:
> "The demo was built on [build_date]. Today's offset is [n] days — I'll update the Display Date dimension to shift all dates forward by [n] days."

---

## Step 3 — Update the calculated dimension

```bash
python3 -c "
import json, requests, sys
sys.path.insert(0, '.')
from connections import load_config, get_all_tokens

config = load_config()
sf_token, sf_instance, _, _ = get_all_tokens(config)
sf_h = {'Authorization': f'Bearer {sf_token}', 'Content-Type': 'application/json'}

slug = 'SLUG_HERE'
with open(f'demos/{slug}/{slug}_checkpoint.json') as f:
    cp = json.load(f)

sdm_api         = cp['sdm_api']
do_api          = cp['do_api']
display_date_api = cp['display_date_api']
date_field_api  = cp['date_field_api']
new_offset      = OFFSET_HERE

BASE = f'{sf_instance}/services/data/v65.0'

# GET current calculated dimension to confirm it exists
r = requests.get(f'{BASE}/ssot/semantic/models/{sdm_api}/calculated-dimensions/{display_date_api}',
                 headers=sf_h)
if r.status_code != 200:
    print(f'ERROR: calculated dimension not found: {r.status_code} {r.text[:200]}')
    sys.exit(1)

# PUT updated expression
new_expr = f'DATEADD(\"day\", {new_offset}, [{do_api}].[{date_field_api}])'
payload = {
    'apiName': display_date_api,
    'label': 'Display Date',
    'expression': new_expr,
    'dataType': 'Date',
}
r = requests.put(f'{BASE}/ssot/semantic/models/{sdm_api}/calculated-dimensions/{display_date_api}',
                 headers=sf_h, json=payload)
if r.status_code in (200, 201):
    print(f'OK: Display Date updated — offset is now +{new_offset} days')
    print(f'Expression: {new_expr}')
else:
    print(f'ERROR: {r.status_code} {r.text[:300]}')
    sys.exit(1)

# Save new offset to checkpoint
cp['display_date_offset_days'] = new_offset
with open(f'demos/{slug}/{slug}_checkpoint.json', 'w') as f:
    json.dump(cp, f, indent=2)
print('Checkpoint updated.')
"
```

- If successful: tell the user *"Done — the Display Date dimension now shifts all dates forward by [n] days. Your demo will show the signal as current for today."*
- If the calculated dimension is missing (e.g. it was deleted in the UI): offer to recreate it — POST a new one with the same `display_date_api` name, same expression, then update checkpoint.

---

## Step 4 — Verify

Ask the user to open the demo dashboard in Tableau Next and confirm the most recent data point is showing today (or within the last week, depending on data grain).

> "Open the demo in Tableau Next and check the most recent date on the trend line — it should now show data up to around today. Does it look right?"

If they say no, diagnose:
- Check whether the metric's time dimension is pointing at `Display Date` (the calculated dim) vs the raw `date` field. If it's pointing at the raw field, the update won't be visible in metrics — only in vizzes that explicitly use `Display Date`.
- Offer to re-run Phase 7 (metrics) to re-point the time dimension, but warn this will regenerate metric definitions.

---

## Notes

- This skill only updates the **date offset** — it does not re-ingest data, rebuild the SDM, or change metric definitions.
- If the underlying data is genuinely too old (e.g. more than 24 months since build and the demo uses 24-month history), the signal will still be visible but the history will appear truncated. In that case, a full rebuild is needed.
- If the Tableau Pulse datasource also needs refreshing (new .hyper with shifted dates), that requires re-running the Pulse phase. The date offset approach only applies to Tableau Next calculated dimensions.
- Demos built before this feature was added will not have `display_date_api` in their checkpoint — they need to be fully rebuilt to gain refresh support.
