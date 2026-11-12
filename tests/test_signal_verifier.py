"""signal_verifier: passes data that tells the story, fails data that doesn't.

    python3 -m unittest tests.test_signal_verifier -v
"""
import sys
import unittest
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from signal_verifier import (verify_signal, culprit_from_multipliers,  # noqa: E402
                             expected_effect, _thresholds)

TODAY = date(2026, 11, 1)
METRICS = [
    {"label": "Retention Rate", "sentiment": "up_is_good", "agg": "Average", "is_primary": True},
    {"label": "Support Load", "sentiment": "up_is_bad", "agg": "Average"},
    {"label": "Referral Rate", "sentiment": "up_is_good", "agg": "Average"},
]
PLAN = {"culprit": {"dimension": "Region", "value": "West"},
        "culprit_detail": {"dimension": "Tier", "value": "Gold"},
        "counter_trend_metric": "Referral Rate"}
REGIONS, TIERS = ["West", "East", "South"], ["Gold", "Silver"]


def make(drop, counter=0.10, seed=1):
    """24 months; `drop` maps (region, tier) -> fractional fall in the last 3 months."""
    rng = np.random.default_rng(seed)
    rows = []
    for m in range(24, -1, -1):
        y, mo = divmod(TODAY.year * 12 + TODAY.month - 1 - m, 12)
        d = date(y, mo + 1, 1)
        ramp = max(0, 3 - m) / 3 if m < 3 else 0.0
        for r in REGIONS:
            for t in TIERS:
                for _ in range(3):
                    f = drop.get((r, t), 0.0) * ramp
                    rows.append({
                        "Date": d, "Region": r, "Tier": t,
                        "Retention Rate": 0.85 * (1 - f) + rng.normal(0, 0.004),
                        "Support Load": 10 * (1 + f) + rng.normal(0, 0.1),
                        "Referral Rate": 0.30 * (1 + counter * ramp) + rng.normal(0, 0.003),
                    })
    return pd.DataFrame(rows)


GOOD = {("West", "Gold"): 0.35, ("West", "Silver"): 0.25, ("East", "Gold"): 0.08,
        ("East", "Silver"): 0.08, ("South", "Gold"): 0.0, ("South", "Silver"): 0.0}


def run(df, plan=PLAN, **kw):
    return verify_signal(df, METRICS, ["Region", "Tier"], plan, onset_months=3, today=TODAY, **kw)


def names(report):
    return {c["name"] for c in report["failures"]}


class SignalVerifier(unittest.TestCase):
    def test_story_that_landed_passes(self):
        r = run(make(GOOD))
        self.assertTrue(r["ok"], r["failures"])
        self.assertEqual(r["stats"]["culprit"], ("Region", "West"))

    def test_wrong_segment_is_named(self):
        bad = {**GOOD, ("West", "Gold"): 0.0, ("West", "Silver"): 0.0,
               ("East", "Gold"): 0.35, ("East", "Silver"): 0.25}
        self.assertIn("culprit_worst", names(run(make(bad))))

    def test_signal_too_weak(self):
        weak = {k: v * 0.05 for k, v in GOOD.items()}
        self.assertTrue({"culprit_strength", "culprit_signal_vs_noise"} & names(run(make(weak))))

    def test_everything_declines_alike(self):
        flat_story = {k: 0.25 for k in GOOD}
        self.assertIn("siblings_local", names(run(make(flat_story))))

    def test_drill_down_must_get_steeper(self):
        even = {**GOOD, ("West", "Gold"): 0.25, ("West", "Silver"): 0.30}
        self.assertIn("detail_steeper", names(run(make(even))))

    def test_counter_trend_must_improve(self):
        self.assertIn("counter_trend", names(run(make(GOOD, counter=0.0))))

    def test_no_plan_checks_worst_segment(self):
        r = run(make(GOOD), plan=None)
        self.assertTrue(r["ok"], r["failures"])
        self.assertEqual(r["stats"]["culprit"], ("Region", "West"))

    def test_culprit_from_multipliers(self):
        mm = {"Region": {"West": 1.8, "East": 0.4}}
        cm = {("West", "Gold"): 2.2, ("West", "Silver"): 1.1, ("East", "Gold"): 3.0}
        self.assertEqual(culprit_from_multipliers(mm, ["Region", "Tier"], cm, ("Region", "Tier")),
                         (("Region", "West"), ("Tier", "Gold")))


class AdaptiveThresholds(unittest.TestCase):
    def test_gentler_signal_lowers_the_bar(self):
        strong = _thresholds(0.30, 1.0)
        gentle = _thresholds(0.08, 1.0)
        self.assertLess(gentle["min_effect"], strong["min_effect"])
        self.assertLess(gentle["min_z"], strong["min_z"])
        self.assertGreaterEqual(gentle["min_effect"], 0.02)
        self.assertGreaterEqual(gentle["min_z"], 1.5)

    def test_defaults_without_expected(self):
        self.assertEqual(_thresholds(None, 1.0)["scale"], 1.0)

    def test_more_variability_loosens_sibling_check(self):
        self.assertGreater(_thresholds(0.25, 1.5)["sibling_ratio"], _thresholds(0.25, 1.0)["sibling_ratio"])
        self.assertEqual(_thresholds(0.25, 0.0)["sibling_ratio"], _thresholds(0.25, 1.0)["sibling_ratio"])

    def test_expected_effect_follows_settings(self):
        weak = expected_effect(0.2, 3)
        strong = expected_effect(0.5, 3)
        self.assertGreater(strong, weak)
        self.assertGreater(weak, 0)
        self.assertLessEqual(strong, 0.45)                       # realism cap
        self.assertGreater(expected_effect(0.4, 3, up_is_good=False, bad_boost=2.0),
                           expected_effect(0.4, 3, up_is_good=False, bad_boost=1.0))

    def test_gentle_story_passes_with_expected_but_fails_on_defaults(self):
        gentle = {k: v * 0.2 for k, v in GOOD.items()}          # ~7% culprit effect
        df = make(gentle)
        self.assertIn("culprit_strength", names(run(df)))
        r = run(df, expected=0.07)
        self.assertNotIn("culprit_strength", names(r), r["failures"])

    def test_a_missing_story_still_fails_when_expected_is_high(self):
        weak = {k: v * 0.05 for k, v in GOOD.items()}
        self.assertTrue(names(run(make(weak), expected=0.30)))


if __name__ == "__main__":
    unittest.main()
