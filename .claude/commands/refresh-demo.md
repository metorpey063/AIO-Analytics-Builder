# /refresh-demo — Upgrade Legacy Demos to Self-Healing

Upgrades legacy demos to the self-healing Display Date formula. **New demos built after May 2026 never need this** — both Tableau Next and Pulse are self-healing out of the box.

---

## Background

**All new demos are self-healing** — both platforms use `DATEDIFF`/`TODAY()` formulas that evaluate at query time:

- **Tableau Next**: SDM calculated dimension — `DATEADD("day", DATEDIFF("day", #<build_date>#, [DO].[date_field]), TODAY())`
- **Tableau Pulse**: `.tdsx` calculated field — `DATEADD('day', DATEDIFF('day', #<build_date>#, [Date]), TODAY())`

The most recent data always appears as "today" with no manual intervention.

**This skill is only needed for legacy demos** that used the old static-offset approach:
1. **Tableau Next** — old formula: `DATEADD("day", <N>, [DO].[date_field])` with a hardcoded integer
2. **Tableau Pulse** — raw `.hyper` published without a Display Date calculated field

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

List all demos that have a checkpoint file with a `display_date_api` key:

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
        is_self_healing = cp.get('self_healing_date', False)
        status = 'self-healing ✓' if is_self_healing else 'legacy (static offset)'
        print(f'  [{slug}]  built: {build_date}  status: {status}  sdm: {cp[\"sdm_api\"]}')
        found.append((slug, is_self_healing))
if not found:
    print('  No refreshable demos found.')
    print('  Demos must be built with display_date support to use /refresh-demo.')
"
```

- If no demos are found, tell the user: *"No refreshable demos found. Demos need to be built (or rebuilt) to gain date support."*
- If the selected demo is already self-healing, tell the user: *"This demo is already self-healing — the Display Date dimension automatically stays current. No action needed for Tableau Next. Would you like to refresh the Pulse datasource instead?"*
- If the selected demo uses the legacy static-offset formula, proceed to Step 2 to upgrade it.

---

## Step 2 — Upgrade to self-healing formula (legacy demos only)

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

sdm_api          = cp['sdm_api']
do_api           = cp['do_api']
display_date_api = cp['display_date_api']
date_field_api   = cp['date_field_api']
build_date       = cp['build_date']

BASE = f'{sf_instance}/services/data/v65.0'

# GET current calculated dimension to confirm it exists
r = requests.get(f'{BASE}/ssot/semantic/models/{sdm_api}/calculated-dimensions/{display_date_api}',
                 headers=sf_h)
if r.status_code != 200:
    print(f'ERROR: calculated dimension not found: {r.status_code} {r.text[:200]}')
    sys.exit(1)

# PUT self-healing expression
new_expr = f'DATEADD(\"day\", DATEDIFF(\"day\", #{build_date}#, [{do_api}].[{date_field_api}]), TODAY())'
payload = {
    'apiName': display_date_api,
    'label': 'Display Date',
    'expression': new_expr,
    'dataType': 'Date',
}
r = requests.put(f'{BASE}/ssot/semantic/models/{sdm_api}/calculated-dimensions/{display_date_api}',
                 headers=sf_h, json=payload)
if r.status_code in (200, 201):
    print(f'OK: Display Date upgraded to self-healing formula')
    print(f'Expression: {new_expr}')
else:
    print(f'ERROR: {r.status_code} {r.text[:300]}')
    sys.exit(1)

# Mark as self-healing in checkpoint
cp['self_healing_date'] = True
cp.pop('display_date_offset_days', None)  # no longer needed
with open(f'demos/{slug}/{slug}_checkpoint.json', 'w') as f:
    json.dump(cp, f, indent=2)
print('Checkpoint updated — demo is now self-healing.')
"
```

- If successful: tell the user *"Done — the Display Date dimension is now self-healing. The demo will always show the signal as current, no further refreshes needed for Tableau Next."*
- If the calculated dimension is missing: offer to recreate it with POST, then re-point metrics at it using `{"calculatedFieldApiName": "Display_Date"}`.

---

## Step 3 — Verify

> "Open the demo in Tableau Next and check the most recent date on the trend line — it should now show data up to around today. Does it look right?"

If they say no, diagnose:
- Check whether the metric's time dimension is pointing at `Display Date` (the calculated dim) vs the raw `date` field. If it's pointing at the raw field, the update won't be visible in metrics.
- Offer to update each metric's `timeDimensionReference` to `{"calculatedFieldApiName": "Display_Date"}`.

---

## Step 4 — Pulse upgrade (legacy demos only)

If the demo also has Pulse output (`pulse_done: true` in checkpoint) AND was built before the `.tdsx` self-healing pattern was introduced (no `Display Date` calculated field in the published datasource):

> "This demo has a legacy Pulse datasource (raw .hyper without a Display Date calculated field). Would you like me to re-package it as a .tdsx with the self-healing formula and re-publish?"

If yes:
1. Write a `.tds` XML with the Display Date calc field: `DATEADD('day', DATEDIFF('day', #<build_date>#, [Date]), TODAY())`
2. Package the existing `.hyper` + new `.tds` into a `.tdsx`
3. Re-publish the `.tdsx` (overwrite the existing datasource)
4. Update Pulse metric definitions to use `"time_dimension": {"field": "Display Date"}` instead of `"Date"`

If no: skip and finish.

**Note:** Demos built after this update already publish as `.tdsx` with the self-healing formula — they never need this step.

---

## Notes

- **New demos are self-healing by default** — both Tableau Next and Pulse use `DATEDIFF`/`TODAY()` formulas that evaluate at query time. No refresh is ever needed.
- This skill's primary purpose is now **upgrading legacy demos** that used the old `DATEADD("day", <N>, ...)` static-offset pattern (Tableau Next) or raw `.hyper` without a Display Date calc field (Pulse).
- **Pulse self-healing works via .tdsx**: the `.tdsx` contains a `.tds` XML with the calculated field. Tableau Cloud evaluates `TODAY()` at query time because "unstable functions" are excluded from extract materialization.
- If the underlying data is genuinely too old (e.g. more than 24 months since build and the demo uses 24-month history), the signal will still appear but history will look truncated. A full rebuild is needed in that case.
- Date literal syntax uses `#YYYY-MM-DD#` (hash-delimited) in both Tableau calc fields and SDM expressions. The `DATE(year, month, day)` function does NOT accept 3 arguments in SDM expressions.
