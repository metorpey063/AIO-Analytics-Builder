# /data-app — Build a Data App for Tableau Next or Tableau Cloud

Build a data app on any semantic model (Tableau Next) or published datasource (Tableau Cloud). Claude
designs the page from the data and the demo's story; AIO checks every query against the data, then
publishes and verifies it. Standalone: it isn't part of `/build-demo`, but AIO demos are listed first and
their story drives the page.

---

## What this does

| | Tableau Next | Tableau Cloud |
|---|---|---|
| The app | A React page in a workspace (asset type Data App), on one semantic model | A web page packaged as a viz extension inside a workbook, on one published datasource |
| Who writes it | Claude: `src/app.spec.json` (queries + filters) and the page, against `dataapps/assets/next_reference.md` | Claude: the VizQL Data Service queries and `app.js`, against AIO's runtime `dataapps/assets/cloud/aio.js` (`cloud_reference.md`) |
| AIO checks | Every query through the semantic engine gateway; page imports and ids | Every query through the VizQL Data Service; ids, filter fields, JS syntax |
| Publish | tableau-next-pilot MCP: `create_data_app` → `edit_data_app` → `publish_data_app` (server build check) → deploy | `.twbx` from the tableau-mcp template, published with TSC |
| Verify | The app is listed in the workspace | The rendered view is saved as `demos/{slug}/{slug}_data_app.png` |

The app lands in `demos/{slug}/` (the source's AIO demo folder when there is one), checkpoint
`{slug}_data_app_{next|cloud}.json`.

---

## Prerequisites

- **Tableau Next:** a Salesforce connection with its MCP login (Connections → Authorize MCP), and the org's
  Setup → **Tableau Next Features** → **Data Apps (Beta)** turned on (an admin toggle with no API; without it the
  MCP has no data app tools). Not available in Exploratory orgs.
- **Tableau Cloud:** a Tableau Cloud connection (PAT), and the site's Settings → Packages → **Allow Packages**
  turned on (without it the view shows "Packages are not enabled on this site"; the build checks and stops).
  The PAT's user needs API Access on the datasource.
- Claude credentials (the same ones AIO uses for story generation).

---

## How to run

**Use `python3 -m dataapps` for every step — never hand-write the MCP calls, the .twbx or the queries.**
The Web UI's Data Apps pages (homepage cards) run the same engine. Guide the user one step at a time with
buttons (AskUserQuestion), not "type next".

### Step 1 — Platform and connection

Ask Tableau Next or Tableau Cloud, then which connection (from `config.json` profiles: Salesforce
connections for Next, Tableau Cloud for Cloud). Show the label and org/site URL.

### Step 2 — Data and destination

```bash
python3 -m dataapps next sources --profile <key>     # demos, models, workspaces
python3 -m dataapps cloud sources --profile <key>    # demos, datasources, projects
```

Offer the AIO demos first (`demos`), then the other sources. Destination: the demo's own workspace / Pulse
project by default; otherwise ask.

**No data yet? Describe it.** When the customer's use case has no data in the org (e.g. Coeur Mining tracking
haul trucks, parking spots and loaders by mineral at one site), offer "Describe it" instead of a source:

```bash
python3 -m dataapps <next|cloud> describe --plan --company "Coeur Mining" --description "..."   # read-only
python3 -m dataapps <next|cloud> describe --profile <key> --company "Coeur Mining" --description "..."
```

`--plan` has Claude design an event-level data model (one fact row per event, dimensions incl. derived ones
like Loader → Mineral, measures with a distance cost, site positions on a 0-100 grid), generates a year of
mock data with the problem engineered in and runs the signal check. Show the printed summary and the signal
check, and confirm before the real run. The real run loads the data (Next: Data Cloud stream + semantic
model + metrics in a new workspace, through the Build Demo engine with `data_only`; Cloud: a new project and
a self-healing published datasource), saves it as an AIO demo in `demos/{slug}/`, then builds the app on it
with a site map when the data has positions. The design is saved (`{slug}_data_app_scenario.json`) and reused
while the company and description don't change.

### Step 3 — What the app should answer

Optional. Blank builds around the demo's story (AIO demo) or what the data shows.

### Step 4 — Build (writes to the org / site — confirm first)

```bash
python3 -m dataapps next build --profile <key> --source <SDM apiName> --dest <workspace name> [--ask "..."]
python3 -m dataapps cloud build --profile <key> --source <datasource LUID> --dest <project LUID> [--ask "..."]
```

3–8 minutes. Prints `[step] …` lines and a final `RESULT {json}` with the app URL and Claude's summary.
For Cloud, show the user the rendered image (Read `demos/{slug}/{slug}_data_app.png`).

### Step 5 — Revise or remove

```bash
python3 -m dataapps <next|cloud> build ... --feedback "what to change"   # a new version of the same app
python3 -m dataapps cloud repackage --slug <slug>                         # republish as is (newer AIO runtime)
python3 -m dataapps <next|cloud> remove --slug <slug>                     # deletes only the app
```

---

## Troubleshooting

- **Next: "has no MCP login"** — authorize MCP for the connection on Connections.
- **Next: tools missing / create_data_app unknown** — the org's Data Apps (Beta) toggle is off.
- **Next: the MCP's check_data_app_queries / get_data_app_check stay "pending"** — expected: they need the preview
  that only Claude Desktop / claude.ai render. AIO checks queries through the gateway instead.
- **Cloud: "Packages are turned off"** — a site admin turns on Settings → Packages → Allow Packages.
- **"still fails the checks after 3 tries"** — the failing checks are printed; simplify `--ask` or run again.
