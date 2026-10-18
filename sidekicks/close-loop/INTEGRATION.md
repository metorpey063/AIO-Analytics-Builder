# Integrating close-loop into core

## What it does, and why it belongs in core

Close-loop answers the fifth demo question, **"What do we do now?"**. It turns the Q4 at-risk finding into real Salesforce records (Tasks / Case / Campaign) through Flows that the audience fires during the meeting, with a Slack or Chatter notification. Every AiO demo already ends on "who is most at risk?", so this closes that story with a live action instead of a slide. It complements upstream's **5c CRM actionability**, which makes insights *point at* real CRM records; close-loop *acts* on them.

## Today (as a sidekick): no core file depends on it

| Piece | Where it lives now |
|---|---|
| Logic | `sidekicks/close-loop/close_loop.py`, `close_loop_flows.py` |
| Slack profile setup | `sidekicks/close-loop/setup_slack.py` (was in core `setup.py`) |
| Command | `sidekicks/close-loop/COMMAND.md` ← launcher `.claude/commands/close-loop.md` |
| Close-loop Known Pitfalls | `COMMAND.md` § Known Pitfalls (were in core `CLAUDE.md`) |
| Root shim | `close_loop.py` (repo root), for `lessen_pulse_build.py` only |
| `/build-demo` hook | "Optional add-ons" step (intake ~line 421, run ~line 1478, summary ~line 1535) |

## Core files that would change on a full merge

Line numbers refer to `refactor/sidekicks` (upstream `e7288c1` + kept fixes).

| File | Hook point | Change |
|---|---|---|
| `close_loop.py`, `close_loop_flows.py` | repo root | Move from `sidekicks/close-loop/` (replacing the shim). Delete the `ROOT`/`HERE` `sys.path` lines, set `demo_dir()` back to `os.path.join("demos", slug)`, and change CLI strings to `python close_loop.py`. |
| `setup.py` | `setup_section()` ~line 32 (`if section == ...` chain) | add `if section == "slack": return setup_slack(profile)` |
| `setup.py` | new functions after `setup_salesforce()` ~line 219 | `setup_slack()` + `test_slack()`. Copy from `setup_slack.py` (`run` → `setup_slack(profile)` returning the profile; `check` → `test_slack(profile)`). |
| `setup.py` | `select_mode()` ~line 459 | optional prompt "Also configure Slack alerts for /close-loop? [y/N]" → append `"slack"` to steps. **Only if you accept an extra question for everyone with Salesforce** (see "what broke" #6). |
| `setup.py` | `validate_profile()` ~line 492, `run_setup()` ~line 539 | run `test_slack` / `setup_slack` when `"slack" in steps` |
| `connections.py` | `_EMPTY_PROFILE` ~line 15 | add `"slack": {"workspace_id": "", "channel_id": "", "channel_name": "", "app_id": ""}` (optional; every read already uses `.get("slack")`) |
| `config.json.template` | top-level profile | same `slack` block with an `_instructions` note |
| `.claude/commands/setup.md` | new optional step after Salesforce | Slack step. Use `python close_loop.py preflight --slug X` for the check (not inline Python), and the **T… team ID** wording. |
| `.claude/commands/build-demo.md` | "Optional add-ons" | Keep as is; just repoint `sidekicks/close-loop/COMMAND.md` → `.claude/commands/close-loop.md`. Do **not** reintroduce a separate 5c intake. |
| `CLAUDE.md` | design principles (~line 29, after #4) | Principle #5, worded as *optional* ("When the demo includes close-the-loop…") |
| `CLAUDE.md` | walkthrough format: after Section 6 (~line 207), the table (~line 219), label rules (~line 230) | Section 7 "Close the Loop", a table row "(if built)", and the `Trigger:` / `Result:` label rule |
| `CLAUDE.md` | Known Pitfalls (end) | the three "Close the loop:" pitfalls from `COMMAND.md` |
| `CLAUDE.md` | Project structure / What this does | `close_loop.py`, `close_loop_flows.py`, `/close-loop` lines |

## Patches

- `close-loop.patch`: the feature exactly as it was integrated on `backup/integrated-features` (diff `2b0b380..backup/integrated-features`: `close_loop.py`, `close_loop_flows.py`, `close-loop.md`, `setup.md`, `config.json.template`, and only the Slack/close-loop hunks of `setup.py` and `connections.py`). It applies cleanly to `2b0b380`. On current upstream, use it as a **reference**, not a blind `git apply` (setup.py and the command paths have moved).
- `../shared-docs.patch`: the original `build-demo.md` + `CLAUDE.md` edits for **both** features (they were interleaved). It conflicts with upstream's 5c/CRM sections; mine it for wording only.

## New dependencies, config, env vars

- **Python packages:** none new (`pandas`, `requests`, `python-docx` are already core).
- **OAuth scopes / Connected App:** none new. Deploys use the existing `api` scope via the Metadata API.
- **Config:** optional `profiles.{key}.slack` (IDs only, no secrets).
- **Env vars:** none.
- **Org:** Flows deployable. Production orgs need "Deploy processes and flows as active" or the build's activate step. Slack is optional (Setup → Slack + linked user); otherwise Chatter is used.

## What broke last time (see `docs/sidekick-refactor/01-breakage-audit.md`) and how to avoid it

1. **Broken preflight snippets in `build-demo.md` 5c.2/5c.3** (#2). They tuple-unpacked a dict, were missing `import json`, used a literal `PROFILE_KEY_HERE`, and had no `slack_cfg`. → Only ever call the CLI: `python close_loop.py preflight --slug {slug} [--profile K]`.
2. **Wrong Workspace ID instructions** (#3): they said the subdomain. → It's the `T…` team ID. Keep one wording, copied from `setup_slack.py`.
3. **Every build asked 2–6 new questions; dashboard/brand steps renumbered; `all` removed** (#4). → Keep the single "Optional add-ons" question at the end of intake, shown only when the feature exists. Don't renumber 5a/5b/5c.
4. **`CLAUDE.md` made close-loop part of every demo** (#5). → Word principle #5 and Section 7 as conditional.
5. **`/setup` asked about Slack for everyone** (#6). → Keep Slack out of `select_mode()` unless the coworker agrees; `setup_slack.py` works as-is.
6. **Core imported the feature** (`setup.test_slack` → `from close_loop import preflight`) (#7). → If merged, `close_loop.py` is core anyway. If it stays a sidekick, keep the import inside `setup_slack.py`.
7. **Label collisions** with upstream's 5c and Phase 4a/4b/4c (#13). → Use the name "Optional add-ons", never a letter.
8. **Tracked demo files deleted** (#14). → Before merging, run `git diff --stat upstream/main...HEAD -- demos/` and confirm no deletions.

## Integration checklist

1. [ ] Branch from current `upstream/main`.
2. [ ] Decide with the coworker: (a) does `/setup` ask about Slack? (b) does close-loop stay a sidekick or move to root?
3. [ ] If moving to root: `git mv sidekicks/close-loop/close_loop*.py .`, remove the shim, revert the `ROOT`/`HERE` path lines, and update CLI strings (`rg -n "sidekicks/close-loop" -g '!sidekicks/'`).
4. [ ] Add the `setup.py` / `connections.py` / `config.json.template` hooks from the table (only those agreed in step 2).
5. [ ] Move `COMMAND.md` → `.claude/commands/close-loop.md` and its Known Pitfalls → `CLAUDE.md`.
6. [ ] Update `build-demo.md` "Optional add-ons" paths. Leave its wording conditional.
7. [ ] Add the `CLAUDE.md` principle #5, Section 7, and label rule, all conditional.
8. [ ] `git diff --stat upstream/main -- demos/` shows no deletions.
9. [ ] Run the tests below.

## Tests

**Core still works (run these first; they must match upstream):**
1. `.venv/bin/python -c "import connections, setup, oauth_flow"` prints no errors.
2. `.venv/bin/python connections.py` prints the validation table and exits 0/1 with no traceback.
3. `/setup` on an existing profile reaches "ALL SYSTEMS GO". Slack is asked only if step 2(a) said yes.
4. `/build-demo` for a fictitious company, CSV only, choosing no add-ons: the questions are Step 5 → 5a → 5b → 5c as upstream; the build and walkthrough are unchanged.
5. Web UI: `python web-ui/app.py` → Connections → Test responds.

**Close-loop works:**
1. Offline: `python close_loop.py plan --slug waste_connections_route_ops` prints the headline, drill path, action, trigger, and Flow names, with no org calls.
2. Org: `preflight --slug X` returns JSON, `slack_ready` reflects config.
3. `build --slug X --check-only` passes the deploy validation; then `build` deploys, and walkthrough Section 7 appears.
4. `test` creates the records/alert; `reset` removes them; `remove` undeploys only the names in `cp.close_loop.deployed`.
5. `/build-demo` choosing the Close-the-loop add-on runs it after the core build, and the summary shows the add-on row.
