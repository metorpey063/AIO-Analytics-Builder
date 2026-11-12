# AIO Analytics Builder — Roadmap

Planned enhancements, fixes, and integration work. Updated as items are completed or re-prioritized.

## Top Priorities

The Web UI home page shows this list (title, status, summary) with live vote counts. Keep it to 5 items, one line each, in the form `1. **Title** | Status | Summary`. After editing, run `python3 roadmap_votes.py sync` to push it to the roadmap org (items that drop off keep their votes).

1. **Sales Insights customizations** | Next | Tailor the deployed Sales Insights data and dashboards to a customer through a config file
2. **Service Insights deployment** | Planned | Deploy the Service Insights dashboard package to any org with Data Cloud, like Sales Insights
3. **Data Apps for Tableau Next** | Planned | Build data apps on top of AIO's Tableau Next demos
4. **Data Apps for Tableau Cloud** | Planned | Build data apps on top of AIO's Tableau Cloud and Pulse demos
5. **Tableau Studio skills in the Web UI** | Planned | Generate and install a demo's Studio skills from the Web UI and at the end of a build

## Planned

### Sales Insights customizations
- `/deploy-sales-insights` deploys 6 dashboards with fixed, generic, seeded data (`salesinsights/DESIGN.md`). Next: a customer config (company, products, regions, team, story) that drives the generated data and dashboard labels

### Service Insights deployment
- The Service Insights counterpart of `/deploy-sales-insights`: capture the package from the source org, generate synthetic service data, deploy to any org with Data Cloud. Reuse `salesinsights/` (capture → generate → deploy)

### Data Apps for Tableau Next
- Data apps built on AIO's Tableau Next demos (SDM, metrics, Concierge). Scope to be defined

### Data Apps for Tableau Cloud
- Data apps built on AIO's Tableau Cloud demos (published datasources, Pulse metrics). Scope to be defined

### Tableau Studio skills (/studio) — Web UI and build flow
- Currently CLI only (`/studio {slug}`); the Web UI build already saves the story to the checkpoint
- Add a Studio step after Close the Loop in the Web UI build, and a page to run it on any demo in My Demos
- Offer it as an optional add-on at the end of `/build-demo`

### Agentforce action trigger for close-loop
- P2: "create follow-ups for the at-risk accounts" as an Agentforce action
- Default trigger for Tableau Next builds once available
- Replaces the Slack button trigger for Next demos

### Terminal setup (`setup.py`) — untested automatic path (low priority)
- The automatic Salesforce setup was tested end to end in the Web UI on a fresh org (2026-11-06). The terminal wizard (`python3 setup.py`, also used by `/setup`'s fallback) calls the same `org_bootstrap.py` steps, but its prompts haven't been run against a real org.
- Low priority: the Web UI is the main way SEs set up AIO now. Run it once against a fresh org if terminal setup issues are reported.

### Polished CRMA mode
- Today's CRMA output is one dataset + one dark-theme dashboard from `crma_golden_template.json`. `CRMA_BUILD_PLAYBOOK.md` (SE-contributed, ATI Restoration build) documents the shapes for a much more polished build
- Candidates, roughly in value order: light branded cards (white, rounded, brand tints); KPI tiles with %Δ arrow + "vs prior 30 days" + sparkline; worst-first table with colored status dots and severity rank; `pie` + `inner` donuts with center counts; `pillbox` filters past 2
- Later: multi-dashboard nav (needs update-in-place PATCH, done), record links in a new tab via an `analytics__Dashboard` LWC, segmented filter LWC with live counts
- Needs render checks in the browser each round — a successful POST doesn't mean it renders (playbook §0 rule 5)

### CRM Analytics answers in the AIO assistant (crma-beta MCP)
- The CRM Analytics MCP server (`crma-beta`) is activated by setup and works with AIO's MCP login (tested 2026-11-11). Next: let the Web UI's Ask Claude assistant answer analytics questions from a demo org's CRMA data ("what's our win rate by region in Revenue Insights?") by calling `list_datasets` → `get_dataset` → `get_xmd` → `execute_query`
- Design decisions first: the assistant is read-only and can't call an org today (by design). This would be its first org access, so pick which connection it uses, show the SAQL it ran, and cap calls per question (each one costs Flex Credits)
- Keep `get_dashboard` out of the assistant (hundreds of KB per dashboard); summarize from `list_dashboards` + the datasets instead
- Reuse `web-ui/mcp_client.py` (make the endpoint a parameter, use `org_bootstrap.crma_mcp_url()`)

### Existing Next SDM loader for close-loop
- P3: load an existing Tableau Next SDM (not built by AIO) so close-loop can analyze its data
- Enables close-loop on demos the SE already has without rebuilding

## Completed

### Roadmap voting in the Web UI (2026-11-12)
- Home page panel: each SE ranks a top 3 (3 / 2 / 1 points) across Top Priorities and Ideas from SEs (live immediately); Suggest an idea. Anonymous, capped per install per day
- Stored in the Tableau Next & Slack org behind the public AIO Roadmap Site; synced to Data Cloud and shown in the AIO Roadmap Votes Tableau Next dashboard

### CRM Actionability + Close the Loop in the Web UI
- The Tableau Next build's actionability option creates the CRM records, then a Close the Loop step (`/close-loop/<slug>`) picks Slack or Chatter and deploys the Flows
- Standalone `/close-loop` remains for Pulse/CSV demos and post-build use

### Zero-click Salesforce org setup (2026-11-04 → 2026-11-06)
- `org_bootstrap.py`: AIO deploys its own External Client Apps, activates the Tableau Next MCP servers, and finds or creates the Ingest connector. Users only log in through the browser.
- Web UI automatic setup with a progress bar; Claude credentials read from Claude Code's settings (`claude_credentials.py`)
- Verified end to end on a fresh org. Manual: Data Cloud provisioning and the `TableauPilotMCPServerEnabled` permission

### close-loop and studio integration (2026-10-19)
- Applied jzitko's two patches (close-loop + studio)
- Decisions: FLS grant non-fatal, Section 3 untouched, studio standalone only, cp["story"] on every build
- Both features available as standalone commands
