# /studio — Tableau Studio Agent skills for a demo

Generates **Tableau Studio Agent skills** that already know a demo's story, so the SE or the audience can build and explain the demo in natural language inside Tableau Studio:

- **aio-story:** guided builder that walks the four-question narrative (What's wrong → Where → Why → Who)
- **aio-autobuilder:** one prompt ("build the demo") creates the Q1–Q4 worksheets and the story dashboard
- **aio-audience:** interpreter for presenters and viewers ("why did this move?", "what should we do?")
- **Custom skills:** Claude can write new Studio skills for the demo on request (e.g. "a skill that explains billing lag by region")

It runs standalone on demo content the SE already has, and `/build-demo` offers it as an optional add-on after close-loop. It needs no Salesforce org and no Pulse or Tableau Next. Tableau Studio is needed only to install and use the skills.

All logic lives in `studio_skills.py`: story derivation, source import, rendering, custom-skill validation, install, and walkthrough Section 8. The templates live in `sidekicks/studio/skills/`. This command only orchestrates. Never hand-write `demo-story.md`, `install.sh`, or the walkthrough section.

## Usage

- `/studio {slug}`: confirm the story, then generate `demos/{slug}/studio_skills/`
- `/studio {slug} --new`: re-derive the story from the data, ignoring the saved one
- `/studio {slug} --csv PATH` | `--hyper PATH` (a `.hyper` or a `.tdsx` with an extract) | `--datasource "Name"`: bring outside demo content in first
- `/studio {slug} --custom "what the skill should do"`: write a custom skill (Step 3)
- `/studio {slug} --install`: generate, then install into Tableau Studio

If no slug is given, list the `demos/` folders and ask which one, or offer "something from outside AIO". In that case, ask for the CSV, `.hyper`/`.tdsx`, or published datasource name, plus a company and use case, and derive `{company_slug}_{use_case_slug}`.

## Steps

### 1. Source and story
1. **Bring in the content (outside sources only):**
   - **CSV:** `python studio_skills.py story --slug {slug} --csv PATH`
   - **`.hyper` / `.tdsx`:** `--hyper PATH`. A self-healing `.tdsx` has no stored Date; the tool rebuilds it from `Day_Offset`.
   - **Published datasource:** `--datasource "Name" [--profile K]`. It uses the Tableau PAT from `/setup`, downloads the extract, and records the name so `aio-autobuilder` connects to the published source.
   - Each creates `demos/{slug}/` and a minimal checkpoint.
2. **AIO demo folder:** `python studio_skills.py story --slug {slug}` (add `--new` to re-derive).
3. **How the story is derived:** the tool computes it from the data with the same analysis as `/close-loop`, so both tell the same story: culprit, deepest drill, counter-trend, root-cause dimension, supporting metrics, at-risk entities, and segment multipliers from the observed changes.
   - Saved `story` keys win over derived ones.
   - For a demo built by AIO, `METRIC_CONFIG` in `{slug}_demo.py` supplies the metric labels, aggregations and sentiment.
4. **Confirm with the user:** show the one-screen summary the command prints, and ask if it reads right. Fix anything that's off with `--set` and re-run, e.g.:
   - `--set primary_metric="Revenue Realization Rate"`
   - `--set 'supporting_metrics=["Active Location Rate"]'`
   - `--set entity_field="Account Name"`
   - `--set company=Lessen`
   - `--set headline="Closed-won isn't billed"`

   **For outside data with no `METRIC_CONFIG`, always confirm the primary metric and the entity field.** The fallback picks the first numeric column, which is often a count or an ID. If the analysis picks a dimension that just tracks the intended one, pin the drill path with `--set 'dimensions=[...]'` (see the CLAUDE.md pitfall about pinning `cp["story"]`).

### 2. Generate
Run `python studio_skills.py generate --slug {slug}`. It:
- renders `demo-story.md` into each skill's `references/`. This includes Build Fields for autobuilder, the at-risk list, and a **Close the Loop** section if `{slug}_close_loop_payload.json` exists;
- copies the three templates and keeps any custom skills;
- writes `install.sh` and `README.md`;
- sets `studio_skills_generated` in the checkpoint;
- writes walkthrough **Section 8 "Tableau Studio Skills"** into the `.docx`, if there is one.

It's safe to re-run.

### 3. Custom skills (optional — offer once)
> "Want a custom Studio skill for this demo? For example, one that explains a specific drill, coaches the presenter, or builds an extra view."

If they say yes, or passed `--custom`:
1. Agree on a kebab-case name and what the skill does. It must not clash with `aio-*` or a standard Studio skill; the tool rejects clashes.
2. Write `SKILL.md` to a temp file, following the Studio skill format:
   - **Frontmatter:** `name` (must match the folder) and `description`. Say what the skill does, and list 2–4 quoted trigger prompts; these become the README and walkthrough examples.
   - **Step 0:** read `references/demo-story.md` and use its story; ask the user if it's missing. Copy this pattern from the templates.
   - **Fields:** use only fields that exist in the datasource. Run `python studio_skills.py story --slug {slug}` to see the CSV path, and check its header. Wrap field and segment names in backticks; the tool warns about any it can't find.
   - **Building:** if the skill builds anything, use the `aio-autobuilder` ground rules. Use native authoring tools (no Python or raw API calls), verify every sheet, and don't stop mid-build.
   - **Style references:** `sidekicks/studio/skills/*/SKILL.md` and "Customize Skills" in `sidekicks/studio/docs/tableau-studio-guide.md`.
3. Run `python studio_skills.py custom --slug {slug} --name {name} --spec /tmp/{name}.md [--refs DIR]`.
4. Fix any ⚠ warnings (unknown fields, no `demo-story.md` reference) and re-run.

The skill is added to `studio_skills/`, `install.sh`, the README, Section 8, and `cp.studio_custom_skills`.

### 4. Install (only with `--install`, or if the user asks)
Run `python studio_skills.py install --slug {slug}` and remind the user to type `/reload-skills` in Tableau Agent. If it fails because the skills directory is missing, Studio hasn't been set up yet: open Tableau Studio once, then Tableau Agent (Extensions menu), then retry. `python studio_skills.py status --slug {slug}` shows what's generated and installed.

### 5. Report
> **Tableau Studio Skills:** `demos/{slug}/studio_skills/` — {N} skills pre-loaded with this demo's story (culprit: {culprit}, counter-trend: {counter_trend}, root cause: {root_cause_dimension}). Install: `bash demos/{slug}/studio_skills/install.sh`, then `/reload-skills` in Tableau Agent. Connect **{datasource}** in Studio, then try "build the demo".

## Re-running
- Re-run `/studio {slug}` after `/close-loop {slug}` builds, so `aio-audience` and the custom skills pick up the Close the Loop section.
- Re-run after the data changes; the evidence is always recomputed.
- Re-run `install` after regenerating; installed copies don't update themselves.

## Troubleshooting
Follow the CLAUDE.md order: Known Pitfalls first. Studio skills are plain markdown plus a shell script.
- **Skill not listed in Studio:** run `/reload-skills`.
- **"Skills directory not found":** open Tableau Studio and Tableau Agent once.
- **"build the demo" can't map a field:** the datasource connected in Studio isn't the one in Build Fields.
- **"Could not find a Date column":** the source has no date. Pass `--set date_field=...` if the column has another name.
