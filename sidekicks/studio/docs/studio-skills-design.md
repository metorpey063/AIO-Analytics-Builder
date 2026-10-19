# Design: AiO Tableau Agent Skills (v1)

## Overview

This document describes the design of three complementary Tableau Agent skills that showcase AiO story-driven demos inside Tableau Studio. The skills enable three distinct roles:

1. **`aio-story` (Builder — Guided)**: Guides a Solutions Engineer through building a four-question demo using natural language. "Walk me through the AiO story" → Claude asks questions and guides you through building each worksheet step-by-step.
2. **`aio-autobuilder` (Builder — Auto)**: One prompt ("build the demo") builds all four worksheets + the story dashboard on the connected datasource. The skill hands Tableau Agent declarative per-sheet specs; the agent builds them with its native authoring tools and verifies each one. Studio assets only — data, Pulse, and Next still come from `/build-demo`.
3. **`aio-audience` (Interpreter)**: Helps an audience understand and act on a story-driven dashboard during a demo. When the audience sees a worksheet, they ask "Why is this segment worst?" and the skill interprets the data narratively.

Together, these skills demonstrate Tableau Studio's natural-language authoring and agentic build capabilities, while providing multiple workflows for building and running AiO demos — from guided learning to rapid auto-build to audience engagement.

## Scope (v1)

### What's included

- **Three Tableau Agent skills**: `aio-story` (guided builder), `aio-autobuilder` (one-prompt builder), `aio-audience` (interpreter)
- **SKILL.md files** with frontmatter (Step 0 for demo-context detection), body, and supporting references
- **Reference documentation**: 
  - Builder guides: four-questions, signal-design, talk-track (aio-story); build-specs, verification (aio-autobuilder)
  - Interpreter guides: story-interpretation, talking-points (aio-audience)
- **Installation script** (`install_studio_skills.sh`) for standalone use
- **Demo-specific story injection**: During `/build-demo`, the demo's story metadata is assembled into a checkpoint dict and rendered as `demo-story.md`. All three skills check for this file (Step 0) and use demo-specific context if present.
- **Integration hook into `/build-demo`**: New output option `studio`; skill files written to demo-specific folder with `demo-story.md` pre-loaded

### What's deferred (future)

- Slack integration or close-loop automation.
- Semantics / Data 360 integration guidance (skills work with any datasource).
- Studio section in the walkthrough `.docx`.

## Design principles

### 1. Three roles, three skills

- **`aio-story`** is for guided builders (SEs learning by building). It's prescriptive and educational: "Here are the rules for Q1, Q2, Q3, Q4. Let's build each one together."
- **`aio-autobuilder`** is for rapid builders (SEs who need the demo fast). It's automated and orchestrated: "I'll build all four worksheets and the dashboard with my native tools, verify each, and tell you what I adjusted. You review and refine."
- **`aio-audience`** is for interpreters (audience members reading dashboards). It's narrative and context-aware: "Here's why this matters to you, here's what changed, here's what to do."

All three skills are demo-aware (they read `references/demo-story.md` if present) and datasource-agnostic (they work with any structured data).

### 2. Standalone + integrated

- **Standalone**: Anyone can download the `sidekicks/studio/skills/` folder, run the installer, and use the skills in their own Studio projects.
- **Integrated**: When `/build-demo` generates a demo with "Studio skills" as output, it copies the skills to `demos/{slug}/studio_skills/` and offers to install them. Users see a README with instructions and example prompts.

This dual delivery maximizes reach: SEs can share the skills with colleagues, and new demos automatically include them.

### 3. The four-question framework is the spine

All three skills anchor to the same narrative:

1. **Q1: "What is wrong?"** — Primary metric over time. Problem unmissable.
2. **Q2: "Where is it worst?"** — Metric by dimension, ranked. Culprit identified.
3. **Q3: "Why is it happening?"** — Supporting metrics + root cause. Explanation provided.
4. **Q4: "Who needs action?"** — Individuals/accounts in the culprit, ranked. Action enabled.

The builder skills *build* this (guided or automatic). The audience skill teaches how to *read* it. All reference the same pattern.

### 4. Lean and reference-rich

- **SKILL.md body**: < 150 lines. Only the essential steps, so the skill loads fast and the agent fires predictably.
- **References/**: Long docs (four-questions.md, signal-design.md, etc.) load only when the skill body points to them ("Read `references/four-questions.md`, then..."). The agent only opens these when needed, saving tokens.

This keeps the on-demand cost low while having deep docs available.

## Architecture

### File structure

```
sidekicks/studio/skills/
  aio-story/
    SKILL.md
    references/
      four-questions.md
      signal-design.md
      talk-track.md
  aio-autobuilder/
    SKILL.md
    references/
      build-specs.md
      verification.md
  aio-audience/
    SKILL.md
    references/
      story-interpretation.md
      talking-points.md
sidekicks/studio/install_studio_skills.sh
```

### Installation

**Standalone:**
```bash
bash sidekicks/studio/install_studio_skills.sh
```

**Integrated (in `/build-demo`):**
```
> Select output: "Studio skills"
> (Demo data generated)
> Install the skills? [Y/n]
> bash demos/{slug}/studio_skills/install.sh
```

### Trigger phrases

**Builder — Guided (`aio-story`):**
- "walk the AiO story"
- "build the next worksheet"
- "what should Q2 show"
- "create the dashboard"
- "help me build a story-driven demo"

**Builder — Auto (`aio-autobuilder`):**
- "build the demo"
- "auto-create Q1-Q4"
- "auto-build the story dashboard"
- "generate the four-question worksheet"

**Audience (`aio-audience`):**
- "explain this chart"
- "why is this segment worst"
- "what changed"
- "what should we do"
- "interpret this worksheet"

Each phrase fires the respective skill due to the `description` frontmatter in SKILL.md.

## How the guided builder skill works (`aio-story`)

1. **SE opens Studio** and connects a datasource.
2. **SE opens Tableau Agent** and types "walk the AiO story".
3. **The skill fires.** Claude reads the `aio-story/SKILL.md` body.
4. **Claude asks:** "What's your primary metric? Which dimensions matter?"
5. **SE answers:** Claude guides through Q1–Q4, asking for worksheet descriptions and creating them step-by-step.
6. **Result:** Four worksheets + dashboard following the story pattern (~30 minutes, hands-on learning).

The skill's body tells Claude the steps. The references provide context (four-questions.md explains *why*, signal-design.md explains *how to differentiate segments*, talk-track.md provides example phrasings).

## How the auto-builder skill works (`aio-autobuilder`)

1. **SE opens Studio** and connects a datasource.
2. **SE opens Tableau Agent** and types "build the demo".
3. **The skill fires.** Claude reads the `aio-autobuilder/SKILL.md` body and checks for `references/demo-story.md`.
4. **Claude confirms the story** (primary metric, culprit segment, counter-trend, root cause, supporting metrics).
5. **Preflight:** the agent maps every story field to a real datasource field and stops if anything is missing.
6. **The agent builds each sheet with its native tools**, per `build-specs.md`, and verifies it per `verification.md`:
   - Q1 worksheet (line chart, primary metric over time)
   - Q2 worksheet (bar chart, ranked by dimension, culprit highlighted)
   - Q3 worksheet (multi-line, supporting metrics)
   - Q4 worksheet (summary table, at-risk records)
   - Dashboard (2×2 layout with all four)
7. **Result:** Worksheets + dashboard saved, with a report of anything skipped or adjusted (hands-off).

The skill deliberately contains no XML or raw API calls — the Studio guide warns against the agent re-implementing native tools via scripts, and the document endpoint only checks well-formedness, so hand-written XML can "succeed" while producing broken sheets. Declarative specs + read-back verification are more robust.

## How the audience skill works (`aio-audience`)

1. **During the demo**, audience member sees a worksheet.
2. **Audience asks Tableau Agent:** "Explain this chart" or "Why is this segment worst?"
3. **The skill fires.** Claude reads `aio-audience/SKILL.md` body.
4. **Claude reads the visible worksheet** and answers the question as a knowledgeable guide.
5. **Result:** The audience hears the *story* (why it matters, what changed, what to do) instead of raw numbers.

The skill's references (story-interpretation.md, talking-points.md) teach Claude how to narrate each question and provide ready-to-use phrases.

## Integration with `/build-demo`

### Output option (new)

Add to `.claude/commands/build-demo.md` at line ~347 (Output mode section):

```
- Tableau Studio skills: Generate demo data + skill files. 
  Result: CSV data in demos/{slug}/, skills in demos/{slug}/studio_skills/.
  Use when: Building a demo to showcase natural-language authoring or to integrate with existing dashboards.
```

### Checkpoint keys

When "Studio skills" is selected, add to `{slug}_checkpoint.json`:

```json
{
  "studio_skills_generated": false,    // Set to true after skills written
  "studio_skills_installed": false     // Set to true after user runs installer
}
```

On rerun, check these keys and skip generation if already done.

### Output structure

```
demos/{slug}/
  {slug}_demo.py
  {slug}_checkpoint.json
  {slug}_{date}.csv
  studio_skills/
    aio-story/
      SKILL.md
      references/
    aio-audience/
      SKILL.md
      references/
    aio-autobuilder/
      SKILL.md
      references/
    install.sh
    README.md
```

### README.md (generated)

The `README.md` in `studio_skills/` should include:

```markdown
# AiO Tableau Agent Skills for {Company Demo}

## Quick start

1. Run: `bash install.sh`
2. In Tableau Agent, run: `/reload-skills`
3. Connect the demo CSV, then try: "build the demo", "walk the AiO story", or "explain this chart"

## Prompts for builders

- "Walk me through the AiO story"
- "Build question 1 (what is wrong?)"
- "Show me [metric] by [dimension]"
- "Create the dashboard"

## Prompts for audiences

- "Explain this worksheet"
- "Why is [segment] worst?"
- "What changed compared to last quarter?"
- "What should we do?"

## More information

See [studio-skills-design.md](../../docs/studio-skills-design.md) for the full design.
```

## Testing

### Manual testing (standalone)

1. Run `bash sidekicks/studio/install_studio_skills.sh` in Terminal.
2. In Tableau Studio, open Tableau Agent.
3. Run `/reload-skills`.
4. Verify `aio-story`, `aio-autobuilder`, and `aio-audience` appear in the skill list.
5. Test trigger phrases:
   - "walk the AiO story" → `aio-story` should fire.
   - "explain this chart" → `aio-audience` should fire.
   - "build the demo" (datasource connected) → `aio-autobuilder` fires; 4 sheets + dashboard built. Check `Tableau Agent/logs/ask-ledger.jsonl` for failed tools.
   - "rename this worksheet" → No AiO skill fires (default behavior).

### Integration testing

1. Run `/build-demo`, select "Studio skills" output.
2. Verify `demos/{slug}/studio_skills/` is created with all three skills, each with `references/demo-story.md`.
3. Verify README appears.
4. Run the installer from the demo folder.
5. Load all three skills and test.

### Negative tests

- Unrelated prompt ("What's the weather?") does not fire the skills.
- Skills work with different datasources (Pulse, published, Data Cloud).
- Rerun `/build-demo` on same slug; second run skips skill generation or offers to overwrite.

## Demo-specific story injection (v1, core feature)

When `/build-demo` generates a demo with `studio` output selected, it assembles the demo's story metadata into a structured dict (saved to checkpoint under `"story"`):

```json
{
  "story": {
    "company": "Paylocity",
    "primary_metric": "Relationship NPS",
    "dimensions": ["Team", "Region", "Plan Tier"],
    "culprit_segments": [{"name": "Garnishments", "dimension": "Team", "multiplier": 2.1}],
    "moderate_segments": [{"name": "Payroll Support", "multiplier": 1.0}],
    "counter_trend_segment": {"name": "HREdge", "multiplier": -0.08},
    "root_cause_dimension": "Plan Tier",
    "supporting_metrics": [{"name": "Case Resolution Time", "lag_ratio": 0.7}],
    "signal_onset_months_ago": 6,
    "signal_shape": "accelerating"
  }
}
```

This dict is then rendered into a human-readable `demo-story.md` file that is written to the `references/` folder of **all three** skills. When any skill is invoked in Tableau Studio, Step 0 of the SKILL.md checks for this file. If present, the skill uses the demo-specific metric/segment/dimension names; if absent, the skill operates generically (as with standalone installations).

**Result**: The same SKILL.md files work for both standalone (generic, ask the user) and integrated (demo-specific, use the `demo-story.md` context) scenarios without requiring separate skill definitions.

## Future enhancements

### Phase 2: Slack integration

When audience asks "Who should I call?", send a Slack message to the account owner with a summary.

### Phase 3: Semantics / Data 360 guidance

Document how skills work with Tableau Semantics models and give Concierge-compatible narrative patterns.

### Phase 4: Backfill existing demos

Retrofit existing demo scripts (e.g., `paylocity_voc_analytics_demo.py`) to extract and save their story metadata to checkpoint so that `/build-demo --resume paylocity` will generate the skills with the original story context.

## References

- `CLAUDE.md`: Signal design rules (segment multipliers, counter-trend)
- `AIO_CURRENT_PROCESS.md`: The four-question pattern
- `docs/MCP/tableau-studio-guide.md`: Skill format and loading (lines 725–853)
- `sidekicks/studio/docs/PLAYBOOK.md`: The v2 roadmap (section 4.1)
