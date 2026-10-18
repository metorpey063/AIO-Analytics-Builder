# Sidekicks

Optional add-ons for the AIO Analytics Builder. Each one runs on its own against any `demos/{slug}/` folder, and `/build-demo` offers it in its **Optional add-ons** step. Core files never import or depend on a sidekick, so deleting a sidekick folder leaves the core tool unchanged.

| Sidekick | Command | What it adds | Needs |
|---|---|---|---|
| [close-loop/](close-loop/README.md) | `/close-loop {slug}` | ONE follow-up action built into the Salesforce org (Flows), fired by the audience; Slack or Chatter notify; walkthrough Section 7 | Salesforce org (from `/setup`); Slack optional |
| [studio/](studio/README.md) | `/studio {slug}` | Three Tableau Studio Agent skills pre-loaded with the demo's story | Tableau Studio (only to install/use) |

**Order when used together:** close-loop first, then studio. That way the Studio skills' `demo-story.md` includes the Close the Loop step.

**Shared contract** (`demos/{slug}/`):
- `{slug}_checkpoint.json`. Studio reads and writes `story`, `studio_skills_generated`, `studio_skills_installed`. Close-loop writes `close_loop` (incl. `deployed` Flow names for safe removal). Each merges its keys and never overwrites the others.
- `{slug}_close_loop_payload.json`. Close-loop writes it; studio reads it if present.
- The demo CSV and `{slug}_demo.py` (`METRIC_CONFIG`). Close-loop reads them.

Each folder has:
- `README.md`: what it is, how to run it
- `COMMAND.md`: the full slash-command instructions (`.claude/commands/{name}.md` is a small launcher that points here)
- `INTEGRATION.md` + `{name}.patch`: how to fold it into core later
