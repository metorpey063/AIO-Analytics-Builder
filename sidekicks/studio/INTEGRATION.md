> **Status (2026-10-18): merged.** Engine `studio_skills.py`, command `.claude/commands/studio.md`, `/build-demo` offer after close-loop, `cp["story"]` saved in Phase 1, walkthrough Section 8, CLAUDE.md entries. The templates stay in `sidekicks/studio/skills/`. Still open: checklist item 7 (whether the Studio guide and external API reference may be shared upstream).

# Integrating studio into core

## What it does, and why it belongs in core

`/studio` generates three Tableau Studio Agent skills (aio-story, aio-autobuilder, aio-audience) pre-loaded with a demo's story. The story is the culprit, counter-trend, root cause, and drill path, plus the Close the Loop step if it's built. An SE can then type "build the demo" in Tableau Studio, and a presenter can ask "why did this move?" and get answers grounded in the engineered signal. AiO already designs every demo around that four-question story, and this sends the story to a third authoring surface alongside Pulse and Next.

## Today (as a sidekick): no core file depends on it

| Piece | Where it lives now |
|---|---|
| Generic skills | `sidekicks/studio/skills/` (was `tableau_agent_skills/`) |
| Installer | `sidekicks/studio/install_studio_skills.sh` (was `scripts/`) |
| Command | `sidekicks/studio/COMMAND.md` ← launcher `.claude/commands/studio.md` |
| Docs | `sidekicks/studio/docs/` (was `docs/v2/`, `docs/MCP/tableau-studio-guide.md`, `docs/MCP/tableau-external-client-api-reference.md`, root `AIO_v2_*.md`) |
| `/build-demo` hook | "Optional add-ons" step (intake ~line 421, run ~line 1483, summary ~line 1536) |

It touches no Python, credentials, or config.

## Core files that would change on a full merge

| File | Hook point | Change |
|---|---|---|
| `tableau_agent_skills/`, `scripts/install_studio_skills.sh` | repo root | Optional move back. If moved, set `SKILLS_SOURCE="$REPO_ROOT/tableau_agent_skills"` in the installer and update paths in `COMMAND.md` + `docs/studio-skills-design.md`. |
| `.claude/commands/studio.md` | whole file | Replace the launcher with `COMMAND.md` |
| `.claude/commands/build-demo.md` | "Optional add-ons" (~421 / ~1483 / ~1536) | Repoint to `.claude/commands/studio.md`. Keep the order close-loop → studio. |
| `.claude/commands/build-demo.md` | Pulse/Next Phase 1 (data generation, writes the checkpoint) | Optional: save the `story` dict to the checkpoint on every build, so `/studio` works later with no questions. Today the add-on step writes it only when Studio is chosen. |
| `CLAUDE.md` | "What this does" (~line 102) and "Project structure" (~line 110) | `/studio` line, plus the `tableau_agent_skills/` entry with install and design-doc pointers |

## Patches

- `studio.patch`: the feature as it was on `backup/integrated-features` (diff `2b0b380..backup/integrated-features`: `studio.md`, `tableau_agent_skills/`, `scripts/install_studio_skills.sh`, `docs/v2/`). It applies cleanly to `2b0b380`.
- `../shared-docs.patch`: the original `build-demo.md` + `CLAUDE.md` edits for both features (the Studio parts were 5a/5b and "For Tableau Studio skills output"). They conflict with upstream; use them for wording only.

## New dependencies, config, env vars

None. No Python packages, scopes, config keys, or env vars. Using the output needs Tableau Studio, opened once with Tableau Agent opened once, so `~/Documents/My Tableau Repository (Beta)/Tableau Agent/skills` exists.

## What broke last time (see `docs/sidekick-refactor/01-breakage-audit.md`) and how to avoid it

1. **`/build-demo` intake rewritten** (#4). Studio took 5a/5b, which pushed Dashboard/Brand to 5d/5e and removed `all`. → One "Optional add-ons" question at the end; never take a 5x letter.
2. **Label collisions with upstream** (#13). Upstream added 5c CRM actionability and Phase 4a–4c. → No lettered steps for add-ons.
3. **Duplicate docs** (`docs/MCP/tableau-studio-guide.md` and `docs/v2/private/tableau-studio-guide.md` were identical, 1211 lines each, and the "private" copy was committed). → One copy, in `sidekicks/studio/docs/`. Check whether the guide may be committed at all before merging upstream.
4. **Order dependency with close-loop.** Run studio *after* close-loop, or re-run `/studio` later, so `aio-audience` gets the Close the Loop section.

## Integration checklist

1. [ ] Branch from current `upstream/main`.
2. [ ] Decide: keep `sidekicks/studio/` or move back to `tableau_agent_skills/` + `scripts/`.
3. [ ] If moving: `git mv`, fix `SKILLS_SOURCE`, then `rg -n "sidekicks/studio"` and update every hit.
4. [ ] Move `COMMAND.md` → `.claude/commands/studio.md`.
5. [ ] Update `build-demo.md` "Optional add-ons" paths; optionally save `story` in Phase 1.
6. [ ] Add the `CLAUDE.md` "What this does" and "Project structure" lines.
7. [ ] Confirm the Studio guide / external API reference are OK to share with the coworker's repo.
8. [ ] Run the tests below.

## Tests

**Core still works:** same five checks as in `../close-loop/INTEGRATION.md` § Tests ("Core still works"). Studio touches no Python, so the risk is only in `build-demo.md` wording: confirm a CSV-only build with no add-ons asks exactly the upstream questions.

**Studio works:**
1. `/studio waste_connections_route_ops` (or any demo with a checkpoint) writes `demos/{slug}/studio_skills/{aio-story,aio-autobuilder,aio-audience}/references/demo-story.md`, `install.sh`, and `README.md`, and sets `studio_skills_generated: true` in the checkpoint.
2. If the close-loop payload exists, `demo-story.md` has a "Close the Loop" section.
3. `/studio newco_test --new` with no folder asks the story questions and creates the folder and checkpoint.
4. `bash sidekicks/studio/install_studio_skills.sh`: without Studio, it prints the prerequisite message and exits 1; with Studio, it installs the three skills and `/reload-skills` lists them.
5. `/build-demo` choosing the Studio add-on runs it after close-loop (if chosen), and the summary shows the add-on row.
