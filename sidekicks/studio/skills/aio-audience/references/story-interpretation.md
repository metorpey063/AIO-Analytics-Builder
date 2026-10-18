# How to Read Each Question in the Story

When the audience asks about a chart, Claude should know which of the four questions it belongs to and how to interpret it accordingly. This file explains the story role of each question and what to highlight.

## Q1: "What is wrong?" — Primary Metric Over Time

**What the audience sees:** A trend line showing the primary metric declining over 12–24 months.

**What Claude tells them:**

- **The headline:** "Your [metric] is down [X]% over [time period]."
- **The urgency:** Emphasize the *direction* and *acceleration*. Is it getting worse? Did it just start or has it been steady?
- **The scope:** "This is across all [segments], not just one area."

### Example interpretation

**Chart:** Enrollment rate declining from 75% (Jan) to 50% (Oct).

**Claude says:** "Enrollment is down 25 percentage points in the last 10 months. But look at the curve—it's getting *steeper*. August was bad. September was worse. October is the worst. We're accelerating downward, and that's the urgent part. If this keeps going, enrollment will be critical by year-end."

---

## Q2: "Where is it worst?" — Metric by Dimension, Ranked

**What the audience sees:** A ranked breakdown showing one or more segments as clear culprits, with contrast (some segments worse, some better, maybe one improving).

**What Claude tells them:**

- **The culprit:** "President's Club is down 40%, driving most of the decline."
- **The contrast:** "But look at Enterprise—it's actually *up* 5%. That's the puzzle."
- **The insight:** "So the problem is concentrated. It's not systemic. President's Club and Mid-Market are in trouble, but Enterprise is resilient."

### Example interpretation

**Chart:** Enrollment rate by program type (President's Club 45%, Mid-Market 40%, Enterprise 55%).

**Claude says:** "President's Club is the problem child—down to 45% from 75%. Mid-Market is also struggling at 40%. But Enterprise is 55%, which is *higher than it was a year ago*. So we're not in an industry-wide downturn. We're in a *product mix problem*. The expensive programs are getting hit, and the efficient program is doing fine."

---

## Q3: "Why is it happening?" — Supporting Metrics + Cost/Effort Dimension

**What the audience sees:** Supporting metrics (that moved earlier or smaller) plus a cost/efficiency dimension that explains the lever.

**What Claude tells them:**

- **The causal chain:** "Redemption rate fell first. Then engagement dropped. Then enrollment followed."
- **The root cause:** "And when we segment by plan cost tier, it's clear: high-cost plans are being abandoned. Members are cost-sensitive."
- **The implication:** "So it's not a product problem. It's a pricing or positioning problem."

### Example interpretation

**Chart:** Multi-line trend (Redemption, Engagement, Enrollment) + breakdown by cost tier.

**Claude says:** "Notice the sequence: Redemption rate started falling in August—members stopped using their benefits. Engagement followed in September. Enrollment didn't drop until October. That sequence tells us what happened: members saw the cost wasn't worth the value, so they stopped redeeming, which broke engagement. Then new enrollment cratered because word spread.

And here's the real clue: when we look by cost tier, high-cost plans are abandoned, but our lowest-cost tier is holding steady. So it's not that the benefits are bad. It's that the *price* is too high relative to the value members get. We priced ourselves out of the market."

---

## Q4: "Who needs action?" — Individuals/Accounts, Filtered to Culprit

**What the audience sees:** A list of specific people/accounts/teams in the culprit segment, ranked by how bad it is, with owner info.

**What Claude tells them:**

- **The priority:** "These 15 accounts are your biggest risks. 80% of the revenue at stake is in this list."
- **The ownership:** "Sarah owns three of them. David owns two. Let's call Sarah first—she has the most at risk."
- **The ask:** "If you can save *these* accounts, you solve the problem. Everyone else on the list, we have time."

### Example interpretation

**Chart:** Table of top 15 at-risk President's Club accounts, sorted by dollars at risk, with owner.

**Claude says:** "These 15 accounts are your immediate action list. They're in President's Club, they've disengaged the hardest, and they represent $2.8M in ARR. You have 90 days before their renewals hit. Sarah owns three of them—Sarah, you're going to want to be in these conversations first. David, you've got two. These 15 are where we either win or we don't. The rest of the portfolio, we can manage incrementally."

---

## Connecting the questions

When the audience asks a question that spans multiple questions, Claude should connect them:

**Audience:** "Are we going to lose money?"

**Claude (connecting Q4 to Q1–Q2):** "Look at Q1 first: yes, enrollment is down 25%. Now Q2 shows it's concentrated in President's Club. Q4 shows that if we lose these 15 accounts, we're down $2.8M. So the answer is: *not yet*, but we're on that path. If Sarah's accounts renew, we buy time. If they don't, we're in trouble."

---

## The four-question narrative flow

Always connect back to this arc:

1. **Q1 sets the problem.** "What is wrong?"
2. **Q2 locates it.** "Where is it worst?"
3. **Q3 explains it.** "Why is it happening?"
4. **Q4 enables action.** "Who needs action?"

Audience questions almost always fit into this flow. If they ask something you can't answer from the visible chart, say "Let me drill into Q2 / Q3 / Q4 to answer that" and guide them through the story.
