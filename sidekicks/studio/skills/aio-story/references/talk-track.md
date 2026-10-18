# Talk Track — Example Phrasings for the Builder

This file provides example phrasings you can use when describing what you want on each worksheet. Use these as templates—adapt them to your specific metrics and dimensions.

## Triggering the skill

**To start the full story:** "Walk me through the AiO story" or "Help me build a four-question demo"

**To jump to a specific question:** "Help me build Q2" or "What should the dashboard look like?"

---

## Q1: "What is wrong?" — Primary Metric Over Time

### What to say

*"Show me [metric name] over time, declining from [start date] to now. I want it to be obvious in 10 seconds that we have a problem."*

### Examples

- "Show me enrollment rate over the last 24 months, trending downward."
- "Line chart: participation rate, month by month, with a clear drop in the last quarter."
- "I want to see ARR trending down from Jan to now. Make the decline unmissable."
- "Trending redemption rate week by week for the last 12 months."

### What Claude will help with

- Choosing the right time grain (daily, weekly, monthly, quarterly)
- Setting the metric direction so the decline is visually alarming (red if down is bad)
- Adding a reference line for "last year" or "baseline" if helpful

---

## Q2: "Where is it worst?" — Metric by Dimension, Ranked

### What to say

*"Break down [metric name] by [dimension], sorted so the worst is first. I want to see which [segment] is driving the decline."*

### Examples

- "Show me participation rate by program type, sorted worst to best. I want program type on the left, rate on the bottom."
- "Break it down by region, with the region doing worst on top."
- "Rank accounts by their enrollment rate, top 10 worst accounts."
- "Show me by vertical, sorted so the vertical losing the most is on the left."
- "Breakdown by size band: where's our biggest decline happening? Enterprise, mid-market, or SMB?"

### What Claude will help with

- Choosing horizontal vs. vertical bars (usually horizontal, so you can read segment names)
- Highlighting the culprit segment(s) in a contrasting color
- Deciding whether to show all segments or top/bottom N
- Adding a counter-trend segment in a different color if one exists

---

## Q3: "Why is it happening?" — Supporting Metrics + Cost/Effort Dimension

### What to say

*"Show me [supporting metric 1] and [supporting metric 2] over time, and break it down by [cost/effort dimension] so we can see what's driving it."*

### Examples

- "Multi-line trend: show me redemption rate dropping first, then points per rep following. Which program type is hit hardest?"
- "Dual-axis chart: enrollment rate on the left, cost per enrollment on the right, both over time."
- "Break down by deal size band: is our big deals revenue holding up while SMB collapses?"
- "Show me plan cost tier. Are high-cost plans the ones declining?"
- "Trending two things: voluntary plan adoption and involuntary plan adoption, side by side."

### What Claude will help with

- Choosing multi-line vs. dual-axis vs. side-by-side breakdown
- Setting supporting metrics to lag (move earlier or smaller than the primary)
- Deciding whether to show the supporting metric + dimension together or separately

---

## Q4: "Who needs action?" — Individuals/Accounts, Filtered to Culprit

### What to say

*"Show me the [finest dimension] in the [culprit segment], ranked by [metric], top [N]. Include [owner field] so I know who owns each one."*

### Examples

- "Top 15 accounts in President's Club with the worst participation rate. Include the account manager name so I know who to call."
- "Top 10 states in the Northeast region where revenue is down most. Include the regional manager."
- "All teams with fewer than 5 active users, sorted by user count, ascending. Show me the team lead."
- "Worst-performing accounts by ARR at risk. Include the account owner and the renewal date."
- "Individual reps in the quota attainment program with the lowest year-to-date completion rate."

### What Claude will help with

- Choosing table vs. ranked bar (tables are easier to action)
- Deciding how many rows to show (enough to act on, not overwhelming—typically 10–20)
- Including fields that enable action (owner name, phone, email if available)
- Sorting (ascending if low is bad, descending if high is bad)

---

## Dashboard Assembly

### What to say

*"Arrange these four worksheets in story order: [Q1], then [Q2], then [Q3], then [Q4]. Use titles that are the questions so the audience knows what story we're telling."*

### Example

- "Put them in a 2×2 grid. Top-left is 'What is wrong?', top-right is 'Where is it worst?', bottom-left is 'Why?', bottom-right is 'Who needs action?' Make it clear these are the four questions."
- "Stack them vertically so I can scroll through the story. Make each title a question."

### What Claude will help with

- Choosing 2×2 grid, vertical stack, or custom arrangement
- Writing titles that are audience questions (not technical metric names)
- Sizing worksheets so the story is readable
- Adding a title and description to the dashboard

---

## Refining a worksheet

### What to say

*"The chart looks good, but [change]. Can you [action]?"*

### Examples

- "I want to highlight the mid-market segment differently—it's our counter-trend."
- "Can you hide the Enterprise segment and focus on President's Club?"
- "Sort the bars the other way—best on top instead of worst on top."
- "Add a threshold line at 50% so we can see which accounts are above/below that target."
- "Change the color to red for the culprit segments and green for the improving ones."

### What Claude will help with

- Color, sorting, filtering, annotations
- Removing noise or adding reference lines
- Changing chart type if a different viz tells the story better

---

## When you're stuck

**Say:** "What should Q2 focus on?" or "Help me pick the dimension for this breakdown."

**Claude can help with:**
- Suggesting which dimension is most actionable
- Deciding between related dimensions
- Picking a supporting metric that lags the primary
- Recommending a segment to highlight
