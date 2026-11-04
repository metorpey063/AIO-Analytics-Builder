# /update-rev-intel — Tailor a demo org's Revenue Intelligence data to a customer

Re-skins a shared demo org's CRM data so **Revenue Intelligence** (Revenue Insights + Einstein Account Management) tells a story built for one customer and use case: their products, segments, team, renewal motion and the problem they want to solve. It then refreshes CRM Analytics in the right order and verifies the dashboards' data.

It changes **real CRM records** in the org: accounts in a shared demo pool, opportunities, line items, contacts, activities, users, roles, territories and quotas. Everything it loads carries a demo external ID, every destructive step writes a CSV backup first, and loads are insert-only, so re-runs never duplicate.

All logic lives in the `revintel/` package and `crma_refresh.py`. This command only orchestrates. Customer specifics live in `demos/{slug}/config.py` (template: `revintel/config_template.py`; worked example: `demos/knowbe4_renewals/kb4_config.py`). The web UI calls the same CLI.

```
python3 -m revintel demos/{slug} inspect | plan | apply | team <people|reassign|quotas> | refresh | reset
```

## Usage

- `/update-rev-intel {slug}`: full flow (inspect → design → plan → apply → refresh → verify)
- `/update-rev-intel {slug} --refresh`: Data Sync + recipes only
- `/update-rev-intel {slug} --dates`: date refresh (reset, then apply anchored to today)
- `/update-rev-intel {slug} --inspect`: read-only org survey

No slug: list `demos/` folders that have a revintel config and ask which, or offer a new one.

## Ground rules

- **Align everything to the customer and use case.** Research the company (products, pricing model, segments, regions, go-to-market), and read any requirements doc the SE shares (a BRD, RFP or discovery notes). Every product, segment, stage, field and story beat should trace back to that research or doc. Ask when the research doesn't say.
- **Never upload CSVs over CRM Analytics datasets.** Edit CRM records and run the recipes (CLAUDE.md Known Pitfalls).
- **Only delete what the build created or the user approved.** One-off cleanup of another tool's leftovers is an explicit, backed-up step that the user confirms. Records owned by shared personas belong to other demos.
- Use `AskUserQuestion` buttons at each decision. Show the plan's story stats before any org write.

## Steps

### 1. Connect and inspect (read-only)
1. Find the org: `sf org list`. The sf CLI alias goes in `ORG_ALIAS`. AIO `config.json` profiles may point at a different org, so check the instance URL.
2. Create `demos/{slug}/` with a minimal `config.py` (just `ORG_ALIAS`), then run `inspect`. Read `out/inspect.json` and resolve every warning with the user:
   - **Duplicate template apps** (e.g. two "Customer Insights 2"): find which one the dashboards read; offer to remove the other.
   - **EAM filters**: note the current Opportunity/Account record-type answers; they'll need **Reconfigure** in step 6.
   - **Two "Standard Price Book"s**: use the `IsStandard` Id.
   - **Scheduled Apex**: read each job's class body. Demo-refresh jobs (e.g. `SalesInsightsRefresh`) create, close and re-date opportunities and write quotas. Patch them to skip `Demo_External_ID__c` records and pool accounts, or pause them, with the user's OK. Keep the original class in `demos/{slug}/apex/orig/`.
   - **Shared personas**: if the team users own other demos' opportunities, plan `team reassign`.
3. Look for leftovers from earlier tools (MeshMesh, CSV loads): stray line items, re-labelled products, duplicate renewals. Back up, then clean only with the user's approval.

### 2. Design the story with the user
Write it into `config.py`. Present each block and confirm it:
- **Products:** catalog, list prices and price book entries (create Product2 + PBEs if missing). Set `CORE_PRODUCT`, a `CHURN_PRODUCT` if the story has product churn, `LAUNCHED_PRODUCTS`, attach rates by size and expansion weights. Whitespace should read as "most own the core, fewer own the add-ons".
- **Segments:** region × size teams with owners and territories. Follow the CLAUDE.md signal rules: one or two culprit segments (`mult` 1.5–2.5), moderate segments (~1), flat (~0.3), one counter-trend (-0.05…-0.15). Add a leading indicator (the `drop` signal precedes `churn`) and loss-reason mixes from the org's dependent picklist (save it to `loss_reasons.json`).
- **Team:** aim for **7–9 people directly under the sales leader** in Revenue Insights. `LEAD_ROLES` puts each lead in a child role of `SALES_LEADER_ROLE` as forecast manager; add `SUB_ROLES` for one drill level. Use existing SDO personas, or fictional `NEW_USERS` (never real customer employees' names). Hybrid leads get `OWNER_SPLITS`. If the use case has one, include a split-role example (HR line outside the team, forecast line through a territory).
- **Territories:** mirror the customer's forecast structure. Every open renewal needs a territory with a forecast manager and an unbroken chain to the top (no orphans).
- **Forecast-window asks** from the AE (e.g. "renewals for Cindy and Ely closing Nov–Jan, various stages, ATR ≠ Amount"): set them in `FOCUS`.
- **Pool:** reuse tagged `AIO-POOL` accounts, or pick unused accounts (no opportunities, contacts, cases, orders or assets) and write `pool_seed.json` with re-skinned names for the customer's regions.

### 3. Plan (local)
`python3 -m revintel demos/{slug} plan`. Check the story stats with the user: churn by segment by half-year (culprit rising, counter-trend flat), open renewals by stage, co-terms, products dropped, whitespace, win rate. Tune `config.py` and re-plan until it reads right. Nothing touches the org yet.

### 4. People, then data
1. `team people`: creates new users and lead roles (before the data, so owners exist).
2. `apply`: sales process (optional), external-ID field, managers, territories, pool accounts and record type, contacts, opportunities, line items, activities, owners. Checkpointed; a failed step can be re-run safely.
3. `team reassign` (if needed), then `team quotas`.

If Claude Code's auto mode blocks a write, ask the user to add an allow rule such as `Bash(python3 -m revintel:*)`, one rule per entry. Never try to work around a block.

### 5. App configuration (user, in the UI)
- **EAM Reconfigure:** Analytics Studio → Einstein Account Management → Reconfigure. Opportunity record types must include the renewal record type. Account record type = `POOL_RECORD_TYPE` only, so the page lists just the customer's accounts. Keep every other answer (products = Yes; if asked for the supporting Customer Insights app, pick the one the dashboards read). Back up the EAM recipe first, then diff it after the rebuild.

### 6. Refresh
`python3 -m revintel demos/{slug} refresh`. Data Sync, then the recipe chain in dependency waves (about 45–60 minutes). If the user needs to close the laptop, queue the remaining recipes in Salesforce in dependency order (the org runs one recipe at a time).

### 7. Verify
- `EAM_OpptyProduct` / `Product2` datasets show the customer's product families; `AD_Accounts` has Pipeline / Win Rate / YTD for the pool.
- Revenue Insights quota dataset: the leader's quota = the sum of the leads; each lead appears under the leader (`inspect` → "people under leader"); previous-month attainment is believable (no blank rows, no 1,000%+).
- Ask the user to open the dashboards (Claude can't render them).

### 8. Walkthrough summary
Write a short "what was generated" note for the AE: renewal counts per owner and territory, close-date months, stages, ATR vs Amount, product details, supporting history and the team hierarchy. Offer to save a session summary.

### Date refresh (`--dates`)
`reset` (deletes the pool's demo opportunities, contacts and activities), then `apply --today`, `team quotas` and `refresh`. The same story, re-anchored to today.
