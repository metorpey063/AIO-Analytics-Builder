# The Four-Question Story Pattern

Every AiO demo follows the same arc. These four questions are the structure that lets your audience *solve a problem*, not just see a chart.

## Q1: "What is wrong?"

**Audience question:** Is there a problem I should care about?

**What the worksheet shows:** Your primary metric over time (trend line), declining hard enough to see in about 10 seconds. No filters, no breakdowns—just the headline metric and its trajectory.

**Why it works:** The audience sees the problem unmissably. They don't need to drill, filter, or interpret. The metric says "we're in trouble" clearly.

**Typical viz:** Line chart. Metric on Y-axis, Time (Week, Month, Year) on X-axis. Spark-like, 12–24 months of history. Color should emphasize the decline (red if down is bad).

---

## Q2: "Where is it worst?"

**Audience question:** Which segment is driving this? Where should I focus?

**What the worksheet shows:** Primary metric broken down by a key dimension (Region, Vertical, Program Type, etc.), ranked by the metric value, with the culprit segment(s) unmissable.

**Why it works:** Audience discovers that the problem is **not evenly distributed**. One or two segments are catastrophic, others are moderate, and maybe one is actually improving. This is the "aha"—the average hides the real story.

**Typical viz:** Horizontal bar chart, sorted descending. Segment names on Y-axis, metric on X-axis. Highlight the worst segment in a contrasting color. If you have a counter-trend segment (one improving while others decline), use a different color for that too.

---

## Q3: "Why is it happening?"

**Audience question:** What is the root cause? What moved first?

**What the worksheet shows:** Supporting metrics that explain the primary, often moving *earlier* or *smaller* than the primary metric, plus a cost or effort dimension that reveals the lever.

**Why it works:** Supporting metrics prove the root cause. For example: "Redemption Rate dropped first → then Points Per Rep fell → then overall Participation Rate declined." The audience sees the causal chain. A cost/effort dimension (e.g., "Plan Cost Tier", "Deal Size Band") often reveals the root cause is financial or operational friction.

**Typical viz:** Multi-line chart (supporting metrics over time), or a dual-axis if you're showing a trend and a categorical breakdown. Supporting metrics should lag the primary metric (don't move as much, or move earlier). Include a secondary breakdown if explaining cost/effort.

---

## Q4: "Who needs action?"

**Audience question:** Which specific people/accounts/teams are at risk? What should I do?

**What the worksheet shows:** The finest grain of your data (individual account, team, rep, etc.), filtered to the culprit segment(s) from Q2, ranked by the metric, top-N rows. Include an owner field if available (which account manager owns this account, which executive sponsors this team).

**Why it works:** The audience moves from "this segment is bad" to "Bob's team is in the red zone. He's my responsibility. I need to call him." It's personal and actionable.

**Typical viz:** Table or ranked bar. Rows = individual entities (accounts, teams). Columns = metric value, owner/manager, filters applied. Typically top 10–20 rows, enough to be actionable without overwhelming.

---

## How the story compounds

The demo narrative works like this:

1. **Q1 opens:** "Overall participation dropped 25% in the last quarter."
2. **Q2 drills:** "But look—President's Club is down 40%, Mid-Market is down 20%, SMB is actually flat, Enterprise is up 5%."
3. **Q3 explains:** "Redemption Rate started falling in August, before Participation dropped. And when we look at Plan Cost Tier, it's clear: high-cost programs are getting hit hardest."
4. **Q4 acts:** "Here are the 15 accounts in President's Club with the worst trend. Sarah owns three of them. Let's call them today."

Each question is more specific than the last, and the audience goes from pattern (Q1) → segment (Q2) → root cause (Q3) → action (Q4).
