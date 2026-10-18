# AiO 2.0 — "So You Think Your Data Can AI?" assessment

Date: 2026-10-13 · Video due: **Oct 21, 11:59pm PT (8 days)** · Top 10 announced: Oct 23 · Live finals: Oct 27

Sources: `AIO_CURRENT_PROCESS.md`, `CLAUDE.md`, `MCP_BUILD_GUIDE.md`, `CHANGELOG.md`, `.claude/commands/*`, `demos/*`, the competition brief, the Tableau Next and Cloud MCP references, and `scrapedpuppetmode/` (Tableau Studio guide and the External Client API reference).

---

## Part 1 — Critique: AiO v1 as a submission today

### Scorecard (my estimate of how judges would score it)

| Criterion | Weight | v1 score | Why |
|---|---|---|---|
| Tableau Depth | 25% | **3.5** | Covers a lot: Pulse, Tableau Next, Data 360 (stream, DLO, SDM, metrics) and CRMA. But each product is a **parallel output** of the same CSV. Nothing shows the products working *together*, and the rubric's "5" is integrated value, not product count. |
| Impact | 25% | **3.5** | The pain is real and the judges (SE managers) feel it themselves. But I found no evidence in the folder of how many SEs use it, demos built, hours saved, or deals touched. Without numbers, "saves time" is a claim. |
| Build Quality | 20% | **3.5** | Real end-to-end builds with checkpointing and cleanup, and five demos in `demos/`. Against that: the data is synthetic (the rubric says "real data"), six steps are still manual, Next chart axes go stale, and the Paylocity Next build hit the trial-org Bulk Ingest wall and needed a manual CSV upload. |
| Innovation | 15% | **3.0** | "Claude builds demo assets" is common by Oct 2026, so judges will have seen variations. The signal-engineering design (culprit segments, 2D compound drills, counter-trend, lagging indicators) is the original part, but that's hard to see in a video. |
| The Pitch | 15% | **3.0** (unknown) | A demo of a demo-builder is meta. Builds take 10+ minutes. Unless it's time-lapsed and tied to an outcome, five minutes goes to watching progress bars. |
| Bonus (D360 + other SF products + AI) | +1 pt | **+0.5** | Claude Code and D360 are there. MCP is an optional pilot path rather than the default. No Slack, Agentforce or CRM workflow. |

**Weighted: about 3.35 / 5, plus about 0.5 bonus → about 3.85.** That's likely a Top 10 contender ($1k), but not a Top 3 winner as it stands.

### What's strong (keep it, and lead with it)

- **It solves a real, recurring problem that scales.** Every Tableau SE builds custom demos, so the tool's market is the whole judging population's teams.
- **The story engine is the moat.** The four-question arc, culprit plus counter-trend segments, and lagging supporting metrics turn "a chart" into "a decision". That directly answers the brief's warning: *"A dashboard alone won't win. Show what decision it changes, and for whom."*
- **It's hardened.** Checkpoint/resume, retry cleanup, canary validation, about 60 documented pitfalls, and self-healing dates. That's real build-quality evidence. Mention it in one line, not five.
- **There's already an MCP path** (`MCP_BUILD_GUIDE.md`) that removes most manual steps.

### What will cost points

1. **Authorship (fix this first).** All 103 commits in the repo are by **Matthew Torpey**. If you submit AiO, make Matthew a teammate (teams can be up to 3), or make the v2 work clearly and demonstrably yours. Judges and finals audiences will know whose tool it is.
2. **"Parallel outputs" reads as breadth, not depth.** Pulse, Next and CRMA never reference each other or a shared semantic layer.
3. **Synthetic data versus "works on real data."** This needs a deliberate answer: the platform work is real and live on a real org, and the data is synthetic by design because pre-sale customer data isn't available. Better still, add one real-data path (see R6).
4. **Visible seams.** Pasting business preferences, goal lines, percent format, chart dates that age, and trial-org ingest failures all undercut "works end to end".
5. **CRMA dilutes the story.** It's the legacy stack and adds nothing to the D360 narrative. Leave it out of the video.
6. **No closed loop.** The demo ends at the insight. Nothing triggers an action (alert, Slack, agent), and that's where the bonus multiplier lives.

---

## Part 2 — How your instincts fit the rubric

| Your idea | Scoring lift | Verdict |
|---|---|---|
| **Use the Tableau Studio MCP (puppet mode)** | High on Innovation, Depth and Pitch | **Yes, make it a centerpiece.** It's new (2026.3), it's visual (Studio building itself on camera is the "wow" moment), and the brief specifically suggests *"connect to D360 (Tableau Semantics) from Tab Core"*. Studio is how you do that. |
| **More talk tracks for Metrics** | Low on its own | **Fold it in; don't headline it.** Judges score outcomes, not walkthrough content. Reframe it as a "metric layer as backbone" story: metrics defined once in Tableau Semantics, used by Next, Concierge, Studio and Slack, with talk tracks **checked against the data** before the SE sees them. That reframe lifts Depth and Innovation. |
| **"AiO 2.0" framing** | Neutral to positive | Good, as long as v2 is clearly a new capability and not a refactor. |

---

## Part 3 — Recommendations, in priority order

### R1 — Reframe the pitch: "From opportunity to a decision-ready demo, on one semantic layer"

- **Track:** submit as **Customer Zero** (Tableau + D360 running our own business: SE productivity and pipeline), and show the output going in front of a customer tomorrow. That covers both tracks.
- **Who decides what:** the SE decides which story to run. The customer persona (for example a VP of Benefits Ops) decides where to act: the culprit segment.
- **The headline number:** hours to build a tailored demo before AiO versus after. Measure it, don't estimate it.

### R2 — One semantic layer, every surface (biggest Depth gain)

Make the **Tableau Semantics SDM the single source of truth**, and have every output read from it rather than from the CSV:

```
Opportunity (org62) → story design → D360 (stream → DLO → SDM + metrics + business prefs)
        ├─ Tableau Next dashboard + Concierge (analyze_data)
        ├─ Tableau Studio workbook connected to the SDM  ← Tab Core on D360
        ├─ Tableau Next alert on the culprit segment → Slack
        └─ Walkthrough with talk tracks checked against the data
```

- **Verify first (day 1):** that Tableau Studio can connect to a Tableau Semantics / Data 360 model on your org. The Studio docs don't cover connectors. If it can't, fall back to Studio on the Pulse published datasource, and say so in the pitch.
- Keep Pulse as the installed-base option, but don't let it split the story.

### R3 — Tableau Studio "puppet mode" (Innovation and visual pitch)

Replace the 39 KB of reverse-engineered XML in `twb_builder.py` with live Studio authoring through the External Client API or the Studio MCP:

| Step | Studio API operation | Why it scores |
|---|---|---|
| Open or attach the data | `POST openFile` (.tds / .twb) | Starts the live, visible build |
| Build charts | `showMeWorksheet` (26 types, including `dual-bar-line`, `bullet`, `heat`, `filled-maps`) | Native charts with no hand-written XML |
| Assemble | `applyWorkbookDocument` after `validateWorkbookDocument` (XSD) | Validation replaces guesswork, so build quality goes up |
| **Self-QA by looking** | `exportDashboardImage` / `exportWorksheetImage` → Claude reviews the PNG and fixes layout | "The agent checks its own work": an innovation point you can show on camera |
| **Self-QA on the data** | `getWorksheetSummaryData` → confirm the culprit segment really is the worst | Proves the story the SE will tell is true |
| Publish | Keep TSC REST publish | `publish` via the Studio API opens an interactive dialog, so it isn't fully headless |

Also **ship AiO's story rules as a Tableau Agent skill** (`~/Documents/My Tableau Repository (Beta)/Tableau Agent/skills/aio-story-dashboard/SKILL.md`). Any SE in Studio can then type `/aio-story-dashboard`. That's your "scales to the masses" line.

**Risks to state honestly:**

- Driving Studio from an external agent is **internal beta only** and needs an internal Studio build (`feature/desktop` branch of tableau-mcp).
- The Studio API is version `0.2.x`.
- Record the Studio segment early, and keep a pre-recorded fallback.

### R4 — Make the Tableau Next MCP the default path (Build Quality)

- Moving to the MCP upload flow (`generate_presigned_credential` → `create_data_stream` → `run_data_stream`) **avoids the Bulk Ingest entitlement wall** that blocked Paylocity.
- `update_semantic_model(businessPreferences=…)` and `add_global_filter_to_dashboard` remove two manual steps.
- Point at the **open Beta server** (self-enroll in Setup → MCP Servers) rather than the pilot permission, so other SEs can actually use it.
- Run `analyze_data` on every walkthrough question, and **compare each answer's direction with the real trend** in the source data (you already have this rule for Pulse Brief). Show this on camera with something like: "AiO dropped one AI answer because it contradicted the data." That's an uncommon, strong trust moment.

### R5 — Close the loop with an action (Bonus multiplier)

- `create_alert` on the culprit metric and segment, delivered to **Slack**.
- Tag the Pulse datasource **`MCP Enabled`** (required since Aug 31), and write descriptions plus up to 10 sample questions into it, so **Slackbot with Tableau MCP** can answer the demo questions right away.
- Optional: ask the same question in Slackbot and in Concierge to show "same governed answer everywhere."

### R6 — Start from the opportunity, and measure the impact (Impact plus Customer Zero)

- **Input:** an org62 Opportunity. Use the connected `salesforce-for-sales` skills (`account-context`, `call-prep`) to pull industry, persona and the call notes or transcript into `/build-demo`. That's Salesforce CRM depth and it removes a third of the questions.
- **Output:** log a note or activity back on the opp ("AiO demo built: link, walkthrough").
- **Proof:** a small **AiO usage model in D360 / Tableau Next**: builds, SEs, minutes per build, opps influenced. Use **real** session data only, even if it's small (for example 12 SEs and 40 builds). One honest small number beats a big projected one. If you can't collect it in time, run a quick SE survey and quote two or three SEs by name, with their permission.

### R7 — Cut scope for the video

- Out of the video: CRMA, `/transfer-assets`, `/validate-pulse`, `/update`. Give them one "hardened for the field" line.
- Pulse: one beat at most.

---

## Part 4 — Projected score after changes

| Criterion | v1 | v2 (R1–R5) | v2 (+R6) |
|---|---|---|---|
| Tableau Depth (25%) | 3.5 | 4.5 | 4.5 |
| Impact (25%) | 3.5 | 4.0 | 4.5 |
| Build Quality (20%) | 3.5 | 4.5 | 4.5 |
| Innovation (15%) | 3.0 | 4.0 | 4.5 |
| Pitch (15%) | 3.0 | 4.0 | 4.5 |
| **Weighted** | **3.35** | **4.23** | **4.50** |
| Bonus | +0.5 | +0.8 | +1.0 |
| **Total** | **~3.85** | **~5.0** | **~5.5** |

The tiebreaker is Tab plus other-product depth, which R5 and R6 address directly.

---

## Part 5 — 8-day plan

| Day | Date | Work |
|---|---|---|
| 1 | Tue 10/13 | Settle the team and authorship with Matthew. Confirm a real SDO/CDO (not a trial org). Spike: Studio → Tableau Semantics connection. Enroll in the Next MCP Beta. |
| 2 | Wed 10/14 | Switch the Next path to MCP by default, run one clean end-to-end build, and time it. Start collecting usage and impact data. |
| 3–4 | Thu–Fri | Studio puppet-mode phase: openFile → showMe → apply/validate → image self-QA → summary-data check. Draft the Studio skill. |
| 5 | Mon 10/19 | Alert → Slack. MCP Enabled tag plus sample questions. Opportunity-in and note-back on org62. Data-direction check on Concierge answers. |
| 6 | Tue 10/20 | Full dress-rehearsal build on a fresh customer story, recorded. Impact slide with real numbers. |
| 7 | Wed 10/21 | Edit the video (≤ 5:00), captions, submit before 11:59pm PT. Keep a buffer. |
| Finals | Tue 10/27 | Same arc live, with a pre-recorded fallback for any step longer than 20 seconds. |

---

## Part 6 — 5-minute video outline

| Time | Beat | On screen |
|---|---|---|
| 0:00–0:30 | **Problem** | "Tailored demos take an SE about X hours, so most of us show generic ones, and generic demos don't move deals." Real number. |
| 0:30–0:50 | **Input** | An org62 opportunity, then "Build a demo for this opp." |
| 0:50–2:30 | **Build** (time-lapse with an on-screen clock) | D360 stream → SDM + metrics → Next dashboard → **Studio building the workbook live** → the agent reviews its own screenshot and fixes a chart. |
| 2:30–3:40 | **Customer moment** | The four-question drill in Concierge: overall down → segment → compound segment → root cause → counter-trend. Then "AiO dropped one AI answer because it contradicted the data." |
| 3:40–4:10 | **Action** | Alert fires in Slack, and Slackbot answers the same question from the same governed metric. |
| 4:10–4:45 | **Result and scale** | Hours to minutes, SEs using it, opps touched. "Any SE, in Claude Code or as a skill in Tableau Studio." |
| 4:45–5:00 | **Close** | "One story, one semantic layer, every surface." |

Keep the confidential pre-release Studio doc pages off screen, since the video will be shared widely.
