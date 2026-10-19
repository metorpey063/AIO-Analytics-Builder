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

### Existing Next SDM loader for close-loop
- P3: load an existing Tableau Next SDM (not built by AIO) so close-loop can analyze its data
- Enables close-loop on demos the SE already has without rebuilding

## Completed

### close-loop and studio integration (2026-10-19)
- Applied jzitko's two patches (close-loop + studio)
- Decisions: FLS grant non-fatal, Section 3 untouched, studio standalone only, cp["story"] on every build
- Both features available as standalone commands
