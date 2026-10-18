# Close-loop sidekick

Builds the demo's "what do we do now?" step **into the Salesforce org**. The Q4 at-risk finding becomes real records (Tasks per at-risk entity, an escalation Case, or a recovery Campaign) created by a Flow. The audience triggers that Flow during the meeting, either from a Slack **Create follow-ups** link or with a record-triggered breach signal. A Notify Flow then tells the team in Slack, or in Chatter if Slack isn't connected. Claude Code isn't involved at demo time.

## Files

| File | Purpose |
|---|---|
| `close_loop.py` | Story analysis → plan → Flow generation → Metadata API deploy → activate → walkthrough Section 7. CLI below. |
| `close_loop_flows.py` | Flow metadata XML generators (follow-up, notify, alert, screen, signal) + `package.xml` |
| `setup_slack.py` | Saves Slack IDs to the `/setup` profile (flags or prompts) and runs the read-only check. `/close-loop` calls it in Step 2b, the Slack-or-Chatter choice, only when the user picks Slack. |
| `COMMAND.md` | The `/close-loop` instructions and close-loop Known Pitfalls |
| `INTEGRATION.md`, `close-loop.patch` | How to merge this into core later |

The repo-root `close_loop.py` is a small forwarding shim so older root-level scripts (`lessen_pulse_build.py`) can still `from close_loop import preflight`.

## Run

From the repo root, with the project's Python (`.venv/bin/python`):

```bash
python sidekicks/close-loop/close_loop.py preflight --slug {slug} [--profile K]   # read-only org check
python sidekicks/close-loop/close_loop.py plan      --slug {slug}                 # no org changes
python sidekicks/close-loop/close_loop.py build     --slug {slug} --notify slack|chatter [--action task|case|campaign] [--trigger slack_button|record_triggered] [--check-only]
python sidekicks/close-loop/close_loop.py test      --slug {slug} [--step trigger|followup]
python sidekicks/close-loop/close_loop.py reset     --slug {slug} [--yes]
python sidekicks/close-loop/close_loop.py remove    --slug {slug}
python sidekicks/close-loop/close_loop.py slack-check --slug {slug}               # read-only Slack check + fixes
python sidekicks/close-loop/setup_slack.py --channel-id C… --workspace-id T…     # save Slack IDs (or no flags = prompts)
```

Or in Claude Code: `/close-loop {slug}` (also `--test`, `--reset`, `--remove`, `--preflight`).

## Inputs

`demos/{slug}/` containing a CSV and `{slug}_checkpoint.json`, as written by `/build-demo`. Optionally a `{slug}_demo.py` with `METRIC_CONFIG`. For demos made outside AiO, see COMMAND.md Step 1.

## Dependencies

- Python: `pandas`, `requests`, `python-docx`. These are already core requirements; nothing new is needed.
- Core: `connections.py` (`load_config`, `get_sf_token`, `sf_headers`). Uses the existing Salesforce `api` scope, so no new OAuth scopes or Connected App changes.
- Org: Flows deployable via the Metadata API. Slack is optional: the org must be connected in Setup → Slack and the user's Slack account linked. Without it, posts go to Chatter.
- Config: optional `profiles.{key}.slack` = `{workspace_id (T…), channel_id (C…), channel_name, app_id (A…)}`. These are IDs only, with no secrets.
