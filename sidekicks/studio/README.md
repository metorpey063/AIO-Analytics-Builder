# Studio sidekick

Generates three **Tableau Studio Agent skills**, pre-loaded with a demo's story, so the SE or the audience can build and explain the demo in natural language inside Tableau Studio:

- **aio-story**: guided builder that walks the four-question narrative (What's wrong → Where → Why → Who)
- **aio-autobuilder**: one prompt ("build the demo") creates the Q1–Q4 worksheets and the story dashboard
- **aio-audience**: interpreter for presenters and viewers ("why did this move?", "what should we do?")

## Files

| Path | Purpose |
|---|---|
| `skills/` | Generic skills (work without a demo; each asks for the story if `references/demo-story.md` is missing) |
| `install_studio_skills.sh` | Installs the generic skills into Tableau Studio |
| `COMMAND.md` | Pointer. The command is now `.claude/commands/studio.md` and the engine is `studio_skills.py` (repo root) |
| `docs/` | Design doc (`studio-skills-design.md`), Studio guide, external API reference, v2 notes |
| `INTEGRATION.md`, `studio.patch` | How to merge this into core later |

## Run

In Claude Code:
- `/studio {slug}`: generate `demos/{slug}/studio_skills/` from the demo's checkpoint `story`. If there's no story, it asks the story questions, so it works standalone with no build and no org.
- `/studio {slug} --new`: re-ask the story
- `/studio {slug} --install`: generate, then install into Tableau Studio

Then run `bash demos/{slug}/studio_skills/install.sh`, and type `/reload-skills` in Tableau Agent.

Generic skills only: `bash sidekicks/studio/install_studio_skills.sh`.

If `/close-loop {slug}` has been built, `/studio` adds a **Close the Loop** section to `demo-story.md`. Re-run `/studio` after building close-loop.

## Dependencies

- Tableau Studio (to install and use the skills): opened once, with Tableau Agent opened once, so `~/Documents/My Tableau Repository (Beta)/Tableau Agent/skills` exists.
- No Python packages, credentials, or core code changes. Markdown and shell only.
