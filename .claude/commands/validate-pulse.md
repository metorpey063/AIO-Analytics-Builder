# /validate-pulse — Validate Pulse API Payloads

Runs every payload variation used by `/build-demo` against the canary Tableau Cloud pod (10ax) to detect breaking API changes before they hit production sites.

**Use this when:** You want to check if the Pulse API has changed (e.g. after a Tableau Cloud release), or before running `/build-demo` on a site you haven't tested recently.

---

## Prerequisites

A `pulse_validation` profile must exist in `config.json`:

```json
{
  "profiles": {
    "pulse_validation": {
      "tableau": {
        "server_url": "https://10ax.online.tableau.com",
        "site_name": "your-canary-site",
        "pat_name": "validator",
        "pat_secret": "..."
      }
    }
  }
}
```

If the profile is missing, print the setup instructions above and ask the user to configure it.

---

## Step 0 — Update check

Run:
```bash
git fetch origin main 2>/dev/null && git rev-list HEAD..origin/main --count
```
- If `0` — skip silently.
- If **1 or more** — ask if they want to pull first.

---

## Step 1 — Run validation

Execute the validator:

```bash
cd "/Users/mtorpey/Desktop/AI Stuff/AIO Analytics Builder" && python3 pulse_validator.py
```

This will:
1. Sign in to the canary site
2. Ensure a test datasource ("Pulse Validator") exists — creates one if not
3. Test all 6 payload variations (AVERAGE/SUM × NUMBER/CURRENCY/COUNT)
4. Test PATCH `use_dynamic_offset`
5. Test subscription `batchCreate` (flat format)
6. Clean up all test definitions and groups
7. Save results to `.pulse_validation_state.json`

---

## Step 2 — Report results

If all tests pass:
```
✓ All Pulse API payload formats validated
  Site: {server_url} — Build {version} ({build})
  Tests: {passed} passed, 0 failed
  Last run: {timestamp}
```

If any tests fail:
```
⚠ PULSE API BREAKING CHANGES DETECTED
  Site: {server_url} — Build {version} ({build})
  Tests: {passed} passed, {failed} FAILED

  Failures:
    ✗ {test_name}: HTTP {code} | {error_snippet}
    ...

  Action needed: investigate the failures above. The payloads that failed
  will also fail in /build-demo. Check if Tableau Cloud changed the API
  contract and update CLAUDE.md + pulse_validator.py accordingly.
```

---

## Step 3 — Check last validation (optional shortcut)

If the user runs `/validate-pulse --status` or asks "when was the last validation?", read `.pulse_validation_state.json` and report:

```python
import json, os
state_path = os.path.join("/Users/mtorpey/Desktop/AI Stuff/AIO Analytics Builder", ".pulse_validation_state.json")
if os.path.exists(state_path):
    with open(state_path) as f:
        state = json.load(f)
    print(f"Last run: {state['last_run']}")
    print(f"Build: {state['version']} ({state['build']})")
    print(f"Results: {state['passed']} passed, {state['failed']} failed")
else:
    print("No validation has been run yet.")
```

---

## Notes

- **Canary pod**: 10ax receives Tableau Cloud releases ~1 week before production pods. Running validation there gives early warning.
- **Frequency**: Runs automatically once per week during `/build-demo` (or if the server build version changed). Use this command to run it on demand.
- **Cleanup**: All test definitions, groups, and subscriptions are deleted immediately after testing. Nothing persists on the validation site.
- **Release schedule**: See the [Tableau Cloud pod deployment schedule](https://salesforce.enterprise.slack.com/docs/T7KUQ9FLZ/F094XCHG0Q2) for rollout timing.
