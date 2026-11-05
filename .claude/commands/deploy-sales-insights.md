# /deploy-sales-insights — Deploy Sales Insights to any org with Data Cloud

Deploys a standalone copy of Tableau Next **Sales Insights**: the six original dashboards (Sales Performance, Team Performance, Leaderboard, Sales Stage Progression, Sales Stage Conversion, Lead Analysis), their 68 vizzes, and the semantic model behind them (136 calcs, 9 parameters, 7 metrics, 17 joins). The data is synthetic, seeded, and dated relative to today. The org needs Data Cloud and an AIO profile, but **not** the managed Sales Insights app or any CRM data.

All logic lives in the `salesinsights/` package; this command only orchestrates. Design and verified API findings: `salesinsights/DESIGN.md`.

```
python3 -m salesinsights deploy --profile <key>   # checkpointed; rerun resumes where it stopped
python3 -m salesinsights status --profile <key>   # what's deployed, what failed
python3 -m salesinsights reset  --profile <key>   # delete only what the deploy created
python3 -m salesinsights generate --out <dir>     # data only, no org writes
python3 -m salesinsights capture --from <dir>     # maintainer: rebuild package/ from Package & Deploy exports
```

## Usage

- `/deploy-sales-insights`: full deploy to an org you pick
- `/deploy-sales-insights --status` / `--reset`: checkpoint summary / clean removal
- `/deploy-sales-insights --refresh`: re-anchor the data to today (`reset` then `deploy`; ~15 min)

## Steps

1. **Pick the org.** Show the Salesforce profiles from `config.json` with their instance URLs, using `AskUserQuestion` buttons. Never pick the Tableau Next & Slack org: it's the source, and `deploy` refuses it. Profile labels can be misleading (`default`, labeled "Tab Next Dev", points at the source org), so go by instance URL. If the target has no AIO profile, run `python3 org_bootstrap.py apps|wait|authorize --alias <sf alias> --profile <key>` (or `/setup`). It needs one browser login.
2. **Confirm** what will be created: one workspace "Sales Insights", one SDM, 15 `si_*` data streams/DLOs on the profile's ingest connector, 68 vizzes and 6 dashboards. If the org already has these from an earlier deploy, `deploy` reuses the checkpoint; asset names that clash with someone else's get a `_2` suffix.
3. **Run** `python3 -m salesinsights deploy --profile <key>` in the background and report each phase as it finishes. It takes about 10–15 minutes, mostly Data Cloud stream activation and ingest. Phases: preflight → data → sdm → semantic → vizzes → dashboards → verify.
4. **If a phase fails,** read the error and `status`, check CLAUDE.md Known Pitfalls and `salesinsights/DESIGN.md` §7, fix the cause, and rerun `deploy`. It resumes from the checkpoint and never recreates finished assets. Add genuinely new API findings to Known Pitfalls.
5. **Verify** is part of `deploy`: it waits for ingest, then requires every dashboard widget and dynamic token to read back `Ok` and every metric to return data.
6. **Finish in the UI** (tell the user):
   - Share the workspace: Share → All Internal Users → View (the API rejects sharing).
   - If `deploy` printed that business preferences weren't accepted, paste `semanticModel.businessPreferences` from the package into the SDM (Data 360 → Semantic Model → AI Optimization → Manage Business Preferences).

## The demo story (baseline data)

- **Team Harbor is behind.** Rachel Kim's team wins ~29% of closed deals vs ~42–44% for Summit and Ridge, with smaller deals.
- **Pushes and stalls cluster on two Harbor reps**, Lucas Moreau and Mateo Silva (Sales Stage Progression → Pushed / Stalled; Leaderboard).
- **Lead conversion** runs from ~60% (Referral) to under 10% (Trade Show) (Lead Analysis).
- **Open deals with no activity** fill the Leaderboard "No Activity" tab.
- Sales leader: Morgan Reyes. Use the "Team Member" filter (managers) to drill from the leader to a team.

All names are fictional. The data is anchored to the day it was generated, and the "last 7 days" comparisons and quarter views drift as it ages, so refresh before a meeting if the deploy is more than a couple of weeks old.

## Ground rules

- Only `reset` deletes, and only what this profile's checkpoint lists. Never delete other assets in the org.
- Source quirks are kept on purpose (e.g. Open Pipeline counts only `Pipeline` history rows; Average Days to Close is computed close → create). The one deliberate calc fix is listed in `salesinsights/capture.py` `SOURCE_FIXES`.
- If Claude Code's auto mode blocks a write, ask the user to allow `Bash(python3 -m salesinsights:*)`. Never work around a block.
