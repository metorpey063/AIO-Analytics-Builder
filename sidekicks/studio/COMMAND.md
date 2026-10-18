# /studio — Generate the Tableau Studio Agent skills for a demo

Generates the three Tableau Studio Agent skills, pre-loaded with a demo's story, for any analytics demo need:

- **aio-story:** guided builder that walks the four-question narrative
- **aio-autobuilder:** one-prompt builder ("build the demo") that creates the Q1–Q4 worksheets and the story dashboard
- **aio-audience:** interpreter for presenters and viewers ("why did this move?")

**Generation only by default.** Installing into Tableau Studio is a separate, optional step (`--install`, or run the generated `install.sh` later). Studio skills need a Tableau Studio license but no Pulse or Tableau Next.

Works two ways:
- **From an existing demo:** reads the story from `demos/{slug}/{slug}_checkpoint.json` (written by `/build-demo` Phase 1).
- **Standalone:** no prior build needed. Asks the story questions, saves the story to the checkpoint, and generates from that. No data generation, no org connection.

This is a **sidekick**: it runs standalone, and `/build-demo` offers it in its **Optional add-ons** step (after close-loop, so the story can include the Close the Loop section). This file is the single source of truth for generation mechanics; `/build-demo` only points here.

## Usage

- `/studio {slug}`: generate for `demos/{slug}/`
- `/studio {slug} --new`: ignore any saved story and re-ask the story questions
- `/studio {slug} --install`: generate, then run the generated `install.sh`

If no slug is given, list the `demos/` folders and ask which one, or offer "new demo" (ask for company and use case, then derive `{company_slug}_{use_case_slug}`).

## Steps

### 1. Source the story
1. Load `demos/{slug}/{slug}_checkpoint.json` if it exists. If it has a `story` dict and `--new` wasn't passed, use it and show the user a one-screen summary to confirm.
2. Otherwise ask the story questions. Offer best guesses from the CSV header (if a CSV exists in the folder) so the user can just confirm:
   - Company, and a one-line **headline** (e.g. "Closed-won isn't billed")
   - **Primary metric** and 0–3 **supporting metrics** (with lag ratio vs. primary, default 0.7)
   - **Dimensions** available for drilling
   - **Culprit segment(s)** (name, dimension, multiplier), **moderate segments**, and the **counter-trend segment**
   - **Root-cause dimension** (the one that explains cost or effort)
   - **Entity field** (finest-grain name column for the Q4 at-risk list) and **date field**
   - **Aggregation** per metric: rates, scores and averages → AVG; counts, revenue and volumes → SUM
   - **Datasource** to connect in Studio (CSV path or published datasource name)
   - Signal onset (months ago) and shape (`accelerating` / `ramp` / `step`); default 3 and `accelerating` if unknown
3. Build the `story` dict and save it, merging into the checkpoint (never overwrite other phases):

```python
story = {
    "company": COMPANY,
    "primary_metric": ...,
    "dimensions": [...],
    "culprit_segments": [{"name": ..., "dimension": ..., "multiplier": 1.8}],
    "moderate_segments": [{"name": ..., "multiplier": 1.0}],
    "counter_trend_segment": {"name": ..., "multiplier": -0.08},
    "root_cause_dimension": ...,
    "supporting_metrics": [{"name": ..., "lag_ratio": 0.7}],
    "signal_onset_months_ago": 3,
    "signal_shape": "accelerating",
    "entity_field": ...,
    "date_field": "Date",
    "aggregations": {"Metric Label": "AVG"},
    "headline": ...,
    "datasource": f"demos/{slug}/{csv_filename}",
}
save_cp(cp, "story", story)
```

If the folder or checkpoint doesn't exist yet, create `demos/{slug}/` and a minimal `{slug}_checkpoint.json`.

### 2. Render `demo-story.md`
Render the story into markdown with these sections, in order: Primary Metric, The Problem, Culprit Segment(s), Moderate Segments, Counter-Trend Segment, Root Cause Dimension, Supporting Metrics (Leading Indicators), Dimensions for Drilling, **Build Fields (used by aio-autobuilder)**.

Build Fields lists: Headline, Date field, Segment dimension (Q2) = `culprit_segments[0].dimension`, Entity field (Q4), Aggregations, Datasource to connect.

If `demos/{slug}/{slug}_close_loop_payload.json` exists (close-loop already built), append a **Close the Loop** section so `aio-audience` can point the presenter at it: the action and its reason, the trigger label, and each `demo_steps` entry as `- {title}: "{say}" — {trigger} → {result}`.

### 3. Create the skill folders
Copy from `sidekicks/studio/skills/` (`SKILL.md` plus everything in `references/`), then add the rendered `demo-story.md` to each skill's `references/`:

```
demos/{slug}/studio_skills/
  aio-story/        SKILL.md, references/{...copied, demo-story.md}
  aio-audience/     SKILL.md, references/{...copied, demo-story.md}
  aio-autobuilder/  SKILL.md, references/{...copied, demo-story.md}
  install.sh
  README.md
```

Each skill's Step 0 checks for `references/demo-story.md` and falls back to asking the user if it's absent, so the generic skills in `sidekicks/studio/skills/` still work without a demo.

### 4. Generate `install.sh`
Same as `sidekicks/studio/install_studio_skills.sh`, but copies from the demo-specific folder (`SCRIPT_DIR`) so the installed skills carry this demo's story. Target: `$HOME/Documents/My Tableau Repository (Beta)/Tableau Agent/skills`. For each of the three skills: `rm -rf` the target, `cp -r`, echo `✓ Installed {skill} ({COMPANY} story)`. End with "In Tableau Agent, type: /reload-skills". Fail with the same prerequisite message (Studio installed, opened once, Tableau Agent opened) if the target directory is missing. `chmod +x` it.

### 5. Generate `README.md`
Quick start (`bash install.sh`, `/reload-skills`, connect the datasource, example prompts), then three sections of example prompts using the story's names:
- **One-prompt build (aio-autobuilder):** "build the demo"
- **Guided build (aio-story):** "Walk me through the AiO story for {COMPANY}", Q1–Q4 prompts, "Create the dashboard with all four questions"
- **For audiences (aio-audience):** "Explain this {PRIMARY_METRIC} trend", "Why is {culprit} down so much?", "Which {culprit} accounts are most at risk?", "What should we do about this?"

Finish with a pointer to `references/demo-story.md`, `sidekicks/studio/docs/studio-skills-design.md`, and the generic skills in `sidekicks/studio/skills/`.

### 6. Update the checkpoint
```python
save_cp(cp, "studio_skills_generated", True)
save_cp(cp, "studio_skills_installed", False)  # True only if --install ran
```

### 7. Install (only with `--install`, or if the user asks)
Run `bash demos/{slug}/studio_skills/install.sh`, set `studio_skills_installed` to True, and remind the user to type `/reload-skills` in Tableau Agent.

### 8. Report
> **Tableau Studio Skills:** `demos/{slug}/studio_skills/`: three natural-language skills pre-loaded with this demo's story (culprit: {culprit}, counter-trend: {counter_trend}, root cause: {root_cause_dimension}). Install: `bash demos/{slug}/studio_skills/install.sh`, then `/reload-skills` in Tableau Agent.

Also tell the user to connect the datasource in Studio before using "build the demo".

## Re-running
Safe to re-run. It regenerates `demo-story.md`, the skill folders and the scripts. Re-run after `/close-loop {slug}` builds so `aio-audience` picks up the Close the Loop section.

## Troubleshooting
Follow the CLAUDE.md order: Known Pitfalls first. Studio skills are plain markdown plus a shell script, so most problems are a missing skills directory (open Tableau Studio and Tableau Agent once) or a skill not showing up (run `/reload-skills`).
