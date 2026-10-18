---
name: aio-story
description: Use to build a story-driven demo in Tableau Studio. Prompts: "walk the AiO story", "build the next worksheet", "what should Q2 show", "create the dashboard".
---

# AiO Story Builder

This skill guides you through building a four-question story in Tableau Studio, where each worksheet answers a key audience question. You'll build worksheets that surface the problem, locate it, explain it, and identify who to act on.

## How to use this skill

0. **Check for demo-specific context first.** Look for a file at `references/demo-story.md` next to this skill. If it exists, this skill was generated for a specific AiO demo build — read it and use its primary metric, dimensions, culprit/counter-trend segments, and root cause as the specifics for this build instead of asking the user to supply them. Confirm what you found ("I see this demo's story is about {metric}, with {culprit segment} as the problem area — let's build Q1 around that") rather than re-asking from scratch. If `references/demo-story.md` does not exist, this is a standalone/generic session — proceed to step 2 and ask the user conversationally.

1. **Start with a datasource.** Connect a published datasource (Tableau Pulse, Data Cloud, or any other source) in Tableau Studio before invoking this skill.

2. **Ask the builder questions.** Say "walk the AiO story" or "help me build question 1" and Claude will guide you step-by-step through each worksheet.

3. **Clarify your metrics and dimensions.** The skill will ask you for:
   - Your primary metric (e.g., "Enrollment Rate") and its direction (up or down)
   - Key dimensions for filtering and drilling (e.g., "Region", "Program Type", "Size Band")
   - Supporting metrics that explain the primary (e.g., "Redemption Rate" before "Enrollment Rate")

4. **Build each question.** Claude will help you create:
   - **Q1: "What is wrong?"** — Primary metric over time (line chart)
   - **Q2: "Where is it worst?"** — Primary metric by your chosen dimension, ranked bar, with culprit highlighted
   - **Q3: "Why is it happening?"** — Supporting metrics and a cost/effort dimension
   - **Q4: "Who needs action?"** — Your finest dimension, filtered to the culprit, top-N rows

5. **Assemble the dashboard.** Claude will help you arrange the four worksheets in story order with clear titles.

## The four-question pattern

Each question has a specific role in your demo narrative. Read `references/four-questions.md` to understand what each worksheet should show and why.

## Segment differentiation rules

To make your story drillable and your audience find the culprit immediately, use the segment multiplier rules in `references/signal-design.md`. One or two segments should be the clear culprit (1.5–2.5× your base metric), a couple should be moderate (0.8–1.2×), and at least one should be flat or improving (counter-trend) so the average hides the problem.

## Example phrasings

When Claude asks you what you want on a worksheet, you can say things like:
- "Show me enrollment rate declining over time" (Q1)
- "Break it down by program type, sorted with the worst on the left" (Q2)
- "Show me redemption rate and points per rep trending together" (Q3)
- "Give me the top 10 accounts in the worst program type" (Q4)

See `references/talk-track.md` for more examples.
