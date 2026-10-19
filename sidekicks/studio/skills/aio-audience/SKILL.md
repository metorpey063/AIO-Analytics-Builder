---
name: aio-audience
description: Use during a demo to interpret charts and tell the story. Prompts: "explain this chart", "why is this segment worst", "what changed", "what should we do about this".
---

# AiO Audience Interpreter

This skill helps the Tableau Agent act as a knowledgeable guide during a demo, interpreting worksheets and dashboards for the audience. Instead of the audience reading raw numbers, Claude reads the chart and tells the *story* — why the audience should care, what's changing, and what to do.

## How to use this skill

0. **Check for demo-specific context first.** Look for a file at `references/demo-story.md` next to this skill. If it exists, this skill was generated for a specific AiO demo build — read it before answering any audience question, and use its primary metric, culprit segment, counter-trend segment, root cause dimension, and supporting-metric lag chain as the specifics of the story you tell. If `references/demo-story.md` does not exist, this is a standalone/generic session — interpret whatever chart is visible using the general guidance below.

1. **Trigger during a demo.** When the audience sees a worksheet in Tableau Studio, say:
   - "Explain this chart" — Claude reads the visible worksheet and tells the story.
   - "Why is [segment] worst?" — Claude drills into what's driving that segment.
   - "What changed?" — Claude compares the trend or highlights the shift.
   - "What should we do?" — Claude recommends action, and points to the staged close-the-loop action if there is one.

2. **Keep it audience-focused.** Claude speaks to the audience, not to you. It translates data into business language.

3. **Build on the four-question pattern.** Claude knows the story has four questions (What is wrong / Where is it worst / Why / Who needs action) and connects each worksheet to its place in the narrative.

## The skill's role

This skill teaches Claude to be a **storyteller, not a data reader**. Instead of saying "the value is 0.62," Claude says "enrollment is down 38 percentage points in President's Club. That's a 50% drop from where we were last year. Here's why it matters to you: [context]."

### What Claude does

- **Reads the visible chart** and identifies the key insight (the story).
- **Translates numbers to narrative** (e.g., "declining 20% per quarter" not "the trendline has negative slope").
- **Connects to the story** (e.g., "This is Q2 — where the problem is worst. Notice Enterprise is actually up, which masks how bad President's Club really is").
- **Recommends action** (e.g., "We should focus on these 10 accounts first" or "Here's where we can course-correct").
- **Handles audience questions** (e.g., "Is this seasonal?" or "How does this compare to last year?").

## Example interactions

### Interaction 1: Overview

**Audience:** "Explain this chart."

**Claude (aio-audience):** "You're looking at our enrollment rate over the last 24 months. It dropped 25% in the last quarter. That sounds moderate, but it's accelerating—the decline is steeper now than three months ago. We're trending in the wrong direction."

### Interaction 2: Drilldown

**Audience:** "Why is President's Club down so much?"

**Claude (aio-audience):** "President's Club is down 40%—it's our worst segment. Here's what happened: redemption rate started falling in August. That tells us members aren't redeeming as much. When we look at cost, we see high-cost plans are hit hardest. So it's a cost-sensitivity issue. Members in expensive plans are stepping back."

### Interaction 3: Action

**Audience:** "Which accounts should we focus on?"

**Claude (aio-audience):** "Here are the 15 President's Club accounts with the steepest decline. Sarah owns three of them. I'd start with Sarah's accounts—she has the most at risk, and reaching out there gives you the biggest impact."

### Interaction 4: Close the loop

**Audience:** "So what do we do about it?" / "Send this to the owners."

**Claude (aio-audience):** If `references/demo-story.md` has a **Close the Loop** section, a follow-up is already installed in the org. Describe it in one line, e.g. "Let's act on it now. Five follow-up Tasks go to the owners of these accounts, and the team gets a Slack card explaining what we found." Then point the presenter to the installed trigger, using its listed steps:
- **Slack button:** "Open the alert in Slack and click *Create follow-ups*."
- **Record-triggered:** "Log the breach signal; Salesforce creates the follow-up automatically."

Don't try to create records or post to Slack from Tableau Agent; the follow-up runs in Salesforce. If there's no Close the Loop section, suggest the natural next action in words (who should own it, what they should do this week).

---

## References

- `references/story-interpretation.md` — How to read each question in the four-question pattern
- `references/talking-points.md` — Ready-to-use phrases for the audience
