# /build-demo — AIO Analytics Builder Demo Generator

Build a complete demo for a prospect or use case. This command generates synthetic data with an engineered story signal, then lets you choose which outputs to create.

---

## Core design principle — conversational analytics

**The goal is never just a chart. The goal is a problem the audience can solve.**

Every demo must be designed so the presenter can walk through a sequence of questions with the audience:

1. **What is wrong?** — The primary metric drops visibly. The audience sees it in 10 seconds.
2. **Where is it worst?** — Filtering by Vertical, Region, or Size Band reveals which segment is driving the decline.
3. **Why is it happening?** — Category breakdowns (e.g. Voluntary plan enrollment drops before overall enrollment) and supporting metrics explain the cause.
4. **Who is most at risk?** — Dimensions like Plan Cost Tier, Workforce Type, or State identify specific clients or groups to act on.

When designing data for a demo, always ask: *"Can the audience answer all four questions using only the filters and metrics I've built?"* If not, add dimensions until they can.

**Dimension rules:**
- Denormalize all categorical dimensions into the fact table — IngestAPI DLO joins silently drop criteria (see CLAUDE.md Known Pitfalls). Every filterable field must be a column on the fact row.
- Include at least one *cost/effort* dimension (Plan Cost Tier, Deal Size, Spend Bucket) — this is almost always the root cause the audience cares most about.
- Include at least one *who/where* dimension set (Region, Vertical, Size Band, State).
- Include category breakdowns that decompose the primary metric — e.g. Medical vs Dental vs Voluntary enrollment, or New Logo vs Expansion vs Renewal revenue.

**Signal rules:**
- Amplify the primary signal differently by segment so filtering *reveals the story*: e.g. High-cost clients drop hardest, Micro clients harder than Mid-Market, specific verticals or regions lead the trend. This makes filtering feel like discovery.
- Supporting metrics should lag the primary signal slightly — they answer *why* after the audience has already seen *what*.

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

### -1. Update check

**Do this before anything else, every time.**

Run:

```bash
git fetch origin main 2>/dev/null && git rev-list HEAD..origin/main --count
```

- If the command fails (no network, not a git repo, etc.) — skip silently and continue.
- If the result is `0` — skip silently and continue.
- If the result is **1 or more** — tell the user:

> "There's an update available for AIO Analytics Builder (`N` commit(s) ahead of your local version). Run `git pull` to get the latest before continuing, then re-run `/build-demo`. Would you like to update now, or continue with your current version?"

  - If they say **update**: run `git pull origin main` and confirm what changed (`git log HEAD~N..HEAD --oneline`). Then continue the build as normal.
  - If they say **continue**: proceed without pulling.

### 0. Autonomous mode

**Autonomous mode is always on** — the `allow` block is already present in `.claude/settings.local.json`. Do not ask whether to enable it, and do not remove it after the build completes.

At the very start of every `/build-demo` run, before any other output, tell the user:

> "Running in autonomous mode — I'll execute scripts and read files without asking for confirmation. To turn this off, type **manual mode** at any time and I'll switch to asking before each step."

If the user types "manual mode" during the build, pause before every Bash and Read, describe what you're about to do, and wait for confirmation. Do not remove the `allow` block from `settings.local.json` even in manual mode — just change your own behavior.

### 0b. Advanced mode

Ask immediately after the autonomous mode question:

> "Would you like to use **Advanced Mode**? This unlocks extra configuration options — data history length, time grain, and fine-grained signal tuning. Recommended if you have a specific use case or audience in mind. (yes / no)"

- If **no**: skip to Step 1. Use defaults: 24 months history, monthly grain, standard signal ramp.
- If **yes**: ask the following questions one at a time before proceeding to Step 1.

Advanced mode is asked fresh each session — never saved to config.

---

**A. Data history length**

> "How much historical data should the demo show?
> 1. **6 months** — tight, recent story; good for fast-moving metrics like pipeline or NPS
> 2. **12 months** — one full year; shows seasonality and a clean year-over-year comparison
> 3. **24 months** — default; enough history to make the signal look like a real emerging trend
> 4. **36 months** — long view; good for strategic/executive audiences who think in multi-year cycles"

Store as `HISTORY_MONTHS` (6 / 12 / 24 / 36). Default if not asked: 24.

---

**B. Time grain**

> "What time grain should the data use?
> 1. **Daily** — granular; good for operational metrics (support tickets, transactions, outreach response time). Warning: generates a lot of rows — works best with 6–12 months of history.
> 2. **Weekly** — balanced; good for sales pipeline, engagement metrics, or anything reviewed in weekly standups
> 3. **Monthly** — default; cleanest sparklines in Tableau Pulse and Next; recommended for executive and strategic demos"

Store as `GRAIN` (daily / weekly / monthly). Use `freq='D'`, `'W'`, or `'MS'` in `pd.date_range` accordingly. Default if not asked: monthly.

If the user picks **daily + 36 months**, warn them:
> "That combination will generate a very large dataset (~1,000+ rows per entity). I'd recommend 12 months for daily grain, or switching to weekly if you need the longer history. Would you like to adjust?"

---

**C. Signal design — per primary metric**

Run through C1, C2, C3 for each primary metric in turn.

**C1 — Severity**
> "How dramatic should the decline in **[metric name]** appear in the sparkline?
> 1. **Subtle** (~15% drop) — early warning signs; good for 'we caught it early' stories
> 2. **Moderate** (~25% drop) — clear downward trend; unmissable but not alarming
> 3. **Severe** (~40% drop) — crisis-level signal; maximises urgency and the 'uh oh' reaction
> 4. **Custom** — I'll tell you the exact percentage"

Store as `signal_magnitude` (0.15 / 0.25 / 0.40 / custom float). Default if not asked: 0.37.

**C2 — Onset**
> "When should the decline start?
> 1. **6 months ago** — default; decline is clearly visible in the most recent sparkline period
> 2. **3 months ago** — very recent; makes the story feel urgent and unresolved
> 3. **9 months ago** — longer trend; good for 'this has been building for a while' narratives"

Store as `signal_onset` (-6 / -3 / -9). Default if not asked: -6.

**C3 — Shape**
> "How should the decline unfold?
> 1. **Gradual ramp** — default; smooth linear decline that looks like a real emerging problem
> 2. **Slow then accelerating** — flat for a while, then drops sharply at the end; good for 'tipping point' stories
> 3. **Step change** — one visible drop then levels off; good for 'something changed in the business' narratives (e.g. a product launch, a policy change)"

Store as `signal_shape` (ramp / accelerating / step). Default if not asked: ramp.

Implement the shapes in the `signal_ramp` function:
- **ramp**: `min(1.0, (months_from_onset) / duration)` — current default
- **accelerating**: `min(1.0, ((months_from_onset) / duration) ** 2)` — quadratic curve
- **step**: `1.0 if months_from_onset >= duration * 0.3 else 0.0` — drop at 30% through the window then flat

---

**D. Supporting metric signal strength**

> "How clearly should the supporting metrics move in the data?
> 1. **Subtle** (~8% movement) — barely perceptible; lets the primary signal dominate completely
> 2. **Moderate** (~12% movement) — default; visible on closer inspection, tells a causal story
> 3. **Strong** (~18% movement) — clearly correlated; good if you want the audience to connect the dots quickly"

Store as `supporting_magnitude` (0.08 / 0.12 / 0.18). Default if not asked: 0.12.

---

**Applying advanced settings in the script:**

Define all advanced parameters near the top of the script, clearly grouped:

```python
# ── Advanced settings ────────────────────────────────────────────────────────
HISTORY_MONTHS        = 24       # 6 / 12 / 24 / 36
GRAIN                 = "monthly"  # daily / weekly / monthly
SIGNAL_MAGNITUDE      = 0.37    # primary metric decline (fraction)
SIGNAL_ONSET          = -6      # months before today when decline starts
SIGNAL_SHAPE          = "ramp"  # ramp / accelerating / step
SUPPORTING_MAGNITUDE  = 0.12    # supporting metric movement (fraction)
```

Update the `signal_ramp` function to accept `onset`, `shape`, and `duration` parameters. Update date range generation to use `HISTORY_MONTHS` and `GRAIN`. Print a summary of all advanced settings at the start of each script run.

---

### 1. Company name
Ask the user for the company name, and include this note when asking:

> "If this is a real company, I can research their industry, product lines, regions, and go-to-market model to make the demo data and story much more relevant — real segment names, realistic deal sizes, accurate geographies. If it's a fictitious company, the demo will still be compelling but more generic. Real company = better demo."

Use the answer to determine how much research to do in the Company Research step — real company gets web searches, fictitious company gets reasonable industry defaults.

### 1b. Supporting materials
Immediately after the company name, ask:

> "Do you have any notes, documents, or context you'd like to share to help refine the demo? For example: call notes, a brief, a discovery deck, an email thread, specific metrics they care about, or any files I can read. This is optional — I'll also do my own research — but anything you provide will make the demo more tailored. (paste text, drag in a file, or skip)"

- If the user provides text, a file path, or drags in a document: read and incorporate the content into the Company Research phase. Extract any mentioned metrics, dimensions, personas, pain points, goals, or terminology and use them to inform all subsequent steps.
- If the user says **skip** or similar: proceed without additional context.

This step is especially valuable for real customer demos where the SE has call notes, a discovery brief, or specific asks from the account team.

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
4. **Goals, thresholds, and compliance targets** — search for regulatory requirements, SLA commitments, or industry-standard targets that define "good" vs "bad" for this company's metrics. Examples: federal 85% attendance (Head Start), 99.9% uptime SLA, 30-day close rate target, NPS > 40, 95% screening compliance. These become goal lines on Pulse sparklines and make the demo viscerally urgent.
5. **Brand guidelines** — search `{Company} brand guidelines color palette` to find official hex codes for primary and secondary brand colors. Most large companies publish these on their communications or marketing sites.

Use these findings to:
- Name dimensions with real values (real regions, real product lines, real customer segments) not generic placeholders like "Region A"
- Set base metric values and noise ranges that match industry norms
- Write story talking points that reference the company's actual business context
- **Define goal/threshold values** for each metric and include constant target columns in the datasource (e.g. `Attendance Target = 0.85`) — these enable one-click goal setup in the Pulse UI
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
- Write a `.hyper` file with the physical data
- **Publish the `.hyper` directly** — `server.datasources.publish(ds_item, hyper_path, "Overwrite")`
- IMPORTANT: Do NOT publish a `.tdsx` for Pulse. Pulse indexes `.hyper` in seconds but takes 2+ hours to index `.tdsx` packages, causing metric creation to fail with 404.

**Phase 3 — Create Pulse metrics**
- POST each metric to `/api/-/pulse/definitions`
- GET `/definitions/{id}/metrics` to retrieve metric ID (NOT definition ID)
- Use `"time_dimension": {"field": "Date"}` (the raw Date column — Pulse handles time display natively)
- Classify each metric before creating it:
  - Flow (sum, YTD): volume, revenue, originations
  - Rate/Average (average, last month): percentages, ratios, scores
  - Snapped (sum, last month): balances, headcount, pipeline
- Include at minimum GRANULARITY_BY_MONTH, GRANULARITY_BY_QUARTER, GRANULARITY_BY_YEAR

**Phase 3b — Goals / Thresholds (manual setup, auto-documented)**

Pulse goals cannot be set programmatically via the REST API (`datasource_goals` field always returns 400 "Invalid request" regardless of payload format). However, the datasource CAN include pre-computed target columns that make goal setup trivial in the UI.

**During data generation:**
- Add a constant target column for each metric that has a known threshold (e.g. `Attendance Target = 0.85`, `Dental Target = 0.90`)
- Include these columns in the `.hyper` file so they appear as fields in Pulse

**During company research:**
- Look for industry-standard thresholds, regulatory requirements, or internal goals mentioned in the call/brief
- Examples: federal 85% attendance (Head Start), 95% SLA uptime, 30-day close target, NPS > 40
- Store found thresholds in `METRIC_CONFIG` under a `goal` key:
  ```python
  METRIC_CONFIG = [
      {
          'label': 'Attendance Rate',
          'field': 'attendance_rate',
          ...
          'goal': {'value': 0.85, 'field': 'Attendance Target', 'name': 'Federal 85% Threshold', 'direction': 'above'},
      },
  ]
  ```

**In the walkthrough .docx and demo summary:**
- Include a "Setting Up Goal Lines" section with a table mapping each metric to its goal field
- Print clear instructions: open metric → Goals → select field from data → set direction
- This takes under 2 minutes in the UI and creates the visual goal line on sparklines

**Why this matters for the demo:**
- A goal line transforms a sparkline from "interesting" to "urgent" — the audience sees exactly when the metric crosses the threshold
- For compliance-driven organizations (Head Start, healthcare, finance), the threshold IS the story — being 2 points above it is not "fine," it's "dangerously close"

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
- Add calculated measurements (KPIs) and calculated dimensions (self-healing date shift)
- Create a `Display Date` calculated dimension using the **self-healing formula**:
  ```
  DATEADD("day", DATEDIFF("day", #<build_date>#, [DO_apiName].[date_field_apiName]), TODAY())
  ```
  where `<build_date>` is today's date in `YYYY-MM-DD` format (hash-delimited date literal). This shifts every row by the distance between the build date and the current query date — the most recent data always appears as "today" with no manual refresh needed. Use `#YYYY-MM-DD#` syntax for date literals (NOT `DATE(y, m, d)` which fails with "Arguments mismatch").
- Save to checkpoint: `display_date_api`, `date_field_api`, `build_date` (today's ISO date)
- Add semantic metrics with `timeDimensionReference: {"calculatedFieldApiName": "Display_Date"}` (not `tableFieldReference`) and `singularNoun` / `pluralNoun` filled in

**Phase 4c — Field descriptions (AI optimization)**

After the DO is created and field apiNames are known, PUT a `description` on every measurement and dimension. These descriptions are displayed in the Tableau Next UI and used by the Concierge AI to understand what each field means — without them, Concierge cannot answer questions accurately.

**Measurements** — include `description` in the same PUT already made for `aggregationType`. No extra round-trip needed:

```python
requests.put(
    f'{sf_instance}/services/data/v65.0/ssot/semantic/models/{sdm}/data-objects/{do}/measurements/{m_api}',
    headers=h,
    json={
        'apiName': m_api,
        'label': mc['label'],
        'dataObjectFieldName': m_field,
        'aggregationType': mc['agg'],
        'description': mc['description'],   # ← add this
    }
)
```

**Dimensions** — PUT each one after the measurement loop. Endpoint: `PUT /services/data/v65.0/ssot/semantic/models/{sdm}/data-objects/{do}/dimensions/{dim_api}`

Required body fields: `apiName`, `label`, `dataObjectFieldName`, `description`. Example loop:

```python
for field_name, dim_api in dim_field_map.items():
    desc = DIM_DESCRIPTIONS.get(field_name)
    if not desc:
        continue
    requests.put(
        f'{sf_instance}/services/data/v65.0/ssot/semantic/models/{sdm}/data-objects/{do}/dimensions/{dim_api}',
        headers=h,
        json={
            'apiName': dim_api,
            'label': dim_api.replace('_', ' ').title(),
            'dataObjectFieldName': dim_api + '__c',
            'description': desc,
        }
    )
```

**Where to define descriptions in the script:**

Add a `description` key to every `METRIC_CONFIG` entry:

```python
METRIC_CONFIG = [
    {
        'label':       'Benefits Enrollment Rate',
        'field':       'benefits_enrollment_rate',
        'agg':         'Average',
        'is_rate':     True,
        'description': 'Percentage of eligible employees actively enrolled in at least one core benefits plan. Primary KPI — a sustained decline signals client health risk.',
        'singular':    'benefits enrollment rate',
        'plural':      'benefits enrollment rates',
    },
    ...
]
```

Add a separate `DIM_DESCRIPTIONS` dict at the top of the script (near `METRIC_CONFIG`) with a description for every dimension the audience might filter by:

```python
DIM_DESCRIPTIONS = {
    'vertical':       'Industry vertical of the client (e.g. Technology, Life Sciences, Nonprofit). Use to identify which industries are experiencing the largest enrollment declines.',
    'region':         'US geographic region of the client headquarters. Use to spot regional patterns in enrollment trends.',
    'size_band':      'Employee count band of the client. Micro clients (3–25) tend to show the earliest and sharpest enrollment drops.',
    'state':          'US state of the client headquarters. Use for granular geographic filtering within a region.',
    'plan_cost_tier': 'Whether the client is enrolled in a Low, Mid, or High cost benefits plan tier. High-cost tier clients show the strongest signal — cost sensitivity drives voluntary plan drop-off first.',
    'workforce_type': 'Primary workforce composition of the client (Technical, Administrative, Sales, Mixed). Technical workforces tend to have higher voluntary plan adoption and show sharper drops when enrollment declines.',
    'date':           'Date of the benefits activity record. Use to analyze trends over time.',
    'client_id':      'Unique identifier for the TriNet client (employer). Use to drill into a specific client\'s enrollment history.',
}
```

Generate descriptions using company/use-case context from the research step — they should be written for the Concierge AI to read, so phrase them as instructions: *"Use this field to..."* or *"This metric represents..."*

**Phase 4b — Business preferences (Concierge language)**
After all metrics are created, PUT each metric back with natural-language nouns that Concierge uses to generate responses. Pattern: GET the metric, update `insightsSettings.singularNoun` / `pluralNoun` / `sentiment`, strip read-only fields, PUT back.
- Endpoint: `PUT /services/data/v66.0/ssot/semantic/models/{sdm}/metrics/{metric_api}?minorVersion=12`
- Strip these fields before PUT: `id`, `createdBy`, `createdDate`, `lastModifiedBy`, `lastModifiedDate`
- Good noun examples: `"deal closed"` / `"deals closed"`, `"in-person sales activity"` / `"in-person sales activities"`
- Sentiment: `"SentimentTypeUpIsGood"` or `"SentimentTypeUpIsBad"`

**Phase 5 — Visualizations + Dashboard (use template library)**

**Step 5a — Ask whether to build a dashboard:**

After SDM/metrics are complete, ask the user:

> "Your Semantic Data Model and metrics are ready — Concierge can already answer questions. Would you also like me to build a **Tableau Next dashboard** with visualizations? This adds chart widgets and a layout on top of the metrics. (yes / no)"

- If **no**: skip Phase 5 entirely (proceed to post-build). The SDM + metrics alone are enough for Concierge demos.
- If **yes**: continue to Step 5b.

**Step 5b — Present the visualization plan:**

```python
from viz_templates import recommend_dashboard_vizzes
from dashboard_builder import format_layout_preview

# Auto-recommend chart types from METRIC_CONFIG
viz_plan = recommend_dashboard_vizzes(METRIC_CONFIG, list(DIM_DESCRIPTIONS.keys()))

# Show ASCII preview
metric_labels = [mc['label'] for mc in METRIC_CONFIG[:3]]
viz_labels = [f"{v['label']} ({v['template'].replace('_', ' ').title()})" for v in viz_plan]
preview = format_layout_preview(metric_labels, viz_labels)
```

Print the preview and ask the user: **"Here's the dashboard I'll build — approve, edit, or skip?"**

- If **approve**: build as shown
- If **edit**: user can change chart types, swap metrics, add/remove vizzes
- If **skip**: skip viz/dashboard creation (proceed to post-build)

Once approved, build each visualization using the template library:

```python
from viz_builder import build_viz_payload

payload = build_viz_payload(
    template_name=rec["template"],       # e.g. "trend_over_time"
    viz_name=f"{slug}_{rec['metric_field']}",
    viz_label=rec["label"],
    sdm_api=sdm_api,
    ws_api=ws_api,
    do_api=do_api,
    field_map={"measure": rec["metric_field"], "date": "date"},
    dim_field_map=dim_field_map,
    measurements=measurements,
    style_overrides=BRAND,               # brand colors (if defined)
)
# Validation runs automatically — will print failures before POST
r = requests.post(f"{VIZ_API_BASE}/tableau/visualizations",
                  headers=SF_HDR, params=VIZ_PARAMS, json=payload)
```

Available templates: `trend_over_time`, `multi_series_line`, `bar_by_category`, `stacked_bar`, `horizontal_bar`, `donut`, `scatter`, `heatmap`, `funnel`

After all vizzes are created, assemble the dashboard:

```python
from dashboard_builder import build_dashboard_payload

dash_payload = build_dashboard_payload(
    dash_name=f"{slug}_dashboard",
    dash_label=f"{company} {use_case} Dashboard",
    ws_api=ws_api,
    sdm_api=sdm_api,
    metric_apis=list(metric_api_map.values()),
    viz_apis=list(viz_apis.values()),
    layout="auto",                       # or "standard", "story_flow", etc.
    style_overrides={"dashboard_bg": BRAND.get("dashboard_bg", "#F3F3F3")},
)
r = requests.post(f"{VIZ_API_BASE}/tableau/dashboards",
                  headers=SF_HDR, params=VIZ_PARAMS, json=dash_payload)
```

Layout patterns available: `standard` (3 metrics + 2×2 vizzes), `metrics_heavy` (6 metrics + 3 vizzes), `story_flow` (3 metrics + wide hero + 2-up), `wide_viz` (3 metrics + 2 full-width)

After dashboard creation, share the workspace with all users:

```python
# Share workspace with all org users
share_url = f"{sf_instance}/services/data/v66.0/tableau/records/{ws_api}/shares?minorVersion=12"
share_payload = {"shareWith": "ALL_USERS", "accessLevel": "View"}
r = requests.post(share_url, headers=SF_HDR, json=share_payload)
if r.status_code in (200, 201):
    print("  Workspace shared with all users.")
```

**Key rules still apply:**
- Dashboard page `name` must be a UUID string
- `widgets` must be a dict, not a list
- Widget `source` must have only `"name"` key (no type/label)
- Metric widgets need `parameters.metricOption.sdmApiName`
- Container widgets must be in `widgets_dict` with `type: "container"`

**Retry cleanup — apply to EVERY phase that creates assets:**

This pattern must be applied to the workspace/SDM phase (phase 4) and the viz/dashboard phase (phase 6). Track every asset created across all runs (including failed ones) in the checkpoint:

- `all_ws_apis` — workspace names created by this script
- `all_sdm_apis` — SDM apiNames created by this script
- `all_viz_apis` — viz apiNames created by this script
- `all_dash_apis` — dashboard apiNames created by this script

These lists are **never cleared when resetting a phase** — they accumulate across retries so a retry always knows what to clean up.

At the start of each phase (workspace/SDM or viz/dashboard), before creating anything new:
1. DELETE every entry in the relevant lists
2. Reset those lists to `[]` in the checkpoint
3. Clear derived checkpoint keys that depend on the deleted assets (e.g. `ws_api`, `sdm_api`, `do_api` when re-running phase 4)
4. Save the checkpoint
5. After each successful creation, immediately append the new name to the list and save checkpoint

This ensures only one complete, working set of assets survives each run.

**Asset ownership rule (critical):**
- Only ever delete assets whose names are in the checkpoint tracking lists — i.e. assets this script created
- Never delete assets created outside this script (manually, by another build, etc.)
- If a user asks you to delete assets during a session, confirm the asset name appears in the checkpoint before proceeding. If it doesn't, say: "I don't have a record of creating that asset — please confirm you want me to delete it before I proceed."

**Phase 6 — Post-build steps**
- Create a dedicated subfolder for this demo: `demos/{company_slug}_{use_case_slug}/`
- Write the demo guide markdown file there (`{slug}_guide.md`)
- Generate a Concierge walkthrough `.docx` file there using python-docx (`{slug}_demo_walkthrough.docx`)
  - The `.docx` must include a **"Business Preferences (SDM)"** section at the end containing the full business preferences text (see below) with copy-paste instructions pointing to: Data 360 → Semantic Model → [SDM name] → AI Optimization → Manage Business Preferences
- Generate business preferences text tailored to the company/use case and save it to the checkpoint as `"business_preferences"`. Structure as `#`-prefixed instruction lines covering:
  - What the data represents (company context, what entities are tracked)
  - Which metrics are leading vs. lagging indicators
  - Which dimensions are most diagnostic for root-cause analysis
  - Any terminology clarifications (e.g. what "at-risk" means in this org)
  - Default time comparison preference (e.g. last 6 months vs. prior 6 months)
  - Any metric hierarchy notes (which to prioritize when similar metrics exist)
- Print a final summary block with:
  - All created asset names (metric names, viz names, dashboard name)
  - Direct URL to the Tableau Next workspace/dashboard
  - Direct URL to Tableau Pulse
  - Absolute file paths to the guide and walkthrough (so the user can click them)
  - The full business preferences text (reprinted inline for easy access)
  - A clear callout: "Open the walkthrough .docx for the Business Preferences text to paste into your SDM"
  - A note about date freshness: "Tableau Next dates are self-healing (Display Date uses TODAY() at query time). For Pulse, run `/refresh-demo` before your meeting if the demo is more than a week old — it takes ~30 seconds to regenerate and re-publish fresh data."
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
- `use_dynamic_offset` is enabled — Pulse anchors to the most recent data point automatically
- **Coming back to this demo later?** Run `/refresh-demo` before your meeting if the demo is more than a week old. It regenerates data anchored to today and re-publishes in ~30 seconds. Your metrics, group, and subscriptions stay intact.

For Tableau Next:
- Visit your Tableau Next workspace
- Enable Analytics Agent Readiness: Data 360 → Semantic Model → Settings → Analytics Agent Readiness → toggle ON
- **Add Business Preferences to the SDM:** Data 360 → Semantic Model → [your SDM] → AI Optimization → Manage Business Preferences → paste the text from the "Business Preferences (SDM)" section of the walkthrough `.docx`
- The Concierge panel is now ready for Q&A demos
- Open the walkthrough `.docx` — it contains the exact Concierge prompts to use during the demo
- The Display Date dimension is **self-healing** — `TODAY()` evaluates at query time, data always appears current automatically

**Date freshness:**
- Tableau Next: fully self-healing, no action needed ever
- Pulse: run `/refresh-demo` before meetings if the demo is >1 week old (~30 seconds)

Note: the Tableau Next Concierge does not have a public REST API — it is UI-only. Automated testing of Concierge responses is not currently possible programmatically. Business Preferences are also UI-only — the build generates the text for you, but you must paste it in manually.

For CSV:
- Open the file in Tableau Desktop, Excel, or any viz tool
- Use it to build custom views or upload to another platform

---

## Cleanup

To remove a demo and all its assets, Claude can run cleanup steps on request. Specify the company name and timestamp to target a specific build.
