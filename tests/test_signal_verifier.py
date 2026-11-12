"""signal_verifier: passes data that tells the story, fails data that doesn't.

    python3 -m unittest tests.test_signal_verifier -v
"""
import io
import random
import sys
import unittest
from contextlib import redirect_stdout
from datetime import date, timedelta
from unittest import mock
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import data_generator  # noqa: E402
import signal_verifier  # noqa: E402
from signal_verifier import (verify_signal, culprit_from_multipliers,  # noqa: E402
                             expected_effect, FALLBACK_MIN_EFFECT)

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


def make(drop, counter=0.10, seed=1, wander=0.0, months=24):
    """`months`+1 monthly points; `drop` maps (region, tier) -> fractional fall in
    the last 3 months. `wander` adds the generators' kind of background: an
    AR(1) path and a drift per region, which month-to-month noise doesn't show."""
    rng = np.random.default_rng(seed)
    paths = {}
    for r in REGIONS:
        e, path = 0.0, []
        slope = rng.uniform(-1, 1) * wander
        for t in range(months + 1):
            e = 0.6 * e + rng.normal(0, wander)
            path.append(1 + e + slope * (t / months * 2 - 1))
        paths[r] = path
    rows = []
    for t, m in enumerate(range(months, -1, -1)):
        y, mo = divmod(TODAY.year * 12 + TODAY.month - 1 - m, 12)
        d = date(y, mo + 1, 1)
        ramp = max(0, 3 - m) / 3 if m < 3 else 0.0
        for r in REGIONS:
            for t2 in TIERS:
                for _ in range(3):
                    f = drop.get((r, t2), 0.0) * ramp
                    rows.append({
                        "Date": d, "Region": r, "Tier": t2,
                        "Retention Rate": 0.85 * paths[r][t] * (1 - f) + rng.normal(0, 0.004),
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

    def test_culprit_is_the_largest_multiplier_not_the_first_dimension(self):
        mm = {"Region": {"West": 1.8, "East": 0.4}, "Segment": {"Mid-Market": 2.2, "SMB": 0.1}}
        self.assertEqual(culprit_from_multipliers(mm, ["Region", "Segment"]),
                         (("Segment", "Mid-Market"), None))

    def test_runner_up_close_behind_warns(self):
        close = {**GOOD, ("East", "Gold"): 0.30, ("East", "Silver"): 0.23}
        r = run(make(close))
        self.assertIn("culprit_margin", {c["name"] for c in r["warnings"]})


class Noise(unittest.TestCase):
    def test_no_signal_never_passes(self):
        """Background wander alone must not read as the story, even when the settings
        ask for a gentle one (the old expected-scaled cutoffs passed 5 of these 40)."""
        passed = [s for s in range(40) if run(make({}, seed=s, wander=0.03), expected=0.02)["ok"]]
        self.assertEqual(passed, [])

    def test_noise_is_measured_from_the_data(self):
        quiet = run(make(GOOD, wander=0.0))["stats"]["thresholds"]["noise_sd"]
        noisy = run(make(GOOD, wander=0.04))["stats"]["thresholds"]["noise_sd"]
        self.assertLess(quiet, 0.01)
        self.assertGreater(noisy, 0.03)

    def test_gentle_story_passes_on_a_quiet_background_only(self):
        gentle = {k: v * 0.2 for k, v in GOOD.items()}          # ~6% culprit effect
        self.assertTrue(run(make(gentle))["ok"], run(make(gentle))["failures"])
        self.assertIn("culprit_signal_vs_noise", names(run(make(gentle, wander=0.05))))

    def test_settings_inside_the_noise_warn(self):
        r = run(make(GOOD, wander=0.04), expected=0.05)
        self.assertIn("designed_vs_noise", {c["name"] for c in r["warnings"]})

    def test_short_history_falls_back_and_warns(self):
        r = run(make(GOOD, months=7))
        self.assertTrue(r["ok"], r["failures"])
        self.assertEqual(r["stats"]["thresholds"]["min_effect"], FALLBACK_MIN_EFFECT)
        self.assertIn("culprit_signal_vs_noise", {c["name"] for c in r["warnings"]})

    def test_sum_metric_with_a_partial_current_month(self):
        """Daily rows run to mid-month: a monthly sum would read month 0 as a crash."""
        metrics = [{"label": "Bookings", "sentiment": "up_is_good", "agg": "Sum", "is_primary": True}]
        rng = np.random.default_rng(3)
        rows, d, end = [], date(2024, 11, 1), date(2026, 11, 12)
        while d <= end:
            m = (end.year - d.year) * 12 + end.month - d.month
            ramp = max(0, 3 - m) / 3 if m < 3 else 0.0
            for r in REGIONS:
                f = {"West": 0.30, "East": 0.05}.get(r, 0.0) * ramp
                rows.append({"Date": d, "Region": r, "Tier": "Gold",
                             "Bookings": 1000 * (1 - f) + rng.normal(0, 20)})
            d += timedelta(days=1)
        r = verify_signal(pd.DataFrame(rows), metrics, ["Region"], {"culprit": {"dimension": "Region", "value": "West"}},
                          onset_months=3, today=end)
        self.assertTrue(r["ok"], r["failures"])
        self.assertAlmostEqual(r["stats"]["segments"]["South"], 0.0, delta=0.02)


class PlanProblems(unittest.TestCase):
    def assertNotRedrawable(self, report, check):
        self.assertIn(check, names(report))
        self.assertFalse(report["fixable_by_redraw"])

    def test_culprit_value_not_in_data(self):
        r = run(make(GOOD), plan={**PLAN, "culprit": {"dimension": "Region", "value": "Pacific"}})
        self.assertNotRedrawable(r, "culprit_exists")
        self.assertEqual(r["stats"]["culprit"], ("Region", "Pacific"))

    def test_culprit_off_the_signal_dimension(self):
        self.assertNotRedrawable(run(make(GOOD), signal_dims=["Tier"]), "culprit")

    def test_drill_down_on_the_culprit_dimension(self):
        plan = {**PLAN, "culprit_detail": {"dimension": "Region", "value": "East"}}
        self.assertNotRedrawable(run(make(GOOD), plan=plan), "detail_steeper")

    def test_counter_trend_is_the_primary(self):
        self.assertNotRedrawable(run(make(GOOD), plan={**PLAN, "counter_trend_metric": "Retention Rate"}),
                                 "counter_trend")

    def test_a_missed_draw_is_redrawable(self):
        r = run(make({k: 0.25 for k in GOOD}))
        self.assertFalse(r["ok"])
        self.assertTrue(r["fixable_by_redraw"])


class ExpectedEffect(unittest.TestCase):
    def test_follows_settings(self):
        weak = expected_effect(0.2, 3)
        strong = expected_effect(0.5, 3)
        self.assertGreater(strong, weak)
        self.assertGreater(weak, 0)
        self.assertLessEqual(strong, 0.45)                       # realism cap
        self.assertGreater(expected_effect(0.4, 3, up_is_good=False, bad_boost=2.0),
                           expected_effect(0.4, 3, up_is_good=False, bad_boost=1.0))

    def test_worst_multiplier_and_ceiling(self):
        self.assertLess(expected_effect(0.4, 3, culprit_mult=2.0, worst_mult=2.9), expected_effect(0.4, 3))
        self.assertLessEqual(expected_effect(0.4, 3, up_is_good=False, max_effect=0.18), 0.18)


DG_DIMS = {"Region": ["West Coast", "Northeast", "Southeast", "Midwest"],
           "Client Segment": ["Mid-Market", "Small Business", "Micro Business", "Large Enterprise"]}


def dg_kwargs(**kw):
    return {"metrics": [{"label": "Enrollment Rate", "field": "x", "sentiment": "up_is_good", "agg": "Average",
                         "is_primary": True, "base_range": [0.62, 0.82]}],
            "dimensions": list(DG_DIMS), "dimension_values": DG_DIMS,
            "multipliers": {"Region": {"West Coast": 2.0, "Northeast": 0.8, "Southeast": 0.1, "Midwest": -0.1}},
            "today": date(2026, 11, 12), **kw}


class GenerateDemoData(unittest.TestCase):
    def test_weekly_and_daily_run_through_today(self):
        for grain, latest in (("weekly", date(2026, 11, 8)), ("daily", date(2026, 11, 12))):
            with redirect_stdout(io.StringIO()):
                df = data_generator.generate_demo_data(**dg_kwargs(grain=grain, history_months=6))
            self.assertEqual(max(df["Date"]), latest.isoformat(), grain)

    def test_random_state_is_the_returned_draws(self):
        """Every draw misses, the first scores best: the RNG must be as seed 42 left it."""
        def fake(df, *a, **kw):
            fake.n += 1
            return {"ok": False, "failures": [{"message": "miss", "redraw": True}],
                    "stats": {"culprit_z": 10 - fake.n}, "fixable_by_redraw": True,
                    "checks": [], "warnings": []}
        fake.n = 0
        with mock.patch.object(signal_verifier, "verify_signal", fake), redirect_stdout(io.StringIO()):
            df = data_generator.generate_demo_data(**dg_kwargs(history_months=6))
        after = (random.random(), np.random.random())
        data_generator._generate_once(**dg_kwargs(history_months=6, seed=42))
        self.assertEqual(df.attrs["signal_seed"], 42)
        self.assertEqual(after, (random.random(), np.random.random()))


if __name__ == "__main__":
    unittest.main()
