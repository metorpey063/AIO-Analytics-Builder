# AIO Analytics Builder — Roadmap

Planned enhancements, fixes, and integration work. Updated as items are completed or re-prioritized.

## In Progress

### CRM Actionability + Close the Loop (Tableau Next)
- Integrate `/close-loop` Flow deployment into the Tableau Next CRM Actionability build path
- Single question during Next builds: "Make this demo CRM-actionable?" gates both record creation and Flow deployment
- Slack-or-Chatter choice happens during the CRM Actionability flow, not in `/setup`
- Standalone `/close-loop` command remains available for Pulse/CSV demos or post-build use

## Planned

### Web UI integration for close-loop and studio
- Wire `/close-loop` and `/studio` into the browser-based Web UI
- Both commands currently work from CLI on Web UI demo folders
- Web UI build pipeline should save `story_config` to checkpoint so story analysis works without `METRIC_CONFIG`
- Natural hook: before the final `progress(q, "done", ...)` in `run_build`

### Tableau Studio skills (/studio) — build flow integration
- Currently standalone only (`/studio {slug}`)
- Future: offer as optional add-on in `/build-demo` after testing is complete
- Could appear as a skill on the AIO UI home page

### Agentforce action trigger for close-loop
- P2: "create follow-ups for the at-risk accounts" as an Agentforce action
- Default trigger for Tableau Next builds once available
- Replaces the Slack button trigger for Next demos

### Terminal setup (`setup.py`) — untested automatic path (low priority)
- The automatic Salesforce setup was tested end to end in the Web UI on a fresh org (2026-11-06). The terminal wizard (`python3 setup.py`, also used by `/setup`'s fallback) calls the same `org_bootstrap.py` steps, but its prompts haven't been run against a real org.
- Low priority: the Web UI is the main way SEs set up AIO now. Run it once against a fresh org if terminal setup issues are reported.

### Existing Next SDM loader for close-loop
- P3: load an existing Tableau Next SDM (not built by AIO) so close-loop can analyze its data
- Enables close-loop on demos the SE already has without rebuilding

## Completed

### Zero-click Salesforce org setup (2026-11-04 → 2026-11-06)
- `org_bootstrap.py`: AIO deploys its own External Client Apps, activates the Tableau Next MCP servers, and finds or creates the Ingest connector. Users only log in through the browser.
- Web UI automatic setup with a progress bar; Claude credentials read from Claude Code's settings (`claude_credentials.py`)
- Verified end to end on a fresh org. Manual: Data Cloud provisioning and the `TableauPilotMCPServerEnabled` permission

### close-loop and studio integration (2026-10-19)
- Applied jzitko's two patches (close-loop + studio)
- Decisions: FLS grant non-fatal, Section 3 untouched, studio standalone only, cp["story"] on every build
- Both features available as standalone commands
