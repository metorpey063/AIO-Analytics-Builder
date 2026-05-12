# /build-demo — Analytics Builder Demo Generator

Build a complete demo for a prospect or use case. This command generates synthetic data with an engineered story signal, then lets you choose which outputs to create.

## Prerequisites

### For Tableau Pulse builds
Run `/setup` first. All connections must show OK before building a demo.

### For Tableau Next builds (allow 1–2 hours before starting)

Before running `/setup` or `/build-demo` for a Tableau Next demo, the Salesforce org must be provisioned and configured. This takes time — start this process well before your demo session.

**Step 1 — Get a demo org**
- Request a **CDO (Clean Demo Org)** or **SDO (Standard Demo Org)** from your SE resources
- Wait for the provisioning email

**Step 2 — Activate the org**
- Confirm your email address from the provisioning email
- Log in and change your password

**Step 3 — Enable Data Cloud**
- Go to **Data Cloud Setup** in the App Launcher
- Click the button to start the Data Cloud setup wizard and complete it

**Step 4 — Enable Tableau Next**
- Go to **Salesforce Setup** (gear icon → Setup)
- Search for **Tableau** in the Quick Find box
- Open the Tableau Next setup guide and complete through **Step 4**

Once all four steps are done, run `/setup` to connect your credentials and then come back here to build the demo.

---

## What this builds

Based on your inputs, the demo builder will:

1. **Generate synthetic data** — realistic monthly data for your chosen use case with an engineered signal (a deliberate metric decline that tells a story)
2. Let you choose one or more **output modes**:

| Mode | What gets built |
|------|----------------|
| **Pulse** | Publishes a .hyper datasource to Tableau Cloud, creates Pulse metric definitions, creates a group, subscribes the group to all metrics |
| **Tableau Next** | Pushes data to Salesforce Data Cloud, builds a Semantic Data Model, creates metrics and calculated fields, creates visualizations and a dashboard |
| **CSV Export** | Exports the generated dataset as a CSV file in the `demos/` folder |

---

## How to run

When you invoke `/build-demo`, Claude will ask you the following questions one at a time. You don't need to have all answers ready — work through them conversationally.

### 0. Autonomous mode

**Ask this first, before anything else:**

> "Would you like me to run autonomously — executing scripts and reading files without asking for confirmation at each step? This makes the build faster and hands-off. You can say no to step through each action manually. (yes / no)"

**If yes — enable autonomous mode:**

Write the following into `.claude/settings.local.json`, preserving any existing `env` block:

```json
{
  "permissions": {
    "allow": ["Bash(*)", "Read", "WebFetch(*)"]
  },
  "env": {
    "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "16384"
  }
}
```

Then tell the user:
> "Autonomous mode enabled for this session. I'll run the build without stopping for confirmations. You'll see everything I do in the transcript."

Proceed through all phases without pausing.

**If no — manual mode:**

Do not modify `settings.local.json`. Tell the user:
> "Manual mode — I'll describe each step before running it and wait for your go-ahead."

Pause before each Bash execution and Read, briefly describe what it does, and wait for the user to confirm.

**After the build completes (either mode):**

Remove the `allow` block from `.claude/settings.local.json`, leaving only the `env` block:

```json
{
  "env": {
    "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "16384"
  }
}
```

Tell the user: "Permissions restored to default — the next session will ask for confirmation again unless you choose autonomous mode."

### 1. Company name
Ask the user for the company name, and include this note when asking:

> "If this is a real company, I can research their industry, product lines, regions, and go-to-market model to make the demo data and story much more relevant — real segment names, realistic deal sizes, accurate geographies. If it's a fictitious company, the demo will still be compelling but more generic. Real company = better demo."

Use the answer to determine how much research to do in the Company Research step — real company gets web searches, fictitious company gets reasonable industry defaults.

### 2. Use case / industry
What business problem are we telling a story about? Examples:
- Corporate travel compliance declining
- Hotel booking revenue at risk
- Loan originations falling in a specific region
- Customer churn in subscription services
- Operational cost overruns in logistics

### 3. Persona
Who is the primary viewer of this demo? (e.g. VP of Finance, Chief Revenue Officer, Head of Operations). This shapes which metrics matter most.

### 4. Story signal
What is the "uh oh" moment in the data? The signal is a deliberately engineered decline that creates urgency. Examples:
- Bookings through the platform down 18% over last 6 months
- Off-platform spend increasing in a specific region
- Net Promoter Score declining among enterprise accounts

### 4b. Primary metric(s)
Which 1–2 metrics carry the story? These are the ones the demo click path leads with — they get a strong, obvious signal that any viewer can see at a glance.

The remaining metrics are **supporting context**: they show correlated movement (e.g. issues up when CSAT is down) but their signal is softer. They answer "why" when the audience digs in, but they don't compete for attention up front.

Examples:
- Primary: CSAT Score. Supporting: Issues Reported, Resolution Hours, Platform Booking Rate
- Primary: Platform Booking Rate. Supporting: CSAT Score, NPS Score
- Primary: Loan Origination Volume. Supporting: Approval Rate, Time-to-Close

**Signal design rule:**
- Primary metric: exaggerate for storytelling impact — a 25–40% drop over 6 months creates a clear "uh oh" moment that's unmissable in a sparkline. Real-world anomalies of 5–10% matter operationally but don't land in a demo. The goal is to make the audience say "wow, something is clearly wrong here" within the first 10 seconds.
- Supporting metrics: softer correlated drift — 8–15% movement is enough to tell a causal story when the audience digs in, without stealing attention from the primary signal.
- The ramp should be smooth (use the `signal_ramp` function), not a sudden cliff — a gradual deterioration looks like a real emerging problem, not synthetic data.

Apply this when generating the data and when writing the walkthrough document — the demo flow should always open on the primary metric and use supporting metrics only to answer follow-up questions.

### 5. Output mode
Choose one or more:
- `pulse` — Tableau Pulse metrics
- `next` — Tableau Next + Data Cloud
- `csv` — CSV export only
- `all` — all three

### 5b. Brand colors (only ask if output includes `next` or `all`, and only for real companies)

> "Would you like me to look up {Company}'s brand guidelines and apply their official colors to the Tableau Next dashboard? (yes / no)"

- If **yes**: include brand color research as step 4 of the Company Research section (search `{Company} brand guidelines color palette`). Define a `BRAND` dict at the top of the script and apply colors to the dashboard background, gutter, and viz shading/fonts as described in the Brand colors section below.
- If **no**: skip brand research entirely. Use the default neutral palette (`dash_bg: "#F3F3F3"`, `chart_bg: "#FFFFFF"`, `text: "#2E2E2E"`) and omit the `BRAND` dict from the script.

Do not ask this question for fictitious companies or for CSV/Pulse-only builds.

---

## Token limits

Demo scripts are long — writing one from scratch can hit Claude's output token limit mid-write. When this happens:

> "I've hit the output token limit while generating the script. To avoid this in future sessions, go to **Claude Code → Settings → Max output tokens** and increase it to 32000 or higher. For now, I'll split the remaining script into smaller sections and write them in sequence."

The current project is configured with `CLAUDE_CODE_MAX_OUTPUT_TOKENS=16384` in `.claude/settings.local.json`. To permanently raise it:
1. Open `.claude/settings.local.json`
2. Change `"CLAUDE_CODE_MAX_OUTPUT_TOKENS": "16384"` to `"CLAUDE_CODE_MAX_OUTPUT_TOKENS": "32000"`

When writing a demo script and the limit is low, break the write into 4 sequential chunks:
- **Chunk 1**: Header, imports, parameters, auth, data generation
- **Chunk 2**: Pulse phases (hyper file, metric creation, group subscription)
- **Chunk 3**: Next phases 1–5 (schema, streams, DLO wait, bulk ingest, ingest polling)
- **Chunk 4**: Next phases 6–10 (workspace, SDM, measurements, metrics, vizzes, dashboard, docs, summary)

Each chunk appends to the file — create it with `Write` on chunk 1, then use `Edit` to append for chunks 2–4.

## Company research (do this before writing any data)

Before generating numbers, spend 3–4 web searches to ground the demo in reality:

1. **The company itself** — industry, primary product lines, go-to-market model (direct/channel/PLG), typical customer segments, notable regions or markets
2. **Industry benchmarks for the use case** — e.g. for sales: average win rates by segment (Enterprise ~20–25%, SMB ~30–40%), typical sales cycle lengths, realistic quota sizes and attainment distributions (median attainment ~80–100%, top quartile ~120–140%, rarely >150%)
3. **Any use-case-specific context** — e.g. for a hotel chain: actual property categories they operate (full-service, select-service, extended-stay), real regions/markets they operate in, realistic ADR and occupancy ranges
4. **Brand guidelines** — search `{Company} brand guidelines color palette` to find official hex codes for primary and secondary brand colors. Most large companies publish these on their communications or marketing sites.

Use these findings to:
- Name dimensions with real values (real regions, real product lines, real customer segments) not generic placeholders like "Region A"
- Set base metric values and noise ranges that match industry norms
- Write story talking points that reference the company's actual business context
- Apply brand colors in the Tableau Next dashboard (see Brand colors section below)

### Brand colors (Tableau Next only — only if user said yes in step 5b)

After finding the brand colors, define a `BRAND` dict at the top of the script with primary, secondary, and background colors:

```python
BRAND = {
    "primary":    "#XXXXXX",   # dominant brand color — used for dashboard background tint
    "secondary":  "#XXXXXX",   # accent color — used for shading/banding
    "chart_bg":   "#FFFFFF",   # almost always white
    "text":       "#2E2E2E",   # body text — use dark brand color if available, else near-black
}
```

Apply these colors in the dashboard and visualizations:
- **Dashboard `style.backgroundColor`** and **`style.gutterColor`**: use a light tint of the primary brand color. If the primary is dark (e.g. navy), compute a ~10% tint: mix toward white (`mix(primary, #FFFFFF, 0.10)` logic — do this manually from the hex). If the brand palette includes an explicit light/background color, use it directly.
- **Viz `style.shading.backgroundColor`**: set to `BRAND["chart_bg"]` (usually `#FFFFFF`)
- **Viz `FONTS`**: set `color` fields to `BRAND["text"]`

**Tint formula** (for dark primaries — when primary luminance is below 50%):
Take the primary hex, blend each channel 90% toward 255: `tint = hex(round(channel + (255 - channel) * 0.90))`. E.g. `#033C5A` → `#E6F1F6`.

If brand colors cannot be found after searching, fall back to a neutral light gray (`#F3F3F3`) for backgrounds and `#2E2E2E` for text — never leave placeholder hex codes in the script.

**Realistic base values (healthy period):**
- Quota attainment: 88–102% is realistic for a healthy team; the signal drop should bring it to 60–75% — painful but not apocalyptic
- Win rates: 18–28% Enterprise, 28–38% Commercial, 35–48% SMB for SaaS
- Sales cycle: 90–120 days Enterprise, 30–60 days Commercial, 7–21 days SMB
- CSAT: 4.1–4.5/5.0 is healthy; decline target 3.5–3.8
- NPS: 35–55 is good for SaaS; decline target 15–25
- Revenue: calibrate deal_count × avg_deal_size to land within 5% of monthly_quota in healthy months
- Percentages: always store as decimals (0.35 not 35)

**Signal magnitude (engineered, not realistic):**
- Primary metrics: 25–40% decline over 6 months — exaggerate for visual impact, this is a demo not a forecast
- Supporting metrics: 10–18% decline — corroborating but not competing for attention
- The base (pre-signal) period should look stable with mild noise, so the decline reads as a clear inflection

Always sanity-check: print the min/max/mean of derived metrics (e.g. quota attainment) before finalising the data generation code. If anything looks implausible, recalibrate the base values.

## Build process

### For Pulse output:

**Phase 1 — Data generation**
- Create a DataFrame: 24 months of history, one row per entity per month
- Engineer the signal: metric declines over the last 6 months using a ramp function
- All percentages stored as decimals (0.35 not 35)
- Column names business-friendly with spaces and proper caps

**Phase 2 — Publish to Tableau Cloud**
- Connect via PAT (from config.json)
- Clean up any existing project/datasource with the same company name
- Create a timestamped project: `{Company} | {YYYY-MM-DD HH:MM}`
- Write a .hyper file and publish as a datasource
- Inject `display_date` calculated field so the demo stays current

**Phase 3 — Create Pulse metrics**
- POST each metric to `/api/-/pulse/definitions`
- GET `/definitions/{id}/metrics` to retrieve metric ID (NOT definition ID)
- Classify each metric before creating it:
  - Flow (sum, YTD): volume, revenue, originations
  - Rate/Average (average, last month): percentages, ratios, scores
  - Snapped (sum, last month): balances, headcount, pipeline
- Include at minimum GRANULARITY_BY_MONTH, GRANULARITY_BY_QUARTER, GRANULARITY_BY_YEAR

**Phase 4 — Create group and subscribe**
- POST XML to create a group named `{Company} | {YYYY-MM-DD HH:MM}`
- POST to `/api/-/pulse/subscriptions:batchCreate` for each metric ID

### For Tableau Next output:

**Phase 1 — Data generation** (same as above)

**Phase 2 — Register schema + streams**
- GET existing schemas from the connector, merge new schemas (don't replace)
- POST to create data streams for fact and dimension tables
- Wait for DLO status to reach `ACTIVE` (poll every 10s, up to 5 min)

**Phase 3 — Bulk ingest**
- Submit all bulk ingest jobs in parallel (submit all, then poll)
- Use DC token (not SF token) and dc_domain (not sf_instance)
- Response key is `"data"` not `"jobs"`
- Wait for state `"JobComplete"` — this can take 5-10 minutes; that's normal
- New schemas need 15-30s before bulk API accepts them — retry on 404

**Phase 4 — Build workspace + Semantic Data Model**
- Create workspace via `/services/data/v65.0/tableau/workspaces`
- Create SDM with `agentEnabled: true`
- Add relationships between fact and dimension tables
- Add calculated measurements (KPIs) and calculated dimensions (date shift)
- Add semantic metrics at creation time with `singularNoun` / `pluralNoun` filled in

**Phase 4b — Business preferences (Concierge language)**
After all metrics are created, PUT each metric back with natural-language nouns that Concierge uses to generate responses. Pattern: GET the metric, update `insightsSettings.singularNoun` / `pluralNoun` / `sentiment`, strip read-only fields, PUT back.
- Endpoint: `PUT /services/data/v66.0/ssot/semantic/models/{sdm}/metrics/{metric_api}?minorVersion=12`
- Strip these fields before PUT: `id`, `createdBy`, `createdDate`, `lastModifiedBy`, `lastModifiedDate`
- Good noun examples: `"deal closed"` / `"deals closed"`, `"in-person sales activity"` / `"in-person sales activities"`
- Sentiment: `"SentimentTypeUpIsGood"` or `"SentimentTypeUpIsBad"`

**Phase 5 — Visualizations + Dashboard**
- Create 4 visualizations (bar + line charts for key metrics)
- Create a dashboard with metric tiles and filters
- Dashboard page `name` must be a UUID string
- `widgets` must be a dict, not a list
- Omit `"headers": {}` from visualization style

**Retry cleanup — always do this at the start of the viz/dashboard phase:**

Track every viz and dashboard created across all runs (including failed ones) in the checkpoint under `all_viz_apis` and `all_dash_apis`. These lists are **never cleared when resetting phase6** — they accumulate so that a retry always knows what to clean up.

At the start of the viz/dashboard phase, before creating anything new:
1. DELETE every entry in `cp["all_dash_apis"]` and `cp["all_viz_apis"]`
2. Reset both lists to `[]` in the checkpoint
3. After each successful creation, immediately append the new name to the list and save the checkpoint

This ensures only one complete, working set of assets survives each run.

**Asset ownership rule (critical):**
- Only ever delete assets whose names are in `all_dash_apis` / `all_viz_apis` in the checkpoint — i.e. assets this script created
- Never delete assets created outside this script (manually, by another build, etc.)
- If a user asks you to delete assets during a session, confirm the asset name appears in the checkpoint before proceeding. If it doesn't, say: "I don't have a record of creating that asset — please confirm you want me to delete it before I proceed."

**Phase 6 — Post-build steps**
- Create a dedicated subfolder for this demo: `demos/{company_slug}_{use_case_slug}/`
- Write the demo guide markdown file there (`{slug}_guide.md`)
- Generate a Concierge walkthrough `.docx` file there using python-docx (`{slug}_demo_walkthrough.docx`)
- Print a final summary block with:
  - All created asset names (metric names, viz names, dashboard name)
  - Direct URL to the Tableau Next workspace/dashboard
  - Direct URL to Tableau Pulse
  - Absolute file paths to the guide and walkthrough (so the user can click them)
- Remind user: enable Analytics Agent Readiness toggle in Data 360 → Semantic Model → Settings

### For CSV output:

- Generate the same DataFrame as above
- Export to `demos/{company_slug}_{use_case_slug}/{company_slug}_{use_case_slug}_{date}.csv`
- Print the file path

---

## Naming conventions

| Asset | Format |
|-------|--------|
| Project / Group | `{Company Name} \| {YYYY-MM-DD HH:MM}` |
| Datasource | `{Company Name} - {Use Case}` |
| Workspace / SDM | `{company_slug}_{use_case_slug}` |
| DLO objects | `{company_slug}_Fact_{Entity}`, `{company_slug}_Dim_{Entity}` |
| Demo subfolder | `demos/{company_slug}_{use_case_slug}/` |
| Script filename | `demos/{company_slug}_{use_case_slug}/{company_slug}_{use_case_slug}_demo.py` |
| Demo guide | `demos/{company_slug}_{use_case_slug}/{company_slug}_{use_case_slug}_guide.md` |
| Concierge walkthrough | `demos/{company_slug}_{use_case_slug}/{company_slug}_{use_case_slug}_concierge_walkthrough.docx` |
| CSV export | `demos/{company_slug}_{use_case_slug}/{company_slug}_{use_case_slug}_{date}.csv` |

---

## After the build

For Pulse:
- Visit your Tableau Cloud site → Pulse
- The group will already be subscribed to all metrics
- Metrics will show the engineered signal in the default time range

For Tableau Next:
- Visit your Tableau Next workspace
- Enable Analytics Agent Readiness: Data 360 → Semantic Model → Settings → Analytics Agent Readiness → toggle ON
- The Concierge panel is now ready for Q&A demos
- Open the walkthrough `.docx` — it contains the exact Concierge prompts to use during the demo

Note: the Tableau Next Concierge does not have a public REST API — it is UI-only. Automated testing of Concierge responses is not currently possible programmatically.

For CSV:
- Open the file in Tableau Desktop, Excel, or any viz tool
- Use it to build custom views or upload to another platform

---

## Cleanup

To remove a demo and all its assets, Claude can run cleanup steps on request. Specify the company name and timestamp to target a specific build.
