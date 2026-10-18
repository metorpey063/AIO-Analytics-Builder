# Signal Design Rules for Drillable Stories

When building a story-driven demo, your data should be engineered so the story *reveals itself* as the audience drills down. These rules ensure your data tells the right story, with the culprit unmissable and the counter-trend credible.

## Segment Differentiation by Multiplier

**The problem:** If all segments decline equally, the average hides nothing. The audience drills and sees "everything is down 20%."

**The solution:** Assign different impact multipliers to each segment so the story compounds as you drill.

### Multiplier ranges

| Segment role | Multiplier range | What it means |
|---|---|---|
| **Culprit (worst)** | 1.5–2.5× | This segment is the primary driver. Drops 40–50% when the overall metric is down 20%. |
| **Moderate** | 0.8–1.2× | This segment moves in line with the average or slightly better. |
| **Counter-trend** | -0.10 to 0.0 | This segment is *improving* while others decline. Props up the overall average so the true severity is hidden. |

### Example: Enrollment Rate with Program Types

- **President's Club** (culprit): 2.0× multiplier → drops from 75% to 45% (30 percentage points)
- **Mid-Market** (moderate): 1.0× multiplier → drops from 60% to 40% (20 percentage points)
- **SMB** (moderate): 0.9× multiplier → drops from 50% to 32% (18 percentage points)
- **Enterprise** (counter-trend): -0.10 multiplier → improves from 55% to 65% (+10 percentage points)

**The narrative:** Overall enrollment is down 20%. But President's Club is down 30%, which is why everyone is worried. Enterprise improving masks how bad it really is.

## Supporting Metrics Lag the Primary

**Why:** The audience moves through a causal chain. What moved *first* is often the root cause.

**How:** Supporting metrics should use 0.7× the primary metric's multiplier and move earlier in time.

### Example: Redemption Rate → Participation Rate

- **Redemption Rate** (leading indicator): multiplier 1.4× (70% of primary's 2.0×)
- **Participation Rate** (lagging indicator): multiplier 2.0×
- **Timeline:** Redemption starts falling in August; Participation follows in September.

**The story:** "See? Redemption Rate dropped first. That's what broke the machine."

## Counter-Trend Segment

**Why:** A segment that improves while others decline makes the overall average *misleading on purpose*. The "aha" moment is when the audience sees they've been looking at the wrong thing.

**How:** Pick one segment (e.g., Enterprise, Channel Partner, Global) and give it a small negative multiplier (-0.05 to -0.15). It should move visibly upward while everything else declines.

### Important constraint

- **Never set counter-trend below -0.15**, or the upward trend becomes implausibly obvious and looks fake.
- **Only one counter-trend segment per metric.** Multiple improving segments dilute the story.

### Example reveal

- Q1: "Participation down 25% overall."
- Q2: "Enterprise is up 5%! Wait, what? Enterprise is improving while President's Club tanks?"
- Q3: "Ah, Enterprise has a dedicated account team and aren't affected by the cost-cutting that hit our SMB and Mid-Market programs."

## Signal Ramp Shape

**Default: Accelerating (quadratic).** Slow at first, steeper toward the present. This mirrors how real problems manifest (small at first, urgent recently).

### Ramp formula (conceptual)

```
progress = min(1.0, (months_from_onset) / duration)
if accelerating:
    signal = progress ** 2
else:
    signal = progress  # linear
```

- `onset`: how many months before today the signal started (e.g., onset=-3 = started 3 months ago)
- `duration`: how many months until the signal reaches full magnitude (e.g., duration=3 = takes 3 months to go from 0 to full)
- `SIGNAL_MAGNITUDE`: the full impact multiplier (0.45–0.55 recommended, since accelerating keeps early months flat)

### Why accelerating beats linear

- **Linear:** Signal rises steadily from month -3 to month 0. Looks too uniform, like a straight line.
- **Accelerating:** Signal is tiny in month -3 (almost flat), then rises quickly. Month -1 is already 75% of full magnitude. Feels like something that just started happening, not a slow drift.

## Noise Scale by Size Band

**Why:** Large segments (Global, Enterprise) should be smoother; small segments (SMB, startups) need more noise to look realistic.

### Typical noise scale (standard deviation)

| Segment | Noise std dev |
|---|---|
| Small Enterprise | 0.022 |
| Mid-Market | 0.016 |
| Large Enterprise | 0.011 |
| Global | 0.007 |

**Application:** Add normal-distributed random noise scaled to the segment size. Smaller segments show more churn; larger segments are stable.

## Base Value Variation

**Why:** If all clients start at the same base level, the data looks synthetic at the row level.

**How:** For each client/account, randomize the starting value (e.g., `random.uniform(0.62, 0.82)` for a 62–82% metric).

**Result:** Rows look diverse and realistic. When the audience filters, they see variation that feels lived-in.

## Summary Checklist

Before you finalize your story data:

- [ ] **Culprit segment(s)** assigned 1.5–2.5× multiplier?
- [ ] **Moderate segments** assigned 0.8–1.2× multiplier?
- [ ] **One counter-trend segment** assigned -0.05 to -0.15 multiplier?
- [ ] **Supporting metrics** use 0.7× multiplier and move earlier (or move smaller)?
- [ ] **Signal ramp** set to accelerating (quadratic) by default?
- [ ] **Noise scaled** by segment size (larger = smoother)?
- [ ] **Base values randomized** per client/account?

If yes to all, your data will tell a compelling story.
