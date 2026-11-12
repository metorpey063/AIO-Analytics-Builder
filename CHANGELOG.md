# Changelog

All notable changes to AIO Analytics Builder are documented here.

---

## 2026-11-12 — Signal verifier: check that the data tells the story (v2.15.0)

### Added
- **`signal_verifier.py`:** reads the generated DataFrame back and checks the story landed — the named culprit is the worst segment, at least 3% worse and well above the noise (z >= 2.5), the other segments move less, the drill-down cell is at least 1.15x the rest of the culprit, the counter-trend metric improves. Warns (never fails) when no segment is flat, the runner-up is within 85% of the culprit, supporting metrics don't follow, the decline is implausibly deep, or the settings design a story inside the noise. Idea adapted from the SE Data App Kit's `verify.py`.
- **Noise is measured from the data:** the same recent-vs-baseline change is taken at every earlier point before the onset and pooled over segments, so drift, AR(1) persistence and seasonality count as noise. One cutoff then holds for any background: a 5% story passes at `variability` 0 and fails at 1.5. Month-to-month differences (the first version) understated the noise about 3x; with cutoffs scaled down for gentle settings, 4 of 20 stories with no signal at all passed. Now 0 of 20 (1 of 20 at magnitude 0.02, was 15). With too little history before the onset to measure noise (under ~18 months for a 3-month onset), the strength cutoff rises to 10% and a warning says so.
- **Mean per row for every metric:** a Sum metric at daily or weekly grain was read as a monthly sum, so the partial current month and 4- vs 5-week months looked like a crash (up_is_good failed every build, up_is_bad read as improving). All 20 now pass.
- **Plans the data can't meet aren't redrawn:** a culprit or drill-down value that isn't in the data, a culprit off the dimension the generator signals on, a drill-down on the culprit's own dimension, or a counter-trend metric that is missing or is the primary. The report's `fixable_by_redraw` is False and the message names the problem (it used to burn 4 draws, then name some other segment).
- `tests/test_signal_verifier.py`: 25 tests (good story passes; wrong segment, weak signal, uniform decline, flat drill-down, missing counter-trend each fail; no signal never passes; noise follows the background; Sum with a partial month; short history; plan problems; RNG state; weekly/daily dates).

### Changed
- **Web UI `generate_data` redraws a missed draw** (up to 4, best kept) against the story's `signal_plan`. About 1 in 8 draws used to leave a neighbouring segment looking worse than the named culprit, so the walkthrough named the wrong segment; 1 of 60 miss now (Meridian sweep, magnitude 0.4, variability 0, 1.0 and 1.5). The report is saved as `story_config["signal_check"]`.
- **`data_generator.generate_demo_data` verifies and redraws too** (up to 3 seeds). The culprit comes from a new `signal_plan=` argument, else from the multipliers: the compound table's dimension, or the largest multiplier anywhere (it used to be the first dimension listed). **A config whose seed-42 draw misses now returns seed 43 or 44 data** (`df.attrs["signal_seed"]`); the global `random` / `np.random` state is left as the returned draw left it. It warns instead of raising and keeps the report on `df.attrs["signal_report"]`. Pass `verify=False` to skip. The original body is now `_generate_once`.
- **`generate_demo_data` daily and weekly data run through today.** Weekly used a fixed 4 weeks per month and ended two months early; daily ended at the start of the current month.

---

## 2026-11-12 — Transfer Assets: dashboard health badges, readable service errors (v2.14.5)

### Added
- **Dashboard list health badges:** after the list loads, each dashboard gets ✓ healthy, ⚠ N of M widgets erroring (they already error in the source and transfer the same way), or ✕ semantic model deleted (can't be packaged, so its checkbox is disabled). One dashboard GET each, 8 in parallel: 45 dashboards in ~13s. `transfer_assets.dashboard_health()`, `POST /api/transfer/health`.

### Fixed
- A failed package or deploy printed the Package & Deploy service's whole server traceback. The engine now prints one `ERROR` line with the service's own message, and the page shows it in red under the button. `SDM_NOT_FOUND` explains itself: the dashboard's semantic model was deleted in the source org (the dashboard is broken there too), so pick another dashboard.

---

## 2026-11-11 — Installer works on Intel Macs and fresh Macs (v2.14.4)

### Fixed
- **Intel Macs:** the AIO Builder launcher ran Python through `arch -arm64`, which fails on Intel ("Bad CPU type"), so it rebuilt the venv on every launch and the server never started. It now uses `arch -arm64` only on Apple Silicon (`hw.optional.arm64`).
- **Python on fresh Macs:** macOS ships Python 3.9, and `AIO Installer.app` (launched from Finder with a minimal PATH) found only that one even when a newer Python was installed. Both installers now add `/opt/homebrew/bin` and `/usr/local/bin` to PATH, use the newest `python3.13`…`python3.10` they find, and link straight to the python.org macOS installer when there's none. The launcher's venv rebuild uses the same lookup.
- **git:** both installers check for Apple's Command Line Tools before cloning and open Apple's installer if they're missing, instead of failing partway.
- `.mcp.json` (personal MCP config that can hold tokens) is now gitignored.

### Docs
- README Prerequisites and QUICK_START list a Mac (Apple Silicon or Intel), Python 3.10+ (macOS has 3.9), git / Command Line Tools, and Claude Code or saved Claude credentials.

---

## 2026-11-11 — Salesforce CLI installs without Homebrew (v2.14.3)

### Fixed
- With no Homebrew, `install_sf_cli.sh` only printed instructions, and the suggested Homebrew command breaks when shared through Slack (it turns the quotes curly). It now downloads the official Salesforce CLI installer (`sf-arm64.pkg` / `sf-x64.pkg`, signed and notarized) and opens it in the macOS Installer, which asks for the Mac password itself. It opens once (`.sf_pkg_offered`); later launches print the link.
- The setup error and Setup page hint point to that installer when Homebrew is missing, and the error no longer says "use manual setup below" twice.

### Docs
- README / QUICK_START: Homebrew is optional; the Salesforce CLI installer is listed for Macs without it.

---

## 2026-11-11 — Installer adds the Salesforce CLI; Homebrew in the prerequisites (v2.14.2)

### Fixed
- New SEs without the Salesforce CLI hit "Salesforce CLI not found" on Salesforce Automatic Setup, because no installer set it up. New **`install_sf_cli.sh`** installs `sf` with Homebrew (or npm) when it's missing and otherwise prints how to install it, including the Homebrew command when Homebrew is missing too. It always exits 0, so an install or launch never stops on it. It runs from `install_remote.sh`, `AIO Installer.app`, `install.py`, and the **AIO Builder launcher**, so existing installs pick it up on their next launch.
- The setup error (`org_bootstrap.preflight`) and the Setup page hint now say to install Homebrew first when it's missing, and to relaunch AIO Builder after installing the CLI.

### Docs
- README **Prerequisites** and QUICK_START gain a "Before you start" checklist: Python 3.10+, Homebrew, Salesforce CLI.

---

## 2026-11-11 — Transfer Assets: login check, Reconnect, step badges (v2.14.1)

### Fixed
- A transfer from the Web UI crashed when an org's Salesforce login had expired: the background job tried to open a browser login and failed with `Address already in use` on the OAuth callback port. Background jobs now set `AIO_NO_BROWSER_REAUTH`, so `connections.get_sf_token` raises `ReauthRequired` instead (`allow_browser=False` does the same in-process). The transfer prints one `AUTH_ERROR` line and the page offers Reconnect.

### Added
- **Transfer Assets page:** picking an org checks its login right away (✓ Signed in, or ⚠ expired with a **Reconnect** button that runs the same OAuth login as Connections). Check transfer and Transfer show step badges (Package → Source data → Target data; Package → Data → Deploy n/N → Verify) with the current step's detail, so the 30-second stream listings and the row copy don't look hung.

---

## 2026-11-10 — Transfer Assets: tested engine + Web UI page (v2.14.0)

> Tested end to end on 2026-11-10: AIO Test Org → AIO Dev, 5 dashboards (Z, F, dynamic composed, Exec Summary, Trend & Breakdown) into one workspace and one SDM, 18,000 rows copied, every widget `Ok`, all 6 metrics returning the source's values, layouts identical to the source.

### Added
- **`transfer_assets.py`**, the engine behind `/transfer-assets`: `list`, `plan` (read-only), `run`, `verify` and `remove`. `run` packages the dashboards, creates the target's data stream and copies the rows when it's missing, deploys the first dashboard with a new workspace + SDM and the rest into it, then checks every metric against the source. Checkpointed and resumable; `remove` deletes only what the transfer created.
- **Web UI → Skills → Transfer Assets:** pick source and target orgs and the dashboards, Check transfer (read-only), Transfer, Remove.

### Fixed (the skill's inline code)
- Target data was matched by DLO prefix, which embeds the connector name, so it never matched across orgs with different connectors. Now matched by schema name.
- The schema fields were read from a stream GET key that doesn't exist (`dataLakeFieldInputRepresentations`), and the Query API columns from `metadata.columns` (the metadata is a dict keyed by column). Both came back empty.
- Multi-dashboard transfers created a workspace + SDM per dashboard, because the deploy status doesn't name the SDM.
- `/ssot/data-streams?limit=500` returns 400. It now pages at 200.

---

## 2026-11-10 — Trend & Breakdown: no empty band above the last chart (v2.13.1)

### Fixed
- Trend & Breakdown had a 15-row empty band before its full-width breakdown (the captured layout's hole where the source had a widget). Role-based templates now close any vertical gap larger than 2 rows.

---

## 2026-11-10 — Revenue Intelligence demos keep moving: `roll` and `add` (v2.13.0)

> Previews for Nov 10, 17 and 30 and Feb 20 behave as designed. Applied live on the Tab Next & Slack org on 2026-11-10: `roll` updated 23 opportunities and 12 line items and logged 65 activities; `add` created 8 deals with line items; the org then showed 51 new OpportunityHistory rows. Backups are in the demo's `out/`.

### Added
- **`python3 -m revintel demos/{slug} roll [--apply] [--refresh]`** — a built Revenue Intelligence demo otherwise stands still: nothing closes after the load date, and Revenue Insights' "last 7 days" tiles, Closed Won line and Changes tabs go flat (a fresh load shows one huge jump, then nothing). Only *edits* create the OpportunityHistory those read, and a reset + reload can't back-date, so `roll` plays the days since the last roll through the open deals:
  - deals reach their close date and close (won / lost) or slip; a slipped commit drops back to best case
  - stages advance as close nears; healthy renewals turn At Risk and counter-trend ones recover
  - amounts (via the line items) and close dates drift
  - culprit segments slip, lose the churn product (with loss reasons) and drift down more; counter-trend segments less
  - activity is logged against the opportunities, leaving at-risk and quiet culprit deals bare, so RI's "No Activity" list shows the deals worth coaching on
- Dry run by default: prints counts, per-segment results and the effect on this month's Closed Won and Commit, and writes `out/roll_plan.json`. `--apply` backs up the before-values first and refuses future dates; a second run on the same day needs `--force`. Only touches opportunities with the demo's external-ID prefix.
- **`python3 -m revintel demos/{slug} add [--apply] [--count N]`** — `roll` moves the deals that exist; `add` creates new ones, so the New tab and pipeline coverage change week to week. Each new deal is an expansion on a pool account for a product it doesn't own (the whitespace EAM shows), stage mix 65% Targeting / 25% Needs Analysis / 10% Proposal, sized from the account's headcount like the original load, with a first logged activity on about half. Counter-trend segments generate more than culprit ones; a segment's `boost` weights its favourite products. About 8 a week by default (`ADD = {...}` tunes it). Same safety as `roll`: dry run by default, once a day unless `--force`, no future dates, created IDs saved to `out/add_<date>.json`.
- **Update Rev Intel page:** "Keep the data moving" — Preview roll / Roll forward, Preview add / Add deals, and one button that rolls, adds and refreshes CRM Analytics. Writing needs a confirm click.
- `ROLL = {...}` in the config tunes the rates (see `roll.DEFAULTS`).
- **`roll --close today=3,2026-11-04=1`** closes deals on chosen dates (back-dating works) so a flat month gets a Closed Won staircase on demand. Picks Commit / Best Case deals weighted by Commit, Einstein score, segment health and smaller size; `--keep "name,name"` freezes story deals, `--max-deal` sets the size cap, `--close-only` skips the day simulation. Deals with a higher Einstein score are also less likely to slip in the normal roll.

### Docs
- `/update-rev-intel` pre-approves `roll`, `add` and `refresh` (any demo folder) in its `allowed-tools` header, so SEs aren't blocked by auto mode's write check on a shared org and need no settings of their own. `reset`, `apply` and `team` are not pre-approved.
- `/update-rev-intel`: `roll` and `add` are the default way to keep dates fresh; `--dates` (reset + re-anchor) is for re-dating the story itself.
- CLAUDE.md: `roll.py` in the project structure; new Revenue Intelligence pitfall (no week-over-week movement after a load; Amount is read-only with products; RI "No Activity" reads opportunity activity).

---

## 2026-11-10 — Every dashboard template works on any demo (v2.12.0)

> Tested on a 6-metric, 4-dimension Tableau Next demo in a fresh test org: each template built through the Web UI's own `run_build`, then every dashboard read back (all widgets `Ok`), every viz queried for data, and the stored assets scanned for leftover customer text. Z Layout's payloads are byte-identical to before.

### Fixed
- **Executive Summary and Pharma Analytics never deployed.** They were captured from customer demos, so their vizzes pointed at fields no other demo has; the build silently fell back to a generic dashboard and reported success. They're now remapped by role: dates, measures and dimensions map to the demo's own; static KPI numbers become real metric tiles; titles come from the demo's metrics ("Net Revenue Retention by Month, Year over Year"). Both open with a large, left-aligned dashboard title where the customer's logo was.
- **Pharma Analytics is now Trend & Breakdown** (4 KPIs, year-over-year trend, three breakdowns). The template packages and picker previews no longer contain the source customers' names, data, logos or semantic model.
- **F Layout skipped its story styling:** its vizzes are named `Donut_Chart1`, `Details_Table1`…, so the rules that add metric columns to the details table and turn a donut on an average metric into a bar didn't apply. They now match by role.
- **A template that fails says so.** The build warns in the log and the final message, and the walkthrough opens with a note naming the template and the reason. The fallback dashboard is still built so the demo isn't empty.

### Removed
- **Multi-Page KPI template** (captured from one customer's demo; too large for a demo build).

---

## 2026-11-10 — README: correct Web UI port

### Fixed
- The README and the installer's header comment said the Web UI opens at `localhost:5050`; it's `localhost:5100` (what the installer and launcher actually use).

---

## 2026-11-10 — No false "update available" for unpushed work (v2.11.1)

### Fixed
- The Web UI offered an "update" whenever the local `VERSION` differed from GitHub's, so a copy with unpushed commits was told to update to GitHub's *older* version (e.g. "you have 2.11, update available: 2.10"). It now offers an update only when GitHub has commits this copy doesn't. Tested ahead / behind / same against a stand-in GitHub. (Clicking Update in that state was already harmless: the updater skips copies that are only ahead.)

---

## 2026-11-10 — The Web UI assistant can read AIO's docs and your demo logs (v2.11.0)

> Tested end to end through `/api/chat` with real Claude calls on the Salesforce gateway: a "Cyclic relationship detected" question was answered from CLAUDE.md Known Pitfalls and the deploy log, with file:line citations, in about 9 seconds; a deploy-status question was answered from the checkpoint and logs. Path escapes, `config.json` and credential files are refused; secret-looking JSON values are redacted.

### Changed
- **"Ask Claude" troubleshoots instead of guessing.** It now runs on Claude Sonnet 5.5 (was Haiku 4.5, 1,024-token answers) with read-only tools: search and read AIO's docs (CLAUDE.md Known Pitfalls, guides, every skill's instructions), list demos and read their checkpoints and logs, see recent Build Demo / Update Rev Intel / Deploy Sales Insights job logs from the server, and list connections. It shows what it's doing ("Searching the docs for…", "Reading demos/…") and cites file:line. It can't change anything: it tells you what to click or which command to run.
- Its skills list and page hints are current: all ten skills are read from `.claude/commands/`, and Update Rev Intel and Deploy Sales Insights pages have hints.
- `web-ui/assistant.py` holds the tools and the tool loop. The Build Demo story generator and the credentials Test button keep their model.

### Fixed
- Sales Insights verify printed the last year's metric value (next year, usually 0). It now prints this year's.

---

## 2026-11-10 — v2.10.0

Release marker for everything since v2.9.0 (entries below, back to 2026-10-30). Highlights:
- **New skills:** `/update-rev-intel` (tailor a demo org's Revenue Intelligence data, with Research customer and Upload documents in the Web UI) and `/deploy-sales-insights` (standalone Sales Insights on any Data Cloud org, now with its own Web UI page)
- **Setup:** zero-click Salesforce org setup that also activates the Tableau Next MCP servers; Claude credentials detected from Claude Code automatically
- **Tableau Next builds:** dashboards and data follow the story out of the box (story-driven composer, realistic segment differences and seasonality), Dynamic Dashboard template, Concierge retry
- **CRM Analytics:** rebuilds update dashboards in place; SE playbook captured
- **Updates:** install new dependencies, restart the server, and never delete unpushed commits

---

## 2026-11-10 — Updates never delete unpushed commits

> Tested in throwaway clones (ahead / behind / diverged from a stand-in GitHub) for both the launcher and the Web UI Update button.

### Fixed
- **Auto-update deleted local commits.** The AIO Builder launcher and the Web UI Update button ran `git reset --hard origin/main` whenever local `HEAD` differed from GitHub, including when the local copy was only *ahead*. On launch that wiped two committed-but-unpushed commits (recovered from the reflog). Now:
  - **only ahead** (nothing new upstream): no reset; "Already up to date. This copy also has commits that aren't on GitHub yet."
  - **diverged**: the local commits are saved to a `backup/pre-update-<timestamp>` branch first, then the reset runs as before
  - **behind** (the normal case): unchanged
  
  `/update` follows the same rule.
- **The sidebar restart button didn't restart anything.** `/api/restart` touched a file to trigger Flask's auto-reloader, but the server runs with the reloader off. It now re-executes the server in place, the same way the Update button does (shared `_schedule_restart()`), so code changes on disk load. Tested on a second instance: same port, back up within seconds.

---

## 2026-11-09 — Deploy Sales Insights in the Web UI

> Tested with the Flask test client and on a second server instance (port 5199): page renders, profiles list with org URLs and deploy state, unconfirmed writes rejected, `check` and a no-op `deploy` on aio-dev run through the job/poll endpoints, deployed state renders (headless Chrome). A full fresh deploy hasn't been run from the page yet.

### Added
- **Deploy Sales Insights page** (replaces the info-only placeholder): pick a Salesforce connection (listed with its org URL and whether Sales Insights is deployed there), **Check org**, **Deploy** with a 7-phase tracker and live log, the finish-in-Tableau-Next items (share the workspace; business preferences fallback) and the demo story, and **Remove** (deletes only what the deploy created). `?profile=<key>` preselects a connection.
- `/api/sales-insights/profiles | run | job/<id>`: one job per connection. Writes need confirmation. Progress is polled, so a page reload during a 10–15 minute deploy reconnects to the running job. Logs also go to `demos/sales_insights/{profile}/{action}.log`.
- `python3 -m salesinsights check --profile <key>`: read-only preflight (login, ingest connector, source-org guard, earlier deploy).

---

## 2026-11-09 — Dynamic Dashboard tile; Skills section in the sidebar

> The build path ran on demo_build_test_1 with Z Layout + Dynamic selected: both dashboards were created, 16/16 checks passed, and the org was left with exactly those 2 dashboards and 10 vizzes. All Web UI pages render with the new sidebar (Flask test client).

### Added
- **Dynamic Dashboard tile** in the Tableau Next template picker. It runs the story-driven composer (`compose_dashboard_runner`) inside the build, after a layout template or on its own. The window and direction come from the story. A rebuild replaces only the composed assets it tracked. `compose_dashboard_runner.main()` now takes an argument list for in-process calls.
- **Skills** section in the sidebar with Update Rev Intel (moved from Manage) and Deploy Sales Insights.
- `/deploy-sales-insights` page: what the skill deploys, the demo story, and the commands to run it. **Sales Insights is still CLI-only.** The page explains how to run it from Claude Code or a terminal. The home page card links to it.

### Fixed
- The template picker says "Select one or more", but the build only used the first checked template. It now receives every checked tile (`dashboard_templates`), so Dynamic can be combined with a layout. Picking several layout templates still builds only the first.

---

## 2026-11-09 — Story-driven dashboard composer follows the signal plan

> Ran `compose_dashboard_runner.py` on demo_build_test_1: 5 vizzes plus a dashboard, all 16 widgets `Ok`. Each chart's claim was checked against the data, which found the two title and level problems fixed below. The level fix was checked across 12 generated builds (story's region and segment lowest in 12 of 12). The demo's own data predates it.

### Changed
- **Composer reads `signal_plan`.** The culprit sets the "where" dimension and segment, the drill-down sets the "why" dimension, and the counter-trend metric gets a full-width dual-axis row ("Win Rate fell while In-Person Activities rose"). The runner uses the full saved story and a short dashboard title (it used the whole story paragraph).
- **"Why" breakdown of an average is a heatmap**, not a stacked bar. Stacked win rates add up to nonsense totals (~85%). Sum metrics keep the stacked bar.

### Fixed
- The "where" chart said "{segment} drove last month's decline", but it shows levels (`show_change` was never implemented). That was false whenever another segment fell more that month. It now says "{segment} has the lowest {metric}".
- **The story's segments weren't always the lowest.** Segment-level variety could start the named culprit or drill-down above average, so after the decline another segment was still lower (Mid-Market 15.7% vs the declining Enterprise 17.3%). Those segments now start at the average level (`Realism(neutral=…)`). The drill-down cell is also included in the signal scaling, so the 45% cap no longer flattens it back to the rest of the culprit.

- **Dashboards with the fit-to-width table failed to create** (500 "Can't display visualization because it uses features…"). The builder then fell back to a plain dashboard. A dashboard holding a Table-layout viz is now posted on v67.0 too. The post-build check, which read that table on v66.0 (422), retries on v67.0.

---

## 2026-11-09 — The data follows the story; readable trend axis; metrics in the details table

> Rebuilt demo_build_test_1 on its org through `run_build` (16/16 checks passed). Concierge now walks the story's own path: win rate 30.5% → 26.2% over 6 months → West worst → Enterprise worst within West (31.6% → 26.1%) → West deal size down ~45% → in-person activities up (~4,550 → 5,564 a month). The vizzes read back from the org with the new settings. The dashboard hasn't had a visual check in the browser yet.

### Fixed
- **The walkthrough and the data named different culprits.** The generator picked the culprit segment at random, so a story about "West / Enterprise" built data where Midwest was worst. The story now returns a structured `signal_plan` (culprit, drill-down value, counter-trend metric, onset), and the generator follows it. `apply_signal_plan()` puts the culprit's dimension first and the drill-down dimension second. In 9 of 10 test builds, the story's segment came out worst.
- **The counter-trend metric declined with everything else.** The plan's `counter_trend_metric` now rises (In-Person Activities +36% by the latest month), and the Concierge counter-trend question asks about it.
- **The signal onset ignored the story.** It was always 3 months, even when the story said 6–8. It now comes from `onset_months_ago`, and the comparison window follows it.
- **Trend line x-axis labels were cut off ("12/...").** The date had no grouping, so each day was its own header. It's now month-level (`Mdy`, the function the product's own line charts use).
- **The details table showed dimensions only.** It now has the first three metrics as columns (`table_measures`). It's now fit to width: it's created in the product's Table layout (`_to_table_layout()`, posted on v67.0), because the template's layout can't fit to width.
- The full story is saved to the checkpoint (`story_config`), so rebuilds and Retry Concierge keep the company overview and the signal plan.

---

## 2026-11-09 — Demo data looks real: segment differences, seasonality, movement

> Compared on demo_build_test_1's story across 20 random builds: before the signal, win rate now moves about 1 point a month (was 0.2) and regions differ by 2–5 points (was 0.3). Deal size runs Enterprise ≈ $245K > Mid-Market ≈ $183K > SMB ≈ $120K (was ≈ $185K for all three). 18 of 20 builds have a culprit region at least 1.5 points worse than the next. Not yet built into an org.

### Changed
- **New `data_generator.Realism`**, used by both the Web UI and `/build-demo` generators. It adds segment levels, yearly seasonality, per-segment drift and monthly shocks that survive averaging, and noise relative to the value. All of it is applied before the designed signal, so the story is unchanged. `variability` sets the strength (0 turns it off).
- **Signal scaled, not clipped.** The worst segment now drops at most 45% (`signal_scale()`, was up to 100%: 30% → 10%), and every segment keeps its designed ratio.
- The culprit's drill-down cells are centered on the culprit's own multiplier. An independent 1.2–2.8× draw could leave the culprit level with the moderate segment.

### Fixed
- Noise was a fixed ±0.02, so it was invisible on money metrics ($185K) and cancelled out once averaged. It's now relative to the value.
- Sum metrics were multiplied by 1,000 even with a real `base_range` (In-Person Activities 32–48 became ≈ 40,000). The ×1,000 now applies only to legacy 0–1 ranges.

---

## 2026-11-09 — Retry Concierge for a built demo

> Ran against demo_build_test_1, where Concierge still returns 404: the clear error and the cleaned-up walkthrough section both work. The capture path was checked with a mocked Concierge (6 of 6 answers written into the walkthrough).

### Added
- **Retry Concierge** button on My Demos (Tableau Next demos) and `python3 web-ui/builder.py concierge <slug>`. These ask the story's questions again and replace only the walkthrough's Concierge section. Use it when Concierge wasn't available at build time.

### Fixed
- When Concierge returned an error, every prompt failed with `'list' object has no attribute 'get'`, and the error text went into the walkthrough as the "Expected response". Errors now show Salesforce's own message (e.g. "Concierge isn't available on this org yet (404)"). Capture stops after the first failure, and the walkthrough lists unanswered questions as "not captured".
- A failed capture blocked any retry, because the step only ran when no results were saved. It now re-runs until at least one answer is captured.
- **Concierge reported a 30%→23% win-rate drop as "stable".** The business preferences told it to compare the last 6 months with the prior 6, while the signal starts 3 months back. The window now comes from the signal onset (`trend_window_months()`), and the Concierge questions name it ("over the last 3 months").
- Follow-up questions said "that region", and Concierge asked back which one. They now name the segment the drill-down answer found ("the Midwest region"). The counter-trend question asks which segment is improving, instead of asking whether the lead metric "is also declining".
- Walkthrough answers render `$` and Concierge's markdown (bold, headings, bullets) properly.

---

## 2026-11-06 — CRMA: rebuilds update in place, SE playbook captured

> Checked with mocked API calls (update, deleted-dashboard and first-build paths). Not yet run against a CRMA org.

### Added
- **`CRMA_BUILD_PLAYBOOK.md`**: an SE-contributed playbook from the ATI Restoration build. It covers the crash list, widget cookbook, faceting, lenses, LWCs in dashboards, record actions and branding. Its API rules are summarized in CLAUDE.md Known Pitfalls. A "Polished CRMA mode" item based on it is in ROADMAP.md.
- `crma_dashboard_builder.upsert_dashboard()`: PATCHes the demo's saved dashboard in place (checkpoint `crma_dashboard_id`), or creates one if there's none.

### Fixed
- **CRMA rebuilds no longer pile up copies.** The Web UI POSTed a new dashboard on every run, and each copy got an auto-suffixed developer name. It now updates the saved one in place. `/build-demo`'s Smart Template path reuses the app it made earlier (`existing_app_id`) instead of creating a new app each run.
- `CHART_TYPE_MAP` no longer maps to CRMA chart types that break: `time` (white-screens the dashboard) is now `line`, and `donut` (renders as a bar) is now `pie` + `DONUT_PARAMS`.

---

## 2026-11-06 — Tableau Next dashboards tell the story out of the box

> From field feedback on a Corporate Relations demo (Adam D'Ambrosio). Checked offline against the Z Layout template and with a simulated metrics table. Not yet run against an org.

### Fixed
- **Flat trend lines.** The dashboard template's slots were filled with dimensions in SDM order, so the trend line could be colored by a dimension with no signal (e.g. Academic Program instead of Employer Partner). Slots now follow the story's dimension order, so the culprit dimension colors the trend line. This applies to the template, MCP and legacy REST paths.
- **The Web UI's metrics table was dropping the story's metric details.** Every Web UI build rebuilt the metrics from the table and lost each metric's description, why-it-matters, nouns, `base_range` and primary flag. Metrics with `up_is_bad` sentiment were saved as `up_is_good`. The table now keeps the story's metric and applies only the edits.
- **"3000%".** Any metric with Average aggregation was formatted as a percentage, so an average of Days Until Renewal read 3000%. New `viz_templates.metric_unit()` / `is_percent_metric()` use the metric's `unit` (or the Web UI's Format column) and otherwise infer it from `base_range` and the label. They're used for the SDM calc fields, Pulse workbooks, MCP vizzes and CRMA. The data generator no longer caps non-percent averages at 1.0.
- **Donut of an average.** The donut slot becomes a horizontal bar unless its metric is a Sum.
- **Template styling.** The trend line's Y axis no longer starts at zero. Bars are colored by their dimension. Rate measures show as percentages. Unfilled placeholder text ("Section Subheader") is blanked.
- Captured Concierge answers that contain a percentage over 100% are flagged in the build log and the walkthrough.

### Added
- `template_deployer.remove_widget()`: removes a widget from both the `widgets` dict and the layout positions.
- `python connections.py token [profile]` prints AIO's own Salesforce token (`sf org display` hides the CLI's).
- `unit` field in `METRIC_CONFIG` (`percent` / `days` / `currency` / `number`), included in the story prompt and `/build-demo`.

---

## 2026-11-06 — Automatic setup activates the Tableau Next MCP servers

> Verified on a fresh org where both servers were inactive and had no `McpServerAccess` records yet: AIO created them and the MCP Servers page then showed both Active. On AIO Dev, where they were already active, nothing changed.

### Added
- **MCP server activation** — the automatic Salesforce setup (`/setup`, `setup.py`, Web UI) now activates "Tableau Next Beta" (`tableau-next-pilot`) and "Tableau Next" (`tableau-next`). That's the same as clicking Activate in Setup → Integrations → API Catalog → MCP Servers: it sets `McpServerAccess.Active` through the Tooling API. `python3 org_bootstrap.py mcp` does it on its own.
- If `tableau-next-pilot` can't be activated, setup says the `TableauPilotMCPServerEnabled` org permission is the likely cause and where to request it. That permission is still a manual request.

- **Setup progress bar** — the Web UI's automatic Salesforce setup now shows a progress bar, "Step 4 of 6 — Wait for the apps to go live · 1:12" with a spinner and running timer, a line saying what to do right now (e.g. "A Salesforce tab opened: click Allow"), and every step listed from the start with ✓ / ✗ and details. Checked with screenshots of the running, finished and failed states (fake responses, no org).

### Fixed
- The automatic setup's "waiting for the apps to go live" step could hang forever if the computer slept mid-wait: its checks had no timeout. Each check now gives up after 10 seconds and is retried.

---

## 2026-11-05 — Deploy Sales Insights: standalone deploy to any Data Cloud org

> Deployed end to end to a test org (aio-dev): 15 data streams, 171 semantic objects, 68 vizzes and 6 dashboards; all 471 widgets and 128 dynamic tokens read back `Ok`, and all 7 metrics return data. The dashboards haven't had a visual pass in the browser yet.

### Added
- **`salesinsights/` package** (`python3 -m salesinsights capture | generate | deploy | status | reset`):
  - `capture.py` (maintainer): turns the six Package & Deploy exports into one portable package. It keeps only the part of the SDM the dashboards use (15 tables, 78 fields, 136 calcs, 9 parameters, 7 metrics, 17 joins), adds bridge tables automatically, orders calcs by dependency, and switches data objects from DMOs to placeholder DLOs. Documented calc fixes in `SOURCE_FIXES`: one case-sensitive flag comparison, plus three reversed `DATEDIFF`s that made Average Days to Close and converted-lead Lead Age negative on realistic data.
  - `generate.py`: seeded synthetic data dated relative to today. Deals are simulated stage by stage, so history, weekly trend, pushes, stalls and activity all agree. The baseline story: one team behind, pushes clustered on two reps, a wide lead-conversion spread, and open deals with no activity. It validates the data against the contract before writing.
  - `deploy.py`: a checkpointed deploy that resumes after a failure. It refuses the source org, and `reset` deletes only what the checkpoint lists.
  - `package/`: the committed package (1.4 MB) and data contract, so every SE gets the same deploy.
- **`/deploy-sales-insights` rewritten** as a short wrapper around the CLI (was a 744-line description of a pipeline that never ran).

### Fixed (docs)
- New Known Pitfalls: copying DMO-based data objects onto DLOs (drop `standardDataObjectName`, keep `tableType: "Shared"` or multi-fact joins fail as cyclic), and case-sensitive string comparison in calcs.

---

## 2026-11-05 — Claude credentials detected automatically

> Tested with the Claude Code environment variables removed (as when the Web UI starts from the launcher): credentials found in `~/.claude/settings.json`, gateway test call and a chat message succeed, revintel resolves the same credentials, precedence cases pass, Setup and Connections pages render. Not clicked through in a browser yet.

### Added
- **`claude_credentials.py`** — one place for AIO's Claude credentials, used by the chat, Web UI story generation and Rev Intel drafting. It reads the Salesforce rollout's gateway URL, token and CA bundle from Claude Code's settings, so users no longer copy `echo $ANTHROPIC_AUTH_TOKEN` into the Web UI, and AIO follows the token if the rollout changes it. A key the user saves explicitly still wins; "Use Claude Code credentials instead" switches back.
- **Setup and Connections: Claude status** — "✓ Claude connected — using your Claude Code settings (Salesforce gateway)", a **Test** button (one tiny request), and "Use a different key". The paste form only shows when nothing is found.
- `/api/chat/test`, `/api/chat/use-claude-code`; `/api/chat/status` now says where the credentials come from (no secrets).

### Fixed
- A pasted gateway token now uses Claude Code's corporate CA bundle when it has none of its own.
- Chat's "No API key found" error now points to Setup → AI Configuration.

---

## 2026-11-05 — Deploy Sales Insights: design + verified API findings

### Added
- **`salesinsights/DESIGN.md`**: the design for rebuilding `/deploy-sales-insights`. It deploys the 6 original Sales Insights dashboards from the Tableau Next & Slack org to any org with Data Cloud, on seeded synthetic data. The design covers a capture → portable package step, a data generator and a checkpointed deploy. All 6 design spikes passed on a test org. No deploy code yet.

### Fixed (docs)
- **The relationship pitfall was wrong.** Ingest API DLO relationships don't drop their join criteria. The payload we documented does: top-level `leftFieldApiName`/`rightFieldApiName` are silently ignored (201 with `criteria: []`). Posted as `criteria: [{leftSemanticFieldApiName, rightSemanticFieldApiName, ...}]`, the joins work and query correctly. Corrected in CLAUDE.md, ENGINEERING_GUIDELINES §11, `/build-demo` and MCP_BUILD_GUIDE. `/build-demo` still denormalizes into one fact table by default.
- New verified Known Pitfalls in CLAUDE.md:
  - Custom-SQL logical views need API v66.0; v65.0 silently creates an empty view.
  - Read-only "setterless" keys (e.g. `dataDefinedGoals`) must be omitted from payloads.
  - REST dashboard POST at v67.0 `minorVersion=14` takes every widget type inline, but accepts tiles for metrics that don't exist.
  - Explicit DO and field apiNames are kept on SDM create.
  - Ingest schemas accept `DateTime` and `Boolean`.
  - `POST /services/data/v65.0/semantic-engine/gateway` queries an SDM over REST.

---

## 2026-11-05 — Updates install new dependencies

### Fixed
- **New Python packages now arrive with updates, not only on a fresh install.** Before, only the launcher installed dependencies, and only when `requirements.txt` changed during its own update. Updates made with the web UI's Update button or `/update` never installed anything. For example, `pypdf` was missing from existing installs.
  - New `deps.py` compares `requirements.txt` with what's installed and runs pip only for missing or outdated packages (about 0.1 s when nothing is missing).
  - **Update button:** installs the incoming version's new dependencies *before* switching code. If pip fails, the update isn't applied, so code and packages stay in step.
  - **AIO Builder launcher:** checks dependencies on every start. Only lines after its `git reset` changed, so an older launcher updating itself carries on cleanly.
  - **`/update`:** new step 3b runs `deps.py`.
- **The Update button now actually restarts the server.** The web UI runs without Flask's reloader, so after an update the old code kept running until the next relaunch. The button now re-executes the server once the update is applied, closing inherited sockets so the port is free.
- `pypdf` is in the root `requirements.txt`, the one installs and updates read.

---

## 2026-11-05 — Update Rev Intel: Upload documents

### Added
- **Upload documents** button on the Update Rev Intel page, next to Research customer. It takes the BRD, RFP, deck or discovery notes (PDF, Word, PowerPoint, text, Markdown, CSV) and adds each file's text to Requirements, under a `--- filename ---` header. Research customer and Draft with Claude both read Requirements. Up to 60,000 characters per file; the full KnowBe4 BRD is about 33,000.
- **Shared `/api/build/upload`**, also used by the Build Demo page:
  - reads **PowerPoint (.pptx)** slides, by parsing the slide XML (no new dependency)
  - includes **Word tables**, where BRD requirements usually live
  - accepts an optional `max_chars` (default 15,000, up to 100,000)
  - reads up to 60 PDF pages (was 20)

### Fixed
- PDF text now comes from `pypdf` (added to `web-ui/requirements.txt`), falling back to PyPDF2. PyPDF2 split the KnowBe4 BRD one word per line and broke words ("Short-T erm").
- Research customer now reads up to 60,000 characters of Requirements (was 30,000).

---

## 2026-11-05 — Update Rev Intel: Research customer

### Added
- **Research customer** button at the top of the Update Rev Intel page. From the customer name, plus the use case and requirements if they're entered, it suggests the industry, audience, products and list prices (core / dropped at renewal / new), regions and segments, the story (problems, worst segment, counter-trend, root cause, leading indicator) and team structure notes.
  - Only empty fields are filled. Prefilled fields are highlighted until you edit them.
  - A "Why these answers" panel shows the reasoning, a confidence rating per area (pricing is usually low) and the sources.
  - It takes about a minute and doesn't touch the org. Verified live on Zendesk and KnowBe4.
- **`revintel/research.py`** uses the web UI's DuckDuckGo search, then Claude (`claude-opus-5-5`, medium effort). The story is framed as a demo hypothesis, and the company's employees are never named.
- **`revintel/llm.py`** holds the shared Claude calls and credentials (moved out of `draft.py`, which now uses it).

### Fixed
- `researcher.py`: one search with no results (`ddgs` raises "No results found.") ended all research, including `/build-demo`'s story research. It now falls back to the HTML search.
- Update Rev Intel page: saved regions and segments weren't restored when a demo folder was reopened. Product names are now escaped in the products table.

---

## 2026-11-04 — Zero-click Salesforce org setup

> Tested end to end on the AIO Dev org with throwaway apps (all removed): deploy → wait → AIO login with no secret → Data Cloud exchange, Semantics, Bulk Ingest API → profile save and refresh; MCP app login → MCP `initialize` 200 → refresh with no secret; updating a secret-requiring app keeps its consumer key. Ingest connector creation via the API was tested separately (schema registered). The Web UI button and the `setup.py` prompts have been checked (page renders, JS parses, routes respond) but not clicked through against an org.

### Added
- **`org_bootstrap.py`** — sets up a Salesforce org for AIO with only browser logins: Salesforce CLI login, deploys or reuses the two AIO External Client Apps (REST + MCP), reads their consumer keys, waits until they're live, runs the AIO OAuth login with no secret, finds or creates the Ingest API connector, and saves the profile. Registers `tableau-next-pilot` in Claude Code with the MCP app's key.
- **/setup Step 4-Auto** — the default Salesforce path. The manual ECA steps are kept as a fallback.
- **Web UI setup wizard: "Set Up My Org Automatically"** — the main path on the Salesforce step. It runs the same steps (`/api/setup/auto/login|apps|wait|authorize`), then the MCP login, and offers to update an existing app AIO can't use. Manual setup is collapsed behind "Set up manually instead" (it opens by default for connections that were set up by hand).
- **One-org guidance** — `/setup`, `setup.py` and the Web UI tell the user to sign out of every other Salesforce org and log into only the target org before the browser logins. The automatic setup stops if the AIO login lands in a different org than the CLI login, and a "Cross-org" error now explains the fix.
- **`setup.py`** — offers automatic setup before the manual Connected App prompts.

### Fixed
- `setup.py` created connectors with `connectorType: "INGEST_API"`; the API takes `"IngestApi"`.
- `setup.py` sent an empty `client_secret` on refresh; it's now left out when blank (needed for no-secret apps).
- `oauth_flow` timeout now explains that `invalid_client_id` in the browser means the app is still activating.
- Web UI setup page always opens the wizard. A "Form" choice saved in the browser by an older version left users stuck in the old form view (its toggle is hidden), which has no automatic setup.
- Web UI "Save & Return" and "Test Connection" no longer re-save the manual form over an automatically configured connection. They used to put back the login URL and any stale secret, which would break a no-secret app.

---

## 2026-11-04 — /update-rev-intel skill + revintel engine

> Generalised from the KnowBe4 Revenue Intelligence rebuild. Regression-checked: the KnowBe4 demo regenerated through the new package produces an identical plan (all accounts, opportunities, line items, contacts, activities) and identical quotas (180 rep-months). `inspect` and `refresh --plan` run against the Tab Next & Slack org; `apply` / `team` write paths are the same code that loaded the KnowBe4 data, but haven't been run through the new CLI yet.

### Added
- **`/update-rev-intel`** — tailors a shared demo org's Revenue Intelligence data (Revenue Insights + Einstein Account Management) to a customer and use case: inspect → design the story with the SE → plan → apply → team/quotas → refresh → verify, plus a date refresh.
- **`revintel/` engine** (`python3 -m revintel demos/{slug} <command>`), built for both the skill and the web UI (non-interactive, JSON outputs in `out/`):
  - `inspect` — read-only org survey: Revenue Intelligence apps and duplicates, refresh chain, EAM wizard filters, stages per record type, price books, renewal fields, forecast types, territory models, who shows under the sales leader in Revenue Insights, scheduled Apex, pool size. Warns on the known traps.
  - `plan` — deterministic generator (culprit / moderate / counter-trend segments, accelerating ramps, product churn as a leading indicator, co-terms, forecast-window renewals, gap fillers) with story stats (`--json`) and config validation that names every unfilled setting.
  - `apply` — checkpointed, insert-only sf CLI bulk loads with CSV backups; owner moves; pool record type; territories created parents-first.
  - `team people | reassign | quotas` — fictional personas, lead roles under the sales leader (forecast manager each), other demos' opps moved off the team, monthly quotas for role and territory forecast types (ATR due + run rate, floor, story stretch).
  - `refresh` / `reset` — `crma_refresh.py` chain; reset + `apply --today` re-anchors dates.
- **`revintel/config_template.py`** — the per-customer config (Python or `config.json`).

- **Web UI: Update Rev Intel Data** — a home-page card ("Tools & Skills") and a sidebar link open a Q&A page that captures the skill's design answers (customer, use case, requirements, org, products, story, team, forecast window) into `demos/{slug}/rev_intel_request.json`. It runs the engine with live output: Inspect (read-only, with warnings), Plan, then users and lead roles, data load, other demos' deals, quotas, and refresh. Every org write needs a confirm click, and the server refuses unconfirmed writes. The whole flow runs in the UI:
  - **Draft with Claude** writes the customer config and pool from the answers plus the org facts, and validates it by running `plan` (one automatic repair if it fails).
  - **Review** shows the segments and their story roles, who appears under the leader, products (core, dropped, new, created by the build), Claude's assumptions and questions, and story stats.
  - **Revise draft** takes the SE's requested changes.
  - **Build everything** runs users and lead roles → data → other demos' deals → quotas → refresh, stopping at the first failure.
  - **EAM Reconfigure answers** are shown when the filters need changing.
- **`revintel draft`** — Claude (`claude-opus-5-5`, adaptive thinking) drafts the config. It uses the UI's credentials: the Bedrock gateway via its `/invoke` format, else the Anthropic SDK with server-side refusal fallback. It repairs invalid JSON once and records assumptions and questions in `out/draft_notes.json`. Verified locally on a Zendesk test (≈4 min, valid on the first pass; revision run separately).
- **`revintel inspect` org facts** — users, record types, standard price book products, territories, the loss-reason dependent picklist, and candidate pool accounts (unused: no opportunities, contacts or cases).
- **`revintel apply` products step** — finds or creates Product2 and its standard price book entry for products without one.

### Docs
- CLAUDE.md: `/update-rev-intel` in "What this does"; `revintel/` in project structure.

### Not yet verified
- **Build everything** from the web UI hasn't been run against an org yet. Test it on a scratch org first, not a shared demo org.
- The Update Rev Intel page was tested through Flask's test client, not yet in a browser.

---

## 2026-11-04 — CRM Analytics refresh automation + Revenue Intelligence pitfalls

> Built during the KnowBe4 Revenue Intelligence demo rebuild on the Tab Next & Slack org (EAM + Revenue Insights). Groundwork for the upcoming `/update-rev-intel` skill.

### Added
- **`crma_refresh.py`** — refreshes CRM Analytics apps after CRM data changes. Discovers the recipe chain from the datasets the apps' dashboards use (walking back through the recipes that save them), then runs Data Sync and the recipes in dependency waves, stopping on the first failure. `--plan` previews the chain; `--skip-sync` runs recipes only. Tolerates transient network errors while polling.

### Docs
- **Known Pitfalls** — CSV uploads over CRMA datasets break them; EAM record-type filters live in the install wizard (fix with Reconfigure); Revenue Insights is role-based only; territory forecast-manager ordering; Opportunity business-process deploy; scheduled demo-refresh Apex; sf CLI body-less POST and bulk result shapes.
- **Project structure** — `crma_refresh.py` listed.

---

## 2026-10-30 — Sentiment fixes + viz pane fix (lessons from Tableau vibe-coding starter kit)

> Sentiment verified on Brad's org (Meridian story: 4 up-is-bad + 2 up-is-good metrics all correct). The `viz_builder.py` change is compile-checked only — template builds don't exercise it.

### Fixed
- **Tableau Next metric sentiment** — the REST metric POST never set `insightsSettings.sentiment`, so every metric defaulted to "up is good" (e.g. readmission rate rising was treated as positive by insights). Now mapped from `METRIC_CONFIG.sentiment`.
- **Pulse metric sentiment** — `up_is_bad` metrics fell through to `SENTIMENT_TYPE_UP_IS_GOOD` because only the legacy `down_is_good` value was checked. Now maps to `SENTIMENT_TYPE_DOWN_IS_GOOD`.
- **Viz `marks.panes.isAutomatic`** — `viz_builder.py` set it to `True` for charts without encodings (e.g. trend lines), which can render a default bar instead of the requested mark type. Now always `False`.
- **False "SDM query returned 0 rows" validation failure** — the post-build row count parsed queryv2 rows as dicts, but they come back as lists (`[[24000]]`), so every Tableau Next build reported 0 rows and failed one validation check. Now handles both shapes.

### Docs
- **Dashboard filter pitfall rewritten** — filter widgets are not unsupported; they need `source.id`, `receiveFilterSource` subscriptions, and a v67.0 (`minorVersion>=6`) POST to actually filter. Pending org verification.

---

## 2026-10-26 — Setup redesign, close-loop merge, native percentage formatting, MCP token fix (v2.9.0)

### Added
- **Setup hub-and-spoke** — Setup page redesigned from linear wizard to a hub with clickable connection cards. Users pick which connection to configure (Tableau Cloud or Salesforce) and only fill in that one. No more stepping through unrelated forms.
- **Format dropdown (Page 3)** — new "Format" column on the Metrics step with options: Percentage, Number, Currency, Score. Auto-defaults from metric type, user can override. Flows through to data gen and build pipeline.
- **Native percentage formatting** — rate metrics display as percentages natively on Tableau Next (`dataType: "Percentage"` on CLC POST) and CRMA (user XMD API `customFormat: "0.0%"`). No ×100 hack needed. Pulse remains UI-only (platform limitation).
- **Microphone dictation** — mic button on all free-text inputs (company, use case, audience, context, story summary) using Web Speech API. Toggle on/off, appends to existing text.
- **Post-build dimension validation** — checks the CSV for generic dimension values (e.g. "College 1", "Region 3") and flags them in the build log with sample values.
- **Checkpoint invalidation** — detects when the connection profile or build outputs change and auto-resets the checkpoint instead of silently skipping phases.
- **Close-loop Phase 6** — merged `feature/close-loop-phase6`: golden record targeting, record-level action triggers, close-loop UI page, `data_generator.py` reusable module, `ENGINEERING_GUIDELINES.md`.
- **CRMA `set_percentage_fields()`** — new function in `crma_uploader.py` that applies percentage formatting via the Wave user XMD API after dataset upload.

### Fixed
- **MCP token rotation** — `mcp_client.py` used `active_profile` (doesn't exist) instead of `active_salesforce` to save rotated refresh tokens. Tokens were silently lost after each use, requiring re-auth every time.
- **Token cache not cleared on re-auth** — OAuth endpoints now clear `_token_cache` when a new token is obtained, preventing stale cached tokens from being returned for 2 hours.
- **Profile creation on fresh Setup visits** — the Setup route auto-loaded the active profile and set `profileCreated=true`, silently skipping profile creation for new connections.
- **CRMA field name triple underscores** — fields like "Pell & First-Gen Status" produced `pell___first_gen_status` (rejected by CRM Analytics). Now collapses consecutive underscores.
- **Field name truncation** — long field names (40+ chars) now truncate at the last underscore boundary instead of mid-word.
- **Metric-to-measurement matching** — new 8-strategy cascade handles hyphens vs underscores, partial matches, suffix stripping, and fuzzy word overlap. Fixes 5/6 metrics failing on mismatched names.
- **Pulse Discover retries** — retries each metric with up to 3 rephrased question variants. Filters out "I don't have enough data" responses instead of including them in the walkthrough.
- **Concierge walkthrough honesty** — when MCP is unavailable, shows "not captured — run live in Concierge" instead of fabricated expected responses.
- **Generic dimension fallbacks** — smarter defaults by dimension type (College → real college names, Class → "Fall 2022/2023/2024") instead of "Dim 1, Dim 2".
- **`_log()` undefined** — replaced with `progress()` in checkpoint invalidation code.
- **`field_key` undefined** — stale variable reference in metric creation phase after matching refactor.
- **Setup dark mode text** — warning boxes now use amber text colors readable in dark theme.
- **Setup Pulse reference** — removed "Enable Tableau Pulse AI" from Salesforce spoke (it's a Tableau Cloud feature).

### Changed
- **Story prompt** — dimension values are now mandatory ("NEVER use numbered placeholders"). Quick research depth no longer says "use generic".
- **Launcher hardened** — pip install errors visible (not swallowed by `2>/dev/null`), venv health check tests all critical packages (flask, anthropic, pandas, requests, PyPDF2, docx).
- **PyPDF2 + python-docx** added to both root and web-ui `requirements.txt` for PDF/DOCX upload support.

---

## 2026-10-22 — Auto-deploy SDM business preferences, field descriptions, and sentiment via MCP (v2.8.0)

### Added
- **Phase 5b: SDM Enhancement** — new build phase after metrics creation. Uses MCP to automatically set measurement descriptions, labels, aggregation types, and sentiment; dimension labels and descriptions with actual dimension values; calculated measurement and metric descriptions; and business preferences. All deployed directly to the SDM — no manual steps required.
- **Phase 7b: Live Concierge testing** — new post-build phase that runs each walkthrough prompt against the live SDM via MCP `analyze_data` and captures real AI-generated responses. The walkthrough HTML now shows actual Concierge answers (with real numbers and segment names) instead of static template text. Falls back to static prompts when MCP is unavailable.
- **`generate_business_preferences()`** — new function in `builder.py` that produces intent-driven business preference lines matching Tableau's `# ` format. Generates jargon resolution, default query behaviors, metric relationships, sorting defaults, counter-trend guidance, and answer style rules.
- **7 new MCP client methods** — `update_business_preferences()`, `update_measure()`, `update_dimension()`, `update_calculated_measure()`, `update_calculated_dimension()`, `update_metric()`, `list_semantic_models()` in `mcp_client.py`.
- **Per-metric `base_range`** — story prompt now requires `[min, max]` decimal range per metric (e.g. `[0.10, 0.16]` for readmission rates). Eliminates the hardcoded `0.55-0.85` range that produced unrealistic values.
- **System field hiding** — Phase 5b automatically hides `cdp_sys_SourceVersion`, `DataSource`, `DataSourceObject`, `KQ_record_id`, `record_id`, `entity_id`, and `day_offset` so Concierge and the UI only show user-facing fields.

### Fixed
- **Generic dimension values ("Service Line 1")** — dimension values lookup is now case-insensitive and whitespace-normalized. Warns when falling back to generic placeholders.
- **Weak signal on "up_is_bad" metrics** — removed 0.3x dampener that made primary signal nearly invisible for metrics like readmission rates.
- **Column name mismatch causing NULL ingest** — consolidated schema registration and CSV ingest rename into single `clean_field_name()` function, preventing drift between the two algorithms.
- **Legacy sentiment normalization** — `"down_is_good"` auto-converts to `"up_is_bad"` at data gen time.

### Changed
- **Business preferences format** — switched from paragraph-style sections (`# COMPANY CONTEXT\n...`) to atomic one-instruction-per-line format matching Tableau's UI examples. Each line is an intent-driven instruction (jargon resolution, default behaviors, metric relationships) rather than a data dictionary restatement.
- **Walkthrough HTML** — Concierge section now shows live AI responses when captured; business preferences section shows "automatically deployed" when MCP was used. Both fall back gracefully when MCP is unavailable.

---

## 2026-10-21 — Z Layout template fixes, X-prefix ingest bug, dimension values (v2.7.2)

### Fixed
- **Trend line empty** — `Display_Date` SDM calc dim wasn't mapped in the template deployer's `field_map`, so the Trend_Line viz couldn't find its date field. Now mapped from `cp["display_date_api"]`.
- **Empty 3rd chart slot** — Z Layout template had 5 viz widget slots but only 4 viz definitions. `visualization_4` rendered as "Add Visualization". Template deployer now auto-generates `Detail_Bar_2` by cloning `Horizontal_Bar` with the first user dimension.
- **"Section Subheader" raw text** — Dashboard text widgets (`text_1` through `text_8`) weren't reached by `label_map` substitution. Added `label_map` and `detail_headers` params to `prepare_dashboard_payload()` — text now shows company name and metric-by-dimension headers.
- **Generic viz titles** — Viz labels were template defaults ("Trend Line", "Donut Chart"). Now set via `label_map` to meaningful titles like "30-Day Readmission Rate Over Time".
- **X-prefix bulk ingest bug** — Data Cloud auto-prepends `X` to schema fields starting with a digit (e.g. `30day_readmission_rate` → `X30day_readmission_rate`), but CSV upload headers weren't X-prefixed. Data for those columns silently ingested as NULL. Fixed in both `_clean_field_name()` and CSV column rename.
- **Generic dimension values in data** — `generate_data()` ignored `dimension_values` from the story config and fell back to hardcoded patterns, producing "Service Line 1, 2, 3, 4" instead of realistic values. Now reads story-generated values first.

### Changed
- **AIO Builder.app launcher** — no longer hardcodes `~/AIO-Analytics-Builder`. Auto-detects install directory from the `.app` bundle location, so it works from any folder.

---

## 2026-10-20 — CRMA golden template: complete field substitution (v2.7.1)

### Fixed
- **CRMA golden template** — all 5 golden metrics + 3 dimensions now map to the demo's actual fields, not just the first 2. Recursive `_sub_field_values` replaces field names in SAQL queries, lens source arrays, step `visualizationParameters` (plots, columnMap, dimensionAxis), and widget parameters — while preserving dict keys (widget/step names) to prevent duplicate widget errors.

---

## 2026-10-20 — Dark theme, design refresh, UX improvements (v2.7.0)

### Added
- **Dark/Light theme toggle** — sun/moon button in upper right of home page, persists via localStorage. Dark is default.
- **Dark theme for ALL pages** — Setup, Build, Demos, Connections all styled with dark glass cards, dark inputs, dark badges. Same layout, only colors change.
- **Premium animations** — staggered card entrance, 3D perspective tilt on hover, rotating gradient border on Build card, icon glow pulse, hero text fade-in, right panel slide-in.
- **Stats strip** — live stats under hero: Version, Demos Built, Metrics Created, Visualizations, Dashboards, Data Rows (from `/api/stats` endpoint).
- **High-res background** — dark blue silk wave image (Unsplash, Pawel Czerwinski) replaces pixelated stock chart. Layered with gradient orbs and ambient glow animation.
- **Gradient hero title** — "AIO Analytics Builder" cycles through blue → teal → purple over 6 seconds.
- **Colored card accent bars** — thin gradient line at top of each card (blue/teal/purple).
- **Claude AI section on Connections page** — manage API key in one place, auto-hides from Setup if already configured.
- **Copy buttons** (⧉) on setup guide for app names, callback URLs, connector names.
- **Guide expand/collapse** — click step titles to collapse/expand guide content.
- **Save & Finish Later** — on OAuth step, with amber callout about ECA activation delay.
- **Save at every step** — Tableau PAT and SF creds saved when clicking Next, not just on final save.
- **Org provisioning cards** — "Request Salesforce Org" and "Tableau Cloud Site" mini-cards with hover lift.

### Fixed
- **OAuth validation** — validates client_id and login_url before starting flow, clearer error messages.
- **Setup guide** — Click Create moved to step 6, step 10 MCP scopes on separate lines with complete instructions.
- **Update/Restart icons** — differentiated: download arrow for update, cycle arrows for restart.
- **Setup card** — always shows number 1 (not checkmark).

---

## 2026-10-20 — Viz/dashboard builder enhancements from Sales Insights patterns

### Added
- **Dual-axis template** (`viz_templates.py`, `viz_builder.py`, `style_defaults.py`): new `dual_axis` chart type — bar (primary) + line (secondary) over time with independent Y-axes, per-field mark types in `marks.fields`, per-field colors in `style.marks.fields`. Auto-recommended when `secondary_field` is present in metric config
- **Reference lines** (`viz_builder.py`, `style_defaults.py`): new `ref_lines` parameter on `build_viz_payload()` — pass `{field, function, color, dash_style}` dicts to add Avg/Median/Min/Max reference lines to any chart
- **Dynamic token text widgets** (`dashboard_builder.py`): new `build_dynamic_token_text_widget()` — creates text widgets with live BAN values from SDM calc fields that update with dashboard filters
- **`componentVisibility` wired into all metric widgets** (`dashboard_builder.py`): REST `build_dashboard_payload()` now accepts `sdm_id` + `component_visibility`; MCP templates (`build_z_layout_ops`, `build_perf_overview_ops`) now pass their defined visibility configs through to widget parameters
- **`DEFAULT_COMPONENT_VISIBILITY` / `DEFAULT_COMPONENT_VISIBILITY_WITH_CHART`** constants in `dashboard_builder.py`
- **`axis_field_entry()` enhancements** (`style_defaults.py`): new `is_visible` and `title_text` keyword args for hidden axes and custom axis labels (backward-compatible)
- **Dual-axis `marks.fields` validation** (`viz_validator.py`): validates per-field type and stack config

### Patterns reference
- Analyzed `Sales_Insights_Standalone_package.json` (80+ vizzes, 12 dashboards, 11 DOs, ~300 calc fields)
- Extracted reusable patterns into `demos/sales_insights_packages/PACKAGE_PATTERNS.md`

---

## 2026-10-19 — /close-loop + /studio integration, measurement PUT fix

### Added
- **`/close-loop` command**: deploys Salesforce Flows that create follow-up records (Tasks/Case/Campaign) from a demo's at-risk finding, with Slack or Chatter notifications. The audience fires it during the demo — Claude Code isn't involved at demo time. Lifecycle: preflight → plan → build → test → reset → remove
- **`/studio` command**: generates Tableau Studio Agent skills (aio-story, aio-autobuilder, aio-audience) pre-loaded with a demo's story. Works on any AIO demo, outside CSV, .hyper/.tdsx, or published datasource. Standalone — no org needed
- **`studio_skills.py`**: engine for /studio — story derivation (reuses close_loop.analyze_story), demo-story.md rendering, skill folders + install.sh, walkthrough Section 8, custom-skill validation
- **`close_loop.py` + `close_loop_flows.py`**: engine for /close-loop — story analysis, Flow XML generation, Metadata API deploy, walkthrough Section 7
- **`setup_slack.py`**: Slack ID configuration for /close-loop (per-profile, IDs only, no secrets)
- **`ROADMAP.md`**: tracks planned work (Web UI wiring, CRM Actionability integration, Agentforce trigger, studio build-flow integration)
- **`cp["story"]` saved on every build**: all output modes now save story metadata to the checkpoint so /close-loop and /studio work later without re-asking
- **`sidekicks/studio/skills/`**: three Tableau Studio Agent skill templates with reference docs

### Fixed
- **Measurement/dimension PUT 400**: was using `apiName + "__c"` as `dataObjectFieldName` but the apiName has a numeric suffix that doesn't match the DLO field. Now stores the real `dataObjectFieldName` from the DO GET response in `measurement_dof_map` / `dim_dof_map` and uses those in PUT payloads. Fixed in both demo scripts and `build-demo.md`
- **CRM upserter FLS**: new External ID fields get no field-level security for the running user. `grant_field_access()` now creates a Permission Set to fix it, but is non-fatal — warns on failure and lets the upsert try anyway

### Integration decisions (from jzitko handoff)
- Close-loop: will integrate into CRM Actionability question for Tableau Next builds (future)
- Studio: standalone command only, not wired into /build-demo flow yet
- Walkthrough Sections 1-6 untouched (no hand-off line in Section 3)
- Slack config stored per-profile (same as Tableau/Salesforce credentials)

---

## 2026-10-19 — MCP dashboard builder, installer UX, build pipeline fixes (v2.6.0)

### Added
- **Full MCP dashboard builder**: vizzes created via MCP slim spec (line, bar, multi-line with proper field bindings), dashboard assembled with upsert + place_widget_on_page pattern (metrics, filters, vizzes in Z layout)
- **Dashboard filters**: 3 auto-selected dimension filters with labels, placed via MCP
- **Post-build validation**: 7 checks verify SDM data, metrics, Display Date, vizzes, dashboard, data object after every Tableau Next build
- **Build log persistence**: every build writes a `_build.log` file; "Log" button on My Demos opens it
- **Delete with remote cleanup**: checkbox to delete Tableau Cloud/Next assets alongside local folder
- **Restart button**: in-app server restart next to update button — no Terminal needed
- **Flask auto-reloader**: server auto-restarts on code changes after git pull
- **One-line installer**: `curl | bash` with Desktop shortcut and Gatekeeper bypass
- **Getting Started guide**: collapsible panel on home page with 3-step walkthrough
- **AI Configuration in Setup**: required field with `claude setup-token` instructions, OAuth token (Bearer) support
- **File upload**: PDFs, DOCX, TXT, CSV, screenshots extracted and fed to AI story generation
- **Input limits**: demo name 40 chars, field names 40 chars (Data Cloud limit)
- **Retry + Back buttons**: on build progress step for error recovery

### Fixed
- **MCP viz UNKNOWN_EXCEPTION**: was using wrong param names (`semanticModelIdOrName` → `semanticModelName` + `semanticModelLabel`), calc dim `Display_Date` as DO field (needs raw date), and `legends` in spec (server auto-handles)
- **MCP response parsing**: double-nested JSON (`defaultExc` containing JSON string) now correctly unwrapped
- **MCP dashboard widgets**: `upsert_*_widget` only creates definition — must follow with `place_widget_on_page` to position on canvas
- **MCP auth refresh**: removed `code_verifier` from refresh token grants (was causing "unexpected code verifier" 400)
- **OAuth token support**: `sk-ant-oat01-*` tokens route to `Authorization: Bearer` header, not `x-api-key`
- **Schema field names**: truncated to 40 chars, reserved prefixes stripped (`salesforce_`, `tableau_`, etc.), special characters removed
- **Schema PUT**: skip existing schemas entirely (reserved field double-bind), always submit new schema only
- **Duplicate profiles**: fixed apostrophe slug difference creating two profiles with same label
- **Setup wizard**: form mode hidden, edit loads correct profile, MCP auth in Step 3, smart verify hides irrelevant tests
- **Connection checks**: red/green/gray states with MCP error tooltips

---

## 2026-10-19 — Feature parity: Advanced Mode, Research Depth, full output options (v2.5.0)

### Added
- **Advanced Mode** in Build wizard: collapsible section with Data History (6/12/24/36 months), Time Grain (daily/weekly/monthly), Signal Severity, Signal Onset, Signal Shape (accelerating/ramp/step), and Supporting Metric Strength — all wired through to data generation.
- **Research Depth** toggle: Quick (fast defaults) vs. Detailed (deeper company research, 5 metrics, real dimension values). Passed to both story generation and build start.
- **Brand Colors**: primary and secondary hex color pickers with live preview, applied to viz style overrides and dashboard background tints (auto-blended 90% toward white).
- **CRM Actionability**: checkbox creates real Salesforce Account records linked to analytics fact data via `crm_upserter.py` (External ID field, batch upsert).
- **Pulse Dashboard**: checkbox publishes a `.twb` workbook with embedded Pulse metric tiles via `twb_builder.py`.
- **Dashboard Template** selector: Z Layout (MCP), Performance Overview, or Standard (REST fallback).
- **CRMA output**: checkbox uploads dataset to CRM Analytics via `crma_uploader.py`.
- **Build summary panel**: green success panel on completion with checklist of all outputs created.
- **Enriched walkthrough .docx**: full CLAUDE.md format — Demo Scenario (About + Audience & Story), Metrics Reference (What it measures + Why it matters), Click Path or Concierge Prompts with drill-down steps, Goal Lines (Pulse), Business Preferences (Next).
- **File upload**: upload call transcripts, meeting notes, screenshots, PDFs, or any supporting documents. Extracted text is passed to AI story generation for context-aware demo design. Supports PDF, DOCX, TXT, CSV, and image files.

### Fixed
- Signal ramp now supports all three shapes: `accelerating` (quadratic), `ramp` (linear), and `step` (threshold at 30%).
- Data generation uses configurable onset/duration instead of hardcoded `-3`/`3`.
- **macOS Gatekeeper**: one-line remote installer (`curl | bash`) bypasses Gatekeeper entirely. `QUICK_START.txt` always opens (no quarantine on `.txt`). `Install AIO.command` auto-strips quarantine from all files on first run. Three install paths documented: one-liner, zip + Terminal, VS Code CLI.
- **Remote installer creates launcher**: `install_remote.sh` now creates `AIO Builder.command` in the install directory AND a Desktop shortcut so users can relaunch with a double-click.
- **Chat API key save without profile**: the Anthropic API key (for the Ask Claude chat) can now be saved even before creating any connection profiles — new users no longer get "No active profile found" when entering their API key.
- **Auto-restart on update**: clicking the update button now automatically restarts the server after pulling new code. The UI shows "Restarting..." and auto-reloads when the server is back — no manual Ctrl+C needed.
- **Chat widget auto-hides**: the Ask Claude button is hidden until an API key is configured. No more broken chat state for new users.
- **AI Assistant API key in Setup**: Anthropic API key field added to the Setup page under an "AI Assistant" section with save + status badge.
- **Getting Started guide**: new collapsible panel on the home page walking users through the 3 steps (Setup → Build → Present).
- **Collapsible "What's New"**: the changelog panel is now collapsible to save space on the home page.
- **Post-build validation** (Phase 8): after Tableau Next builds, automatically verifies SDM data query (row count), each metric exists, Display Date calc dim is present, each viz has a valid dataSource, dashboard exists, and runs a semantic query to confirm data flows end-to-end. Results logged with ✓/✗ in the build log.
- **Persistent build log**: every build writes a `{slug}_build.log` file. "Log" button on My Demos page opens it in a new tab for debugging.

---

## 2026-10-18 — MCP integration, setup guide improvements, OAuth fixes (v2.4.0)

### Added
- **MCP HTTP client** (`web-ui/mcp_client.py`): direct HTTP connection to the Tableau Next MCP server (140 tools) — no Claude Code CLI needed. Authenticates via MCP ECA OAuth, sends JSON-RPC over Streamable HTTP, handles SSE responses and session management.
- **MCP OAuth flow** (`/api/oauth/mcp`): separate OAuth authorization for the MCP ECA with `mcp_api refresh_token` scopes. "Authorize MCP" button in Setup with prominent blue callout box.
- **MCP in build pipeline**: builder auto-detects MCP availability and uses it for viz/dashboard creation (slim specs, Z layout). Falls back to REST if MCP unavailable.
- **MCP readiness check**: Connections page verifies MCP auth against the live org on Test Connection.
- **Full MCP setup guide**: Setup wizard Step 2 and form mode Step 6 include complete MCP ECA creation instructions — every click, scope, checkbox, and security setting spelled out.
- **Collapsible guide sections**: Steps 1-6 in the form mode guide panel are collapsible with blue/gray expand icons.
- **Copy buttons**: copyable values (app names, callback URL, connector name) have ⧉ buttons that copy to clipboard.
- **MCP Consumer Key + Secret fields**: added to both wizard Step 2 and form mode with tooltips.
- **MCP checklist**: wizard Step 2 has a 3-item MCP checklist (activate server, create ECA, paste key).

### Fixed
- **OAuth scopes per ECA**: `oauth_flow.py` now accepts custom `scopes` parameter. MCP OAuth sends `mcp_api refresh_token` instead of the main ECA's 5 scopes — fixes `OAUTH_APPROVAL_ERROR_GENERIC`.
- **OAuth port reuse**: added `SO_REUSEADDR` to the callback server — fixes `[Errno 48] Address already in use` on retry.
- **MCP refresh token rotation**: client saves rotated tokens on each auth call so they don't expire between uses.
- **Expand/collapse icons scoped**: only top-level step titles show expand/collapse arrows, not nested bold text.
- **Tableau Next Beta references**: updated from `tableau-next-pilot` to `Tableau Next Beta` throughout the UI to match the current Salesforce MCP server name.

---

## 2026-10-18 — Build pipeline fixes, connection management, delete demos (v2.3.0)

### Added
- **Demo Name field** — Build Demo Step 1 now has a "Demo Name" field so builds create unique workspace/SDM/stream names (e.g. "Diversify UI Test" creates `diversify_ui_test` assets)
- **New/Existing Demo toggle** — Step 1 has a toggle to select a previously built demo, auto-populating company name and notes for rebuilds
- **Destination Org picker** — Step 4 shows all connection profiles as radio buttons so users choose which org to build to
- **Delete button on My Demos** — each demo has a red Delete button with confirmation dialog
- **Ingest API connector field** — Setup form mode now has Ingest API Connector Name and Data Cloud Domain fields with tooltip guidance
- **Tableau Next prerequisites** — Step 4 output card lists required org setup (Data Cloud, Tableau Next, AI features, Ingest API connector)
- **Connection name on Setup** — Step 0 asks users to name the connection before configuring it
- **Profile creation API** (`/api/setup/create-profile`) — creates or switches to a named profile
- **Edit button on Connections** — opens Setup with the profile pre-loaded in form mode, showing only relevant sections (hides Tableau Cloud for SF-only profiles)
- **Readiness checklists** — Connections page shows green/gray checkmarks for ECA, OAuth, Ingest API, Data Cloud per profile; Ingest API and Data Cloud verified against live org on Test
- **OAuth propagation note** — Setup Step 3 warns that new ECAs can take up to 10 minutes to become active

### Fixed
- **Config save destroying profiles** — `save_config` was writing flat dict over entire `config.json`, wiping all profiles. Now properly updates only the active profile within the profiles structure.
- **Schema registration** — field names and labels now lowercase with no spaces; `isPrimaryKey` removed from schema fields (only valid in stream fields)
- **Stream creation** — DLO field representations now only include PK field (other fields auto-discovered from schema); 5-second propagation delay after schema PUT
- **Bulk Ingest object name** — was using DLO name, now correctly uses schema name
- **Data Object creation** — added required `label` field
- **Viz field mapping** — field_map now uses base field names (not DO apiNames); system dimensions filtered out; `recommend_dashboard_vizzes` used for template selection
- **Form mode test buttons** — added `Content-Type: application/json` header
- **Connector auto-discovery** — always discovers connector from live org instead of relying on stale config IDs

---

## 2026-10-18 — Full build pipeline wired into Web UI (v2.2.0)

### Added
- **Build orchestrator** (`web-ui/builder.py`): complete build pipeline running in a background thread with SSE progress streaming. Supports all four output modes: CSV, Tableau Pulse, Tableau Next, and CRM Analytics.
- **AI story generation** (`/api/build/generate-story`): Claude API generates story summary, signal design, dimensions, and full `metric_config` from company + industry + use case inputs. User reviews and edits before building.
- **Data generation engine**: creates synthetic data with engineered signals (accelerating ramp), per-segment multipliers, counter-trends, noise scaling, and self-healing `Day_Offset` column. Cross-product of all dimension combinations ensures every filter path has data.
- **Pulse build pipeline**: publish `.hyper` → create metrics with 2026.2 payload format → self-healing `.tdsx` conversion → group creation → subscriptions → walkthrough `.docx`
- **Tableau Next build pipeline**: schema registration → data stream creation → DLO polling → bulk ingest → workspace + SDM + DO creation → measurement updates → Display Date calculated dimension → CLC + metric creation → viz creation (via `viz_builder`) → dashboard assembly → workspace asset linking → walkthrough `.docx`
- **CRMA build pipeline**: dataset upload via `crma_uploader` → walkthrough `.docx`
- **Walkthrough document generation**: creates `.docx` with Demo Scenario, Metrics Reference, and platform-specific sections (Click Path for Pulse, Concierge Prompts for Next)
- **OAuth flow wired to web UI**: "Run OAuth Flow" button in Setup Step 3 now opens the browser, captures the auth code, exchanges tokens, and saves the refresh token — no CLI needed
- **OAuth propagation note**: Step 3 now includes a note that new ECAs can take up to 10 minutes to become active

### Changed
- **Build wizard Steps 2-3**: now call Claude API to generate story + metrics, displayed in editable fields. Metrics table populated from AI output, fully editable before building.
- **Build wizard Step 5**: sends real build config to `/api/build/start`, shows live SSE progress with phase names and percentages
- **Card subtitle text**: dark gray inside glass cards for better readability

---

## 2026-10-17 — Web UI polish: frosted glass, guided setup, version checking, walkthrough links

### Added
- **Frosted glass design** — all cards, accordions, panels use translucent `backdrop-filter: blur` with 16px rounded corners; analytics background image at 50% opacity behind content
- **Platform selection on Setup** — new Step 0 lets users choose which platforms to connect (Tableau Cloud, Tableau Next & Data Cloud, CRM Analytics) before entering credentials; stepper adapts dynamically
- **Side-by-side setup guides** — Steps 1 (Tableau PAT) and 2 (Salesforce ECA) now show the form on the left and a scrollable step-by-step instruction panel on the right with numbered walkthrough
- **Version checking** — `VERSION` file tracks current release; `/api/version` compares local vs `origin/main` on page load; update button turns blue with pulsing glow when outdated; red version text + dismissable banner notification when behind
- **Update button** — refresh icon in sidebar header runs `git pull --ff-only`, prompts to reload
- **"Ask Claude" label** — text label next to the chat bubble so new users know what it does; fades out when chat panel opens
- **Walkthrough doc links** — My Demos page shows clickable links to each demo's `.docx` walkthrough; opens directly in Word/Pages (not browser download)
- **Open Folder** — My Demos "Open Folder" button now actually opens the demo directory in Finder via `/api/demos/{slug}/open`
- **Changelog panel** — home page right sidebar shows the 5 most recent changelog entries with dates and bullet points
- **Contextual guidance** — home page header text adapts based on connection state (nothing connected → both connected) with blue hyperlinks to next action

### Changed
- **Connections page** — reorganized from per-profile accordions to platform-grouped sections (Tableau Cloud / Salesforce & Data 360 / MCP); profiles only appear under platforms they have configured
- **Home page** — two-column layout with numbered workflow tiles (1-Setup → 2-Build → 3-Demos), Tools & Skills section, GitHub link, and expanded description
- **Sidebar nav** — reordered with "Get Started" (1-2-3 step numbers) and "Manage" section labels; increased max content width to 1200px
- **My Demos** — removed Refresh Dates button (self-healing dates handle this)

### Fixed
- Chat bot Bedrock gateway: switched from streaming `invoke-with-response-stream` (binary event format) to non-streaming `/invoke` to fix parsing errors

---

## 2026-10-16 — AIO Web UI (v2.0)

### Added
- **AIO Web UI** (`web-ui/`): a local web server that provides a visual, browser-based experience for AIO Analytics Builder — no VS Code or Claude Code required. Run `python3 web-ui/app.py` or double-click `AIO Builder.command` to launch.
  - **Home page**: action cards for Build Demo, My Demos, Setup, and Connections
  - **Build Demo**: 5-step wizard (Company → Story → Metrics → Output → Build) with a Wizard/Form toggle — wizard walks through one step at a time, form shows everything at once for power users. Fields sync between modes.
  - **Setup**: guided configuration with tooltip help icons on every field explaining exactly where to go and what to click in Tableau Cloud and Salesforce Setup (PAT creation, ECA setup, OAuth scopes, etc.). Includes an ECA checklist with checkable items. Wizard/Form toggle here too.
  - **Connections**: collapsible accordion cards per connection profile (e.g. "Torpey's House of Data", "Tableau Next"). Auto-fetches live data on page load — Pulse API status, datasource/workbook counts, SF username, Data Cloud domain, workspace/SDM counts, ingest connector status. Profile switching built in.
  - **My Demos**: lists all demos from `demos/` with checkpoint data (company name, build type, phases completed)
  - **Chat bot widget**: floating chat bubble (bottom-right corner, every page) powered by the Claude API. Auto-detects `ANTHROPIC_AUTH_TOKEN` / `ANTHROPIC_BEDROCK_BASE_URL` env vars for zero-config auth, falls back to `ANTHROPIC_API_KEY` or manual entry. System prompt loaded with live context (connected orgs, existing demos, available skills). Uses Bedrock `/invoke` format for gateway compatibility.
  - **SSE progress streaming**: build progress streams to the browser in real-time via Server-Sent Events
  - **Sidebar navigation** with live connection status dots (green/gray) for Tableau and Salesforce
- **One-click installer** (`install.py` + `Install AIO.command`): double-click to install everything — checks Python 3.10+, creates a `.venv`, installs all dependencies, creates `config.json`, generates an `AIO Builder.command` launcher, and opens the web UI. Detects existing AIO installations and preserves connections + demos (upgrade in place or copy data over).
- **`requirements.txt`**: added `flask`, `anthropic`, `python-dateutil` to project dependencies

### Architecture
- **Flask backend** (`web-ui/app.py`): routes for pages + REST API endpoints for connection testing, config saving, profile switching, build orchestration, and Claude chat
- **Plain HTML/CSS/JS frontend**: no build step, no npm, no React — just Jinja2 templates and vanilla JS. Professional, clean design with dark sidebar nav.
- **Reuses existing AIO modules**: imports `connections.py` directly for auth, profile management, and live connection testing. The web UI is a presentation layer over the same Python backend.

### Context
- Core SEs and non-power-users need a friendlier interface than VS Code + Claude Code CLI. The web UI makes AIO accessible to anyone who can open a browser — guided setup, visual build wizard, and a chat assistant for questions.

---

## 2026-10-16 — Layout alignment for /transfer-assets

### Added
- **Step 6b — Layout Alignment** in `/transfer-assets`: after deploying a dashboard to a target org, the command now reads the source dashboard's exact widget positions (row, column, rowspan, colspan) and applies them to the target dashboard via PATCH or MCP `update_dashboard`. Widgets are matched by viz/metric label; unmatched widgets are appended at the bottom.
- **Automatic grid scaling**: handles source dashboards with varying column counts (48, 72, or 91 columns) by proportionally scaling positions to the target grid. This fixes the layout drift seen in the Sales Insights clone (91-col source → 48-col target).
- **Multi-page support**: each page is aligned independently when source and target have matching page counts.

---

## 2026-10-13 — Auto re-auth on expired Salesforce refresh tokens

### Changed
- **`connections.py`**: `get_sf_token()` now detects expired/revoked refresh tokens (`invalid_grant`, 30-day idle TTL enforcement) and automatically triggers the OAuth browser flow to re-authenticate — no more crashes when a token goes stale. The new refresh token is saved back to `config.json` so subsequent calls work without re-auth.

### Context
- Salesforce enforces a 30-day idle TTL on refresh tokens starting Nov 4, 2026 (production). SEs who haven't run a demo in 30+ days will hit this. Previously this caused an unhandled `raise_for_status()` crash; now it opens the browser for a one-click re-auth.

---

## 2026-10-02 — REST PATCH viz styling + SDM replication patterns

### Added
- **Two-pass viz creation pattern** for Tableau Next: MCP `create_visualization` for structure, then REST PATCH for full styling (dual-axis, per-field colors, continuous palettes, hidden axes, mark sizes, reference lines, axis titles)
- **SDM replication workflow** for `/transfer-assets`: create SDM with DOs inline, HTML-decode expressions, field apiName translation by `dataObjectFieldName`, dependency-ordered creation (params → calc dims → calc meas → metrics → relationships)
- **Dashboard assembly best practices**: `cellSpacing: 4` with gutters, metric/text widgets via `add_widget_to_dashboard`, section gaps between widget groups
- 12 new Known Pitfalls covering REST PATCH gotchas, MCP BasicViz limitations, calc field level requirements, SDM replication HTML encoding, auto-generated apiName instability, and dashboard widget creation constraints

### Key discoveries
- `PATCH /services/data/v66.0/tableau/visualizations/{id}?minorVersion=12` accepts the FULL viz spec — enables programmatic dual-axis, per-field mark colors, and all style properties that MCP's slim spec cannot express
- `edit_visualization` MCP tool only supports `changeMarkType` (global, not per-field) — REST PATCH is the correct tool for all viz styling
- `negativeValuesFormat: "NegativeSign"` is rejected by the PATCH endpoint — must omit
- SDM field apiName suffixes are not stable across delete/recreate cycles

---

## 2026-09-24 — UX: clickable buttons replace "type next" in /setup

### Changed
- **`/setup` wizard**: all "type next" / "say go" / "type done" prompts replaced with `AskUserQuestion` clickable buttons. Users now click contextual options (e.g. "App created — ready to continue" / "I need help") instead of typing free text.
- Added UX rule section at top of `setup.md` enforcing this pattern for all future step-by-step flows.

---

## 2026-09-21 — Tableau Next MCP integration + MCP Build Guide

### Added
- **MCP_BUILD_GUIDE.md**: comprehensive guide for building Tableau Next demos using the `tableau-next-pilot` MCP server, covering every phase from data upload through dashboard creation
- **MCP setup in `/setup`** (Step 4d): optional guided setup for the Tableau Next MCP server — org permission enablement, ECA creation with `mcp_api` scope, `claude mcp add` command, and connection verification
- **DDI Franchise Performance v2 demo**: full end-to-end MCP build (31,500 rows, 7 metrics, 4 vizzes, dashboard with 7 widgets + 3 global filters, business preferences, 7 live Concierge responses)
- **MCP vs REST comparison doc**: quantified efficiency gains — 80% less code, 5x more assets, zero manual post-build steps, 1,399 lines of shared library code eliminated
- **Concierge Q&A capture via MCP**: `analyze_data` tool replaces manual Concierge testing for Tableau Next demos, equivalent to Pulse BAN/Brief API flow

### Key MCP advantages documented
- `create_visualization`: slim ~10-line specs replace 400+ lines of VizQL payload construction (viz_builder.py, viz_validator.py, style_defaults.py all unnecessary)
- `update_semantic_model(businessPreferences=...)`: programmatic business preferences (was UI-only manual paste)
- `add_semantic_model_metric`: 1 call per metric with nouns + insights inline (was 3 calls: CLC + metric + noun PUT)
- `add_global_filter_to_dashboard`: dashboard filters work via MCP (400 errors via direct REST)
- `analyze_data`: live Concierge response capture for walkthrough .docx

### Notes
- MCP is Tableau Next only — Pulse, CRMA, .twb, .docx generation unchanged
- MCP is currently in pilot (`TableauPilotMCPServerEnabled` permission required)
- Direct REST approach remains the fallback for non-MCP orgs

---

## 2026-09-17 — /transfer-assets: auto-create data infrastructure in target org

### Added
- **Automatic data infrastructure creation** in `/transfer-assets`: when the target org doesn't have a matching DLO, the command now auto-creates it (schema registration, stream creation, bulk ingest) instead of requiring a separate `/build-demo` run first.
- **Data download from source org**: always pulls data directly from the source org via Data Cloud Query API — works regardless of whether the demo was built by this tool. No dependency on local CSV files.

### Changed
- `/transfer-assets` prerequisites relaxed: target org only needs Data Cloud + ingest connector configured, not a pre-existing DLO/stream.

---

## 2026-09-11 — Standardized walkthrough .docx format + Pulse Discover Questions

### Added
- **Pulse Discover Questions phase** (Phase 4b): sends 8-12 demo story questions to the Pulse Discover (Brief) API at build time and captures live AI responses. These become a dedicated section in the .docx with real Ask/Expected response pairs.
- **Setting Up Goal Lines section** in .docx: auto-generated from METRIC_CONFIG goal definitions with field-to-metric mapping and UI instructions.

### Changed
- **Walkthrough .docx structure standardized** across all build types with a section-by-section specification:
  - Pulse: Demo Scenario → Metrics Reference → Demo Click Path (Action/Audience sees) → Pulse Discover Questions (Ask/Expected response) → Setting Up Goal Lines
  - Next: Demo Scenario → Metrics Reference → Concierge Prompts (Ask/Expected response) → Business Preferences
  - CRMA: Demo Scenario → Metrics Reference → Demo Click Path
- **Label rules formalized**: "Action:" / "Audience sees:" for UI navigation (click paths); "Ask:" / "Expected response:" for AI Q&A (Concierge, Pulse Discover). Never mix them.
- **`/build-demo` skill**: when user selects `pulse` output mode, immediately ask whether to also create a Tableau Dashboard (Step 5a).

---

## 2026-08-27 — Tableau Dashboard Builder (.twb workbook generation)

### Added

**`twb_builder.py` — programmatic Tableau workbook generation and publish**

Generates valid `.twb` XML workbooks from a config dict and publishes them to Tableau Cloud via `server.workbooks.publish()`. No Tableau Desktop required — the XML is hand-authored using patterns reverse-engineered from Desktop-saved reference files.

Key features:
- Live `sqlproxy` connection to already-published datasources (no embed)
- Embedded Pulse metric tiles — live KPI cards with BAN, comparison, sparkline
- Multiple chart types: horizontal_bar, bar, line, multi-line (color split), dual_axis (bar+line combo)
- Auto-adapting dashboard layouts: 2×2 grid, side-by-side, 2+1, 3+N patterns
- Global dimension filters wired to all worksheets
- Brand-colored title text
- Deterministic UUIDs for idempotent rebuilds

Dashboard components:
- Filter row (all dimension fields as dropdown filters)
- Styled title zone (brand-colored text)
- Pulse metric tile row (renders live from Pulse metric IDs)
- Viz content grid (auto-layout based on worksheet count)

Integration:
- Added as optional Phase 5 in `/build-demo` for Pulse demos (y/n prompt)
- `get_datasource_content_url()` handles Tableau's timestamp-appended content URLs
- Requires "Allow Tableau-built extensions" in site Settings → Extensions for Pulse tiles

### Fixed

- Pulse Discover AI: documented that "Enable In-Region Model Requests Only" in the backing Salesforce org blocks Tableau Pulse AI silently — disable to fix

---

## 2026-08-06 — Add /transfer-assets Command (Cross-Org Dashboard Deployment)

### Added

**`/transfer-assets` — new skill for moving Tableau Next dashboards between orgs**

Packages a dashboard from a source Salesforce org and deploys it to a target org using the Tableau Next Package & Deploy API (`next-package-deploy.demo.tableau.com`). Solves the cross-org field name mismatch problem (auto-generated suffixes like `region6` vs `region1`) that previously made programmatic dashboard copying unreliable.

Key features:
- Guided flow: select source/target profiles, choose dashboard, deploy
- Automatic DLO name patching (source org UUID suffix → target org UUID suffix)
- "Create new" mode deploys a fresh workspace + SDM with correct field structure
- "Use existing" mode validates dependencies and builds a field mapping
- Package saved locally as `.json` for re-use if deployment fails

API endpoints discovered and documented:
- `GET /api/v1/dashboards/list` — list dashboards in connected org
- `POST /api/v1/dashboards/package` — async package job
- `POST /api/v1/deployment/deploy` — async deploy with workspace/SDM options
- `POST /api/v1/deployment/validate-requirements` — pre-flight validation

---

## 2026-08-03 — Always Build Dashboard + Fix PKCE Token Rotation

### Changed

**`/build-demo` skill — always create visualizations and dashboard for Tableau Next demos**

Previously the skill asked "Would you also like me to build a dashboard?" after creating the SDM and metrics. This resulted in workspaces appearing empty in the Tableau Next UI when users declined (or the question was skipped). Vizzes and dashboards are now always created — the workspace must have assets visible so the demo audience can see them.

### Fixed

---

## 2026-08-03 — Fix PKCE Token Rotation for Refresh Grants

### Fixed

**`connections.py` — PKCE `code_verifier` handling on refresh token grants**

Some Salesforce orgs reject `code_verifier` on refresh grants ("unexpected code verifier") while others require it ("invalid code verifier"). Previously the code tried without first, which worked — but on orgs with refresh token rotation enabled, the first attempt burned the single-use token before the retry could succeed.

**New behavior:**
- First call auto-detects whether the org requires or rejects `code_verifier` on refresh
- Saves the learned mode (`pkce_refresh_mode: "required" | "rejected"`) to the profile config
- All subsequent calls use the correct mode without probing, preventing token burn

This fixes `400 expired access/refresh token` errors on PKCE-enforced orgs with token rotation (e.g. Jordan's Tableau Next org pattern).

---

## 2026-07-21 — Self-Healing Dates Without Prep Flows

### Changed

**Pulse date refresh: replaced Prep flows with `.tdsx` calculated Date pattern**

Previous: build a `.tflx` Prep flow → publish → schedule daily/weekly → flow recalculates `DATEADD(Day_Offset, TODAY())` at runtime. Required scheduling, could fail, added maintenance burden.

New: publish `.hyper` with stored Date (indexes immediately) → create metrics → overwrite with `.tdsx` containing `Date = DATEADD('day', [Day_Offset], TODAY())`. Self-heals forever with zero maintenance — no flow, no scheduling, no refresh needed.

**How it works:**
- `TODAY()` is an unstable function — Tableau re-evaluates it on every query and never materializes it into the extract
- The calculated `Date` field slides forward by one day automatically, every day, with no intervention
- Metrics survive the overwrite because the LUID is preserved and the field name (`"Date"`) stays the same

### Added

**`tdsx_builder.py`** — new module for self-healing Pulse datasources:
- `publish_hyper_for_indexing(df, date_column, ...)` — Step 1: publish `.hyper` with stored Date
- `convert_to_self_healing(df, date_column, ...)` — Step 2: overwrite with `.tdsx` (call AFTER metrics are created)
- `build_hyper_with_date()` / `build_tdsx()` — lower-level builders

### Important

- **Metrics must be created BETWEEN steps 1 and 2** — after the `.hyper` indexes but before the `.tdsx` overwrite
- `prep_flow_builder.py` is kept as a fallback but is no longer the primary approach
- The "Actions Required" section for Pulse builds no longer needs a "Schedule the flow" step
- Restore point: `git tag pre-tdsx-selfheal` — revert with `git reset --hard pre-tdsx-selfheal` if needed

---

## 2026-07-09 — /update Overhaul + Walkthrough Format Standard + Parallel Research

### Fixed

**/update now guarantees identical code across all users (eliminates merge conflicts)**

Previously, `/update` used `git pull` which could fail with merge conflicts when Claude had made local inline fixes to shared files during a build session. Users would get stuck in a conflicted state or end up with stale/divergent code.

**What changed:**
- Replaced `git pull` with `git reset --hard origin/main` — forces all tracked files to match the repository byte-for-byte
- `config.json` is stash-protected (never overwritten)
- `demos/` folder is gitignored (never touched)
- No confirmation prompt — `/update` always proceeds immediately

**Why this matters:** When a bug is found and fixed during one user's session, the fix gets pushed to git. Previously, other users might not get that exact fix due to merge conflicts or local divergence. Now every `/update` guarantees they're running the same code.

### Added

**Walkthrough .docx format standard (codified in CLAUDE.md)**

All demo walkthroughs now follow a consistent 4-section structure:
1. **Demo Scenario** — About the company + Audience & Story
2. **Metrics Reference** — "What it measures" / "Why it matters" per metric
3. **Concierge Prompts** — Ask / Expected response pairs (live from Pulse Discover API when available)
4. **Business Preferences (SDM)** — Copy-paste text for Concierge configuration

This ensures every demo walkthrough feels like the same polished product regardless of who built it or which use case.

**Parallel company research during /build-demo**

Research agent now launches in the background immediately after learning the company name, while the conversation continues (use case, persona, signal, metrics, advanced mode questions). Eliminates 30-90 seconds of dead wait during the build flow.

**Platform indexing outage documentation**

Added guidance for HTTP 400706 errors from Tableau Cloud's catalog indexing service. This is a platform-side issue (not a code bug) that occasionally affects `prod-useast-b` and other pods. Users now get clear instructions: wait for recovery, then retry via checkpoint.

### How to get this update

**If you already have git set up:**
```
/update
```
That's it. The new `/update` command will hard-reset your tracked files to match the repo.

**If you've never updated before or hit a merge conflict previously:**

Run these commands manually in your terminal (from the AIO Analytics Builder directory):
```bash
git fetch origin main
git reset --hard origin/main
```
This will fix any conflicted state and put you on the latest code. Your `config.json` and `demos/` folder will not be affected.

**After updating:** Start a new Claude Code session so the updated skill files and CLAUDE.md take effect.

---

## 2026-07-06 — Prep Flow Auto-Refresh + Build Workflow Restructure

### Added

**`prep_flow_builder.py` — Automated date refresh via Tableau Prep flows**

Programmatically builds self-contained `.tflx` Prep flows that keep Pulse demo dates fresh automatically. The flow embeds the CSV data with relative day offsets and calculates `Date = DATEADD('day', [Day_Offset], TODAY())` at runtime. When scheduled daily/weekly on Tableau Cloud, demos never go stale.

- `build_prep_flow(df, date_column, datasource_name, ...)` — generates the .tflx
- `publish_and_run_flow(flow_path, flow_name, ...)` — publishes to Tableau Cloud and triggers execution

**Post-build "Actions Required" section**

Every `/build-demo` completion now prints a clear **Actions Required** section listing only the manual steps the user is responsible for (schedule the flow, set goals, paste business preferences). Each action has Where/Do/Why format.

### Changed

**Pulse build order restructured: flow-first approach**

Previous: publish .hyper → create metrics → create flow (afterthought)
New: build Prep flow → run flow (creates published datasource) → create metrics against it

Benefits:
- Datasource is "owned" by the flow from the start
- No separate `.hyper` publish step needed
- No auth mismatch when the flow overwrites on scheduled runs
- Single source of truth: the flow IS the datasource publisher

### Fixed

**Pulse definition ID parsing**

The POST `/api/-/pulse/definitions` response wraps everything under a `"definition"` key:
```
resp["definition"]["metadata"]["id"]      → definition ID
resp["definition"]["metrics"][0]["id"]    → metric ID (no separate GET needed)
```
Previously documented as `resp.get("metadata", {}).get("id")` which returned None.

---

## 2026-06-23 — Fix Pulse Insights API language/locale enum format

### Fixed

**Brief API requires enum-format `language` and `locale` fields**

The Pulse brief endpoint (`POST /api/-/pulse/insights/brief`) requires `"LANGUAGE_EN_US"` and `"LOCALE_EN_US"` — not plain strings like `"en"` or `"en_US"`. Using plain strings causes a silent 400 "Invalid request" with no detail about which field is wrong.

---

## 2026-06-23 — Add /update command

### Added

**`/update` slash command** — Pulls the latest version from git, shows what changed, and summarizes updates in plain language. Other SEs can now run `/update` instead of manually running `git pull`.

---

## 2026-06-23 — Fix allowed_dimensions format + response parsing in Pulse payloads

### Fixed

**Pulse `allowed_dimensions` must be flat strings, not objects**

`extension_options.allowed_dimensions` requires a flat list of field name strings (e.g. `["Region", "Program Type"]`). Using objects like `[{"field": "Region"}]` causes a silent 400 "Invalid request". Updated CLAUDE.md Known Pitfalls and build-demo skill with the correct format.

**Pulse definition creation response parsing**

Definition ID is nested under `metadata.id` in the POST response — not at the top level or under `definition.id`. Incorrect parsing caused `def_id=None`, which broke the `GET /definitions/{def_id}/metrics` call and prevented subscriptions from being created in the same run.

---

## 2026-06-23 — Pulse 2026.2 Payload Fix + Canary Validator

### Fixed

**Pulse metric creation broken after Tableau Cloud 2026.2 release**

Root cause: 2026.2 added stricter payload validation to `POST /api/-/pulse/definitions`. Fields that were previously optional are now required, and aggregation/format combinations are now validated. The generic 400 "Invalid request" error gives no detail about which field is wrong — took 4 days of debugging to isolate.

**New required fields in 2026.2:**
- `extension_options` — must be present (with `allowed_dimensions`, `allowed_granularities`, etc.)
- `insights_options` — must be present (can have empty `settings: []`)
- `comparisons` — must be present (can have empty `comparisons: []`)

**New validation rules:**
- `AGGREGATION_AVERAGE` requires `is_running_total: false` — combining AVERAGE with running total now returns 400
- `NUMBER_FORMAT_TYPE_PERCENTAGE` cannot be used with `AGGREGATION_SUM`
- Sentiment must use SCREAMING_SNAKE format (`SENTIMENT_TYPE_UP_IS_GOOD`, not `SentimentTypeUpIsGood`)
- Subscriptions payload changed to flat format: `{"metric_id": "...", "followers": [{"group_id": "..."}]}`

### Added

**Pulse API Canary Validator** (`pulse_validator.py`)
- Runs against 10ax.online.tableau.com (first pod to receive each release)
- Tests 8 payload variations: AVERAGE/SUM/COUNT aggregations, NUMBER/CURRENCY formats, sentiment types, PATCH, subscriptions
- Integrated into `/build-demo`: runs automatically weekly or when the canary pod's build version changes
- If tests fail, warns the user that a breaking change is incoming before it hits their production site
- Credentials stored in `config.json` (pulse_validation profile), not hardcoded

### Changed
- Updated `CLAUDE.md` Known Pitfalls with 2026.2 payload requirements
- Updated `/build-demo` Phase 3 (Pulse metrics) with correct payload format and code example
- Renamed `/refresh-demo` → `/refresh-dates` (Pulse-only, clarified in all docs)
- Moved Advanced Mode from step 0b to step 4c (after metrics are decided)

---

## 2026-06-23 — Session Summaries + CRMA in About Info

### Added
- **Session summaries** — `/build-demo` now saves a structured session summary after every build (company, decisions, assets, resume instructions). Enables "pick up where you left off" in future conversations.
- **New/resume prompt** — `/build-demo` now asks at the start whether this is a new build or resuming an existing one. If resuming, loads the session summary and skips completed phases.
- **Generic session summaries** — long working conversations (troubleshooting, debugging, multi-step projects) offer to save a summary at the end for future context restore.
- **Updated README + OVERVIEW** — CRMA now listed as the 4th output mode alongside Pulse, Next, and CSV in all project documentation.

---

## 2026-06-19 — Rename /refresh-demo → /refresh-dates

### Changed
- Renamed `/refresh-demo` skill to `/refresh-dates` to clarify its purpose
- Updated description: this is **Pulse-only** — Tableau Next demos use self-healing Display Date formula and never need refreshing
- Simplified the Tableau Next section in the skill (just notes dates are self-healing, no re-ingest offered)
- Updated all references across CLAUDE.md, OVERVIEW.md, README.md, and build-demo.md
- Moved Advanced Mode in `/build-demo` from step 0b (before company name) to step 4c (after metrics are decided) — signal tuning is more meaningful once you know the actual metrics

---

## 2026-06-16 — CRM Analytics (CRMA) Output Mode

### Added

**CRM Analytics as 4th output mode** (`crma_uploader.py`, `crma_dashboard_builder.py`)
- Full dataset upload via InsightsExternalData API (metadata → base64 CSV chunks → process → poll)
- Automatic field schema generation from METRIC_CONFIG and dimension lists
- CRMA dashboard builder: SAQL steps (time series, grouped bars, KPIs), chart widgets, filter dropdowns, text headers
- Brand color integration: background container, text colors, chart themes
- App/folder management: find_or_create_app for organizing assets
- Security predicate helper for row-level security on datasets
- CRMA guidance document integrated into build flow (SAQL pitfalls, PATCH rules, field naming)

---

## 2026-06-10 — Viz Template Library + Validation Engine + Dashboard Builder

### Added

**Visualization template library** (`viz_templates.py`, `viz_builder.py`)
- 9 chart templates: trend_over_time, multi_series_line, bar_by_category, stacked_bar, horizontal_bar, donut, scatter, heatmap, funnel
- Auto-recommends chart types from METRIC_CONFIG based on field names and aggregation patterns
- Builds complete API payloads with correct fields, encodings, style, marks, legends
- Infers number formats (%, $, decimals) from field name patterns
- Supports brand color palettes and style overrides
- Adapted from alaviron/tableau-skills template library (internal Salesforce)

**Pre-POST validation engine** (`viz_validator.py`)
- 17 rules checking all known API failure modes before hitting the endpoint
- Validates: root fields, view structure, visualSpecification keys, marks structure, style (fonts/lines/axis/encodings/headers), encoding field references, donut requirements, size encoding support
- Catches errors locally instead of learning from 400 responses
- Returns actionable fix suggestions for each failure

**Dashboard layout builder** (`dashboard_builder.py`)
- 4 layout patterns: standard (3 metrics + 2x2 vizzes), metrics_heavy (6 metrics + 3 vizzes), story_flow (3 metrics + wide hero + 2-up), wide_viz (3 metrics + 2 full-width)
- Auto-selects pattern based on widget counts
- Produces complete dashboard payload with widgets dict, layouts, containers
- ASCII preview generation for user confirmation before building
- 72-column grid with rowspan 15 metric cards (matches our existing preference)

**Style defaults module** (`style_defaults.py`)
- Font builder (7 required keys), line builder (4 keys), shading, field labels
- Brand color override system
- Number format helpers for axis, encoding, and header fields
- Marks header/panes style builders with all v66.12 required fields

---

## 2026-06-05 — Pulse Refresh Pattern + Dynamic Offset + /refresh-demo Rewrite

### Changed

**Pulse date freshness: refresh-based instead of self-healing**
- `.tdsx` packages NEVER index on Tableau Cloud (confirmed: 14+ hours with no indexing, across multiple tests with both hand-crafted and Cloud-format `.tdsx` files)
- True self-healing via calculated fields is not possible for Pulse on Tableau Cloud
- New pattern: publish `.hyper` → set `use_dynamic_offset: True` via PATCH → run `/refresh-demo` before meetings to regenerate data anchored to today
- Metrics survive `.hyper` datasource overwrites — no deletion/recreation needed on refresh

**`/refresh-demo` rewritten from scratch**
- Old purpose: upgrade legacy demos to `.tdsx` self-healing (no longer applicable)
- New purpose: regenerate data + re-publish `.hyper` to keep Pulse dates fresh
- Supports refreshing a single demo by slug or all demos at once
- ~30 seconds to refresh (data gen + publish)
- Optional Tableau Next re-ingest for demos that also use Data Cloud

### Added

**Pulse 26.2 API findings documented**
- `extension_options` must be set via PATCH (not accepted in POST create payload)
- `temporality: 'TEMPORALITY_UNSPECIFIED'` causes 400 on create — field is read-only
- PATCH Content-Type: `application/vnd.tableau.metricqueryservice.v1.UpdateDefinitionRequest+json`

---

## 2026-06-04 — Pulse .hyper Direct Publish Fix

### Fixed

**Pulse datasource indexing: publish .hyper directly, never .tdsx**
- Publishing `.tdsx` packages causes Pulse to take 2+ hours (or indefinitely) to index the datasource — metric creation fails with 404 "Not Found" during that window
- Publishing `.hyper` directly allows Pulse to index in seconds and metric creation succeeds immediately
- Root cause: Pulse's internal discovery system processes raw `.hyper` files on a fast path but queues `.tdsx` packages for deferred processing
- Updated all Pulse publish calls to use `server.datasources.publish(ds_item, hyper_path, "Overwrite")` instead of `.tdsx`
- Pulse metric `time_dimension` now references raw `Date` column (not calculated `Display Date`)

---

## 2026-06-03 — Viz Field Role Exclusivity + Summary Clarity

### Fixed

**Visualizations: field role exclusivity rule**
- Added a guard to prevent placing the same semantic field in both a grouping slot (dimension/columns) and an aggregation slot (measure/rows) in the same visualization
- This caused charts to silently fail to render — reported by a user whose build needed manual correction
- Rule added to both `build-demo.md` Phase 5 instructions and `CLAUDE.md` Known Pitfalls

### Improved

**Final summary: business preferences callout**
- The post-build summary now explicitly tells the user that Business Preferences are at the end of the walkthrough `.docx` file, includes the full file path, and reminds them where to paste it in the SDM UI

---
## 2026-05-29 — Pulse Goals/Thresholds + HCHSP Demo

### Added

**Pulse goals/thresholds support (data-side + documented manual setup)**
- `METRIC_CONFIG` now supports an optional `goal` dict with `value`, `field`, `name`, `direction`
- Data generation adds constant target columns to the datasource (e.g. `Attendance Target = 0.85`)
- Walkthrough `.docx` includes a "Setting Up Goal Lines" section with field-to-metric mapping table
- Company research step now explicitly calls out finding regulatory thresholds and compliance targets

**Known Pitfall: Pulse `datasource_goals` API is non-functional**
- Tested all payload variations: `basic_specification`, `threshold_basic_specification`, minimal — all return 400 "Invalid request"
- PATCH/PUT on existing definitions also fails
- Workaround: include target columns in datasource + document 2-minute UI setup

**HCHSP (Hidalgo County Head Start Program) demo built**
- 27 campuses across 8 ISDs in Hidalgo County, TX
- Metrics: Attendance Rate (85% federal threshold), Dental Completion, Screening Compliance, Family Referral Rate
- Signal: rural ISDs (Monte Alto, Mercedes, La Joya) declining below federal floor; urban campuses masking the problem
- Full walkthrough `.docx` with federal compliance context (45 CFR citations)

---

## 2026-05-28 — Self-Healing Dates (Tableau Next + Pulse)

### Changed

**Both platforms now use self-healing Display Date formulas — no `/refresh-demo` needed**

The same logic applies to both Tableau Next and Pulse:
```
DATEADD("day", DATEDIFF("day", #<build_date>#, [date_field]), TODAY())
```
Each row's date is shifted forward by the number of days elapsed since the build. `TODAY()` evaluates at query time on both platforms, so the most recent data always appears as "today" automatically.

**Tableau Next**: Self-healing calculated dimension on the SDM. Metrics reference it via `{"calculatedFieldApiName": "Display_Date"}`.

**Pulse**: Self-healing calculated field embedded in a `.tdsx` package (ZIP of `.tds` XML + `.hyper`). Pulse evaluates `TODAY()` fresh on every query because "unstable functions" are excluded from extract materialization.

### Key findings
- SDM calculated dimensions use `#YYYY-MM-DD#` hash-delimited date literals (not `DATE(y,m,d)`)
- Metric `timeDimensionReference` for calc dims must use `calculatedFieldApiName` (not `tableFieldReference`)
- Pulse `.tdsx` calc fields use single quotes: `DATEADD('day', ...)`; SDM uses double quotes
- Tableau Cloud evaluates `TODAY()` at query time for both published extracts and SDM expressions

### Updated files
- `CLAUDE.md` — unified date-shifting rule, new Known Pitfall for `calculatedFieldApiName`
- `.claude/commands/build-demo.md` — Phase 2 documents `.tdsx` packaging; Phase 4 documents self-healing calc dim
- `.claude/commands/refresh-demo.md` — reframed as legacy upgrade tool only
- `OVERVIEW.md` — both platforms documented as self-healing
- `README.md` — Step 5 now says "no action needed"

---

## [Unreleased]

---

## 2026-05-21 — Field Descriptions for AI Optimization

### Added

**Automatic field descriptions on every SDM measurement and dimension**
- `METRIC_CONFIG` entries now carry a `description` field; it is included in the measurement PUT payload (same call as `aggregationType` — no extra round-trip)
- A `DIM_DESCRIPTIONS` dict at the top of each demo script maps dimension field names to plain-language descriptions written for Concierge to read ("Use this field to..." style)
- After DO creation, a loop PUTs descriptions on every filterable dimension via `PUT /services/data/v65.0/ssot/semantic/models/{sdm}/data-objects/{do}/dimensions/{api}`
- Descriptions are generated during the company research phase so they reflect the actual use case and terminology

These descriptions appear in the Tableau Next UI and are the primary signal the Analytics AI Agent uses to understand what each field means. Without them, Concierge cannot accurately answer questions about the data.

---

## 2026-05-21 — Conversational Analytics Principle + TriNet Dimension Expansion

### Added

**Conversational analytics design principle**
- Added a core design principle to both `build-demo.md` and `CLAUDE.md`: every demo must let the audience answer four questions — What is wrong? Where is it worst? Why is it happening? Who is most at risk?
- Dimensions must be designed to support each layer of that conversation, not just produce a chart
- Signal amplification by segment (high-cost plans hit harder, micro clients harder than mid-market, specific regions lead) so filtering feels like discovery, not decoration

**TriNet demo — drillable dimensions**
- Added `plan_cost_tier` (Low/Mid/High) and `workforce_type` (Technical/Administrative/Sales/Mixed) to client generation — with realistic distributions by vertical (Tech/Life Sciences skew High cost; Nonprofits skew Low)
- Added three benefit category metrics: `medical_enrollment_rate`, `dental_enrollment_rate`, `voluntary_plan_enrollment_rate` — with differentiated signal decay (voluntary drops at 1.8× the primary signal, medical at 0.2×) to show cost-sensitive benefits drop first
- All new dimensions denormalized into the fact table so the SDM can filter by them (IngestAPI DLO join workaround)
- Signal now amplified by segment: High-cost tier × 1.5, Micro size × 1.3, Northeast/West regions × 1.2–1.3 — creating a real investigative story
- Dashboard expanded to 3 rows of vizzes (6 total): overall trend, voluntary opt-in, voluntary plan breakdown, medical trend, utilization, satisfaction
- Metric tiles updated to show Benefits Enrollment Rate, Voluntary Opt-in Rate, Voluntary Plan Rate as the three opening KPIs
- `additionalDimensions` on metrics now includes vertical, size_band, region, state, plan_cost_tier, workforce_type

---

## 2026-05-21 — Update Check on Skill Launch

### Added

**Automatic update check in `/build-demo` and `/setup`**
- Both skills now run `git fetch origin main` at startup and compare the remote commit count to the local HEAD
- If the remote is ahead, the user is prompted to pull before continuing, with a summary of what changed (`git log --oneline`)
- If the user declines, the build or setup proceeds with their current version
- Failures (no network, not a git repo) are silently ignored

---

## 2026-05-21 — Autonomous Mode Persisted + TriNet Build Fixes

### Changed

**Autonomous mode is now always on**
- The `allow` block in `.claude/settings.local.json` is no longer removed after each build — autonomous mode persists across sessions
- `/build-demo` no longer asks "would you like to run autonomously?" at the start of each session
- Instead, it notifies the user at build start that autonomous mode is active and explains how to switch to manual mode by typing "manual mode"

### Fixed

**Bulk ingest: daily-grain fact tables were losing all but the last day**
- Root cause: fact stream was created with `client_id` as the sole primary key; `upsert` with a non-unique PK overwrites previous rows, leaving only the final day's data
- Fix: added a `record_id` surrogate key (`date_clientid`, e.g. `2025-05-21_TN-10051`) as the stream PK so each client×day row is unique
- Note: the Bulk Ingest API only supports `upsert` and `delete` — `insert` returns 400

**Rate metrics displayed as decimals instead of percentages**
- CLCs for rate metrics (stored as decimals 0–1) now multiply by 100: `AVG([DO].[field]) * 100`
- Viz format suffix and axis format updated to `%` with 1 decimal place for rate fields
- Non-rate metrics (e.g. satisfaction scores) use a separate format with no suffix
- `METRIC_CONFIG` entries now carry an `is_rate` flag to control CLC expression and viz formatting

**Dashboard container widgets missing from widgets dict**
- Container widgets referenced in the layout's `page_widgets` were not included in the top-level `widgets` dict, causing 500 "Cannot invoke EntityObject.getId()"
- Fix: every widget name in the layout must have a corresponding entry in `widgets` with `type`, `name`, `actions: []`, and `parameters`

**Schema registration always updates existing schemas**
- Phase 1 previously skipped schema registration if the schema name already existed on the connector
- Fix: always PUT the current `FACT_FIELDS`/`DIM_FIELDS` definitions, replacing stale schemas — ensures new fields (e.g. `record_id`) are picked up without manual cleanup

### Added (CLAUDE.md pitfalls)

- Bulk Ingest: only `upsert` and `delete` are valid operations; `insert` returns 400
- Bulk Ingest: daily-grain fact tables need a surrogate `record_id` PK (`date_clientid`)
- Schema registration: PUT always replaces — don't skip if schema already exists when fields have changed
- Dashboard: all widget names in the layout must have entries in the `widgets` dict, including containers
- Dashboard widget entries need `actions: []`, `name`, `type`, `source`, and `parameters`

---

## 2026-05-14 — Retry Cleanup Extended to Workspace + SDM

### Fixed

**Stale SDMs and workspaces from failed runs**
- Extended the retry cleanup pattern (previously applied only to vizzes/dashboards in phase 6) to the workspace and SDM creation phase (phase 4)
- `all_ws_apis` and `all_sdm_apis` are now tracked in the checkpoint alongside `all_viz_apis` and `all_dash_apis`
- At the start of each phase 4 run, all previously created workspaces and SDMs in those lists are deleted before new ones are created, preventing accumulation of stale assets across retries
- Derived checkpoint keys (`ws_api`, `sdm_api`, `do_api`) are cleared before recreation so the phase always starts clean

---

## 2026-05-14 — Business Preferences, Brand Colors, Retry Cleanup, Advanced Mode

### Added

**Business Preferences for Tableau Next SDMs**
- The build now generates SDM-level Business Preferences text tailored to the company and use case — structured as `#`-prefixed instruction lines covering entity context, leading vs. lagging indicators, diagnostic dimensions, terminology, and time comparison defaults
- Text is saved to the checkpoint, included as a dedicated "Business Preferences (SDM)" section in the concierge walkthrough `.docx`, and printed in the final summary with a clear callout to paste it into the SDM manually
- Note: there is no public REST API for this field — it must be set in the UI (Data 360 → Semantic Model → [SDM] → AI Optimization → Manage Business Preferences)

**Brand Colors for Tableau Next dashboards**
- `/build-demo` now asks whether to use brand colors when building a Tableau Next demo for a real company
- If yes, Claude researches the company's brand guidelines and applies a `BRAND` dict (primary, secondary, chart_bg, text, dash_bg) to dashboard background/gutter and visualization shading/fonts
- Dark primary colors are automatically tinted: each channel blended 90% toward 255 (e.g. `#033C5A` → `#E6F1F6`)
- If no, or for fictitious companies, defaults to `#F3F3F3` background and `#2E2E2E` text

**Advanced Mode for `/build-demo`**
- Optional mode unlocked at the start of each session — never saved to config
- Configures four parameters per build:
  - **History length** — 6 / 12 / 24 (default) / 36 months
  - **Time grain** — daily / weekly / monthly (default); warns on daily + 36 months combination
  - **Signal design** (per primary metric) — severity (15% / 25% / 40% / custom), onset (−3 / −6 / −9 months), and shape (ramp / accelerating / step)
  - **Supporting metric strength** — subtle (8%) / moderate (12% default) / strong (18%)

**Cross-org OAuth error handling in `/setup`**
- Added two new troubleshooting blocks to the Salesforce OAuth browser flow step:
  - `invalid_client_id`: app not yet activated — wait 2–10 minutes and retry
  - `Cross-org OAuth flows are not supported`: browser is logged into the wrong org — sign out of all Salesforce sessions, log back into the target org, then retry

### Fixed

**Retry cleanup for Tableau Next phase 6**
- Vizzes and dashboards created during failed phase 6 runs are now tracked in `cp["all_viz_apis"]` and `cp["all_dash_apis"]` in the checkpoint
- At the start of each phase 6 run, all previously created assets in those lists are deleted before new ones are created
- These lists are never cleared on phase reset — they survive across retries so stale assets from any prior run are always cleaned up
- Safety rule: Claude will only delete assets that appear in those checkpoint lists; any other deletion requires explicit user confirmation

**VizQL visualization format**
- Rewrote `make_viz` to use the correct VizQL format: `layout: "Vizql"`, columns/rows as field-key arrays, all required top-level and style keys present
- Fixed series of 400 errors from missing required fields: `encodings`, `headers` (style + marks), `legends`, `lines`, `marks.panes`
- `style.marks.headers` now uses the `_marks_headers_style()` pattern
- `marks.panes` is a direct object specifying the chart type, not nested under `default`
- `style.lines` uses explicit keys — `{"referenceLines": {}}` is invalid
- `legends` is required at the top level of `visualSpecification`; use `{}` when no color dimension

**DLO status polling**
- Fixed status field path: `body.get("dataLakeObjectInfo", {}).get("status") or body.get("status", "UNKNOWN")` — the top-level `status` field is not always present
- Added 30-second post-ACTIVE wait before submitting bulk ingest jobs to allow schema propagation

---

## 2026-05-12 — Initial Release

### Added

- **`/setup`** — guided one-time configuration wizard for Tableau Cloud (PAT) and Salesforce (OAuth + Data Cloud); discovers or creates an Ingest API connector; supports multiple named profiles in `config.json`
- **`/build-demo`** — story-driven demo builder with three output modes:
  - **Tableau Pulse** — publishes `.hyper` datasource, creates Pulse metric definitions with correct granularities, creates a group, and subscribes it to all metrics
  - **Tableau Next** — pushes data to Data Cloud via Bulk Ingest API, builds a Semantic Data Model with relationships, calculated measurements, and metrics, then creates visualizations and a dashboard
  - **CSV export** — exports the generated dataset for use in any viz tool
- **Synthetic data generation** — 24 months of history, one row per entity per month, with an engineered signal ramp over the last 6 months
- **Concierge walkthrough `.docx`** — generated automatically with ordered Concierge prompts and talking points for each demo
- **Checkpoint/resume** — each build writes a `{slug}_checkpoint.json` after each phase so interrupted runs can resume without re-ingesting data or re-creating assets
- **`connections.py`** — centralized auth module; all demo scripts import from here, never inline credentials
- **`config.json.template`** — safe-to-commit template showing required credential fields
