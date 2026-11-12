"""Signal verifier: did the generated data actually tell the story?

The generators set the signal up (culprit segment, drill-down cell, counter-trend,
onset). This module reads the finished DataFrame back and checks that each piece
is visible, so a story whose prose says "President's Club is cratering" can't
ship over data where it isn't. Idea adapted from the SE Data App Kit's verify.py
(per-beat lift + z-score + "everything else is flat" sibling check).

Everything is measured on "worsening": the recent change of a metric relative to
its pre-onset baseline, signed so that positive = worse for that metric's
sentiment. Segments are compared on the same scale.

    from signal_verifier import verify_signal, format_report
    report = verify_signal(df, metric_config, dimensions, signal_plan, onset_months=3)
    print(format_report(report))
    if not report["ok"]: ...   # report["failures"] are the hard misses

Hard failures (`ok=False`): culprit isn't the worst segment, is too weak or lost in
noise, siblings move as much as the culprit, the drill-down cell isn't steeper,
the counter-trend metric doesn't improve. Warnings never fail a build: no flat
segment, supporting metrics not following, culprit beyond the realism cap.
"""
from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd

# Default thresholds (worsening is a fraction: 0.10 = 10% worse than baseline).
# They are tuned for a default-strength signal (~25% culprit effect). When the
# caller passes `expected_effect` (what the chosen magnitude/onset/shape should
# produce), verify_signal scales them down for a gentler story — see _thresholds().
MIN_CULPRIT_EFFECT = 0.08      # culprit must be at least this much worse
MIN_Z = 3.0                    # culprit effect vs. month-to-month noise
SIBLING_RATIO = 0.65           # median sibling worsening <= this x culprit's
DETAIL_RATIO = 1.08            # drill-down cell >= this x the rest of the culprit
MIN_COUNTER_EFFECT = 0.03      # counter-trend metric must improve at least this much
MAX_EFFECT = 0.55              # beyond this the decline reads as implausible (warn)
BASELINE_MONTHS = 12


def _months_ago(d, today: date) -> int:
    d = pd.Timestamp(d)
    return (today.year - d.year) * 12 + (today.month - d.month)


def _col(df: pd.DataFrame, name: str):
    """Column lookup tolerant of case and underscores (same rule as data_validator)."""
    want = name.lower().replace("_", " ").strip()
    for c in df.columns:
        if c.lower().replace("_", " ").strip() == want:
            return c
    return None


def _monthly(df: pd.DataFrame, mask, value_col: str, agg: str, today: date) -> pd.Series:
    """Metric by months-ago for the rows in mask: mean per row for Average
    metrics, sum for Sum metrics (rows per month are constant, so the two are
    comparable across segments of the same size)."""
    sub = df.loc[mask]
    g = sub.groupby("_m")[value_col]
    return (g.sum() if agg == "Sum" else g.mean()).sort_index()


def _worsening(series: pd.Series, onset: int, up_good: bool, window: int):
    """(effect, z) of a monthly series. effect>0 = worse. z compares the effect to
    the month-to-month wobble of the baseline (first differences / sqrt 2, which
    drops trend and seasonality from the noise estimate)."""
    recent = series[series.index < window]
    base = series[(series.index >= onset) & (series.index < onset + BASELINE_MONTHS)]
    if len(recent) == 0 or len(base) < 3 or base.mean() == 0:
        return None, None
    change = recent.mean() / base.mean() - 1.0
    effect = -change if up_good else change
    diffs = np.diff(base.sort_index(ascending=False).values / base.mean())
    sd = float(np.std(diffs, ddof=1)) / math.sqrt(2) if len(diffs) > 2 else 0.0
    se = max(sd, 0.002) / math.sqrt(len(recent))
    return float(effect), float(effect / se)


REFERENCE_EFFECT = 0.25        # culprit effect the default thresholds were tuned around


def expected_effect(magnitude: float, onset_months: int, *, shape: str = "accelerating",
                    duration: int | None = None, culprit_mult: float = 2.0,
                    up_is_good: bool = True, bad_boost: float = 1.0,
                    window: int | None = None) -> float:
    """The worsening the chosen signal settings should give the culprit over the
    verifier's recent window (same maths as the generators: scaled magnitude x
    ramp x multiplier, capped). `bad_boost` is the extra factor up_is_bad
    metrics get (2.0 in data_generator, 1.0 in the Web UI generator)."""
    from data_generator import cap_signal, signal_scale
    onset = max(2, abs(int(onset_months)))
    window = window or min(3, onset)
    duration = duration or onset
    mag = magnitude * signal_scale(magnitude, [culprit_mult])
    vals = []
    for k in range(window):                       # k months before the latest month
        progress = max(0.0, min(1.0, (onset - k) / duration))
        ramp = progress ** 2 if shape == "accelerating" else (
            (1.0 if progress >= 0.3 else 0.0) if shape == "step" else progress)
        eff = mag * ramp * culprit_mult * (1.0 if up_is_good else bad_boost)
        vals.append(cap_signal(eff, worsens_upward=not up_is_good))
    return float(np.mean(vals))


def _thresholds(expected: float | None, variability: float) -> dict:
    """Cutoffs for this build. A gentler signal (or none specified -> defaults)
    lowers the strength and z cutoffs in proportion; more background variability
    loosens the sibling check, since segments wander more on their own."""
    scale = 1.0 if expected is None else max(0.25, min(1.0, expected / REFERENCE_EFFECT))
    var = max(0.0, float(variability))
    return {
        "scale": round(scale, 3),
        "min_effect": max(0.02, MIN_CULPRIT_EFFECT * scale),
        "min_z": max(1.5, MIN_Z * max(0.5, scale)),
        "sibling_ratio": min(0.9, SIBLING_RATIO + 0.15 * max(0.0, var - 1.0)),
        "detail_ratio": 1.0 + (DETAIL_RATIO - 1.0) * scale,
        "min_counter": max(0.01, MIN_COUNTER_EFFECT * max(0.4, scale)),
    }


def verify_signal(
    df: pd.DataFrame,
    metric_config: list[dict],
    dimensions: list[str],
    signal_plan: dict | None = None,
    *,
    onset_months: int = 3,
    today: date | None = None,
    date_col: str = "Date",
    culprit: tuple[str, str] | None = None,
    detail: tuple[str, str] | None = None,
    counter_metric: str | None = None,
    expected: float | None = None,
    variability: float = 1.0,
) -> dict:
    """Check the DataFrame against the story's signal plan.

    `signal_plan` is the story's {culprit:{dimension,value}, culprit_detail:{...},
    counter_trend_metric}. Without one, pass `culprit`/`detail`/`counter_metric`
    directly (e.g. derived from generate_demo_data's multipliers); with neither,
    the worst segment of the first dimension is checked as the culprit.

    `expected` (see expected_effect) and `variability` adapt the cutoffs to the
    build's settings; without them the defaults apply. The cutoffs used are in
    stats["thresholds"].

    Returns {"ok", "checks": [{name, ok, severity, message}], "failures",
    "warnings", "stats"}.
    """
    today = today or date.today()
    plan = signal_plan or {}
    df = df.copy()
    dcol = _col(df, date_col) or date_col
    df["_m"] = [_months_ago(d, today) for d in df[dcol]]
    onset = max(2, abs(int(onset_months)))
    window = min(3, onset)

    checks: list[dict] = []
    th = _thresholds(expected, variability)
    stats: dict = {"onset_months": onset, "window_months": window, "thresholds": th,
                   "expected_effect": expected}

    def add(name, ok, message, severity="fail"):
        checks.append({"name": name, "ok": bool(ok), "severity": severity, "message": message})

    if not metric_config or not dimensions:
        add("inputs", False, "No metrics or dimensions to verify")
        return _finish(checks, stats)

    primary = next((m for m in metric_config if m.get("is_primary")), metric_config[0])
    pcol = _col(df, primary["label"])
    if pcol is None:
        add("inputs", False, f'Primary metric column "{primary["label"]}" not in the data')
        return _finish(checks, stats)
    p_up_good = primary.get("sentiment", "up_is_good") == "up_is_good"
    p_agg = primary.get("agg", "Average")

    # Resolve culprit / detail / counter-trend from args, then plan, then the data
    if culprit is None and plan.get("culprit"):
        c = plan["culprit"]
        culprit = (c.get("dimension"), c.get("value"))
    if detail is None and plan.get("culprit_detail"):
        c = plan["culprit_detail"]
        detail = (c.get("dimension"), c.get("value"))
    counter_metric = counter_metric or plan.get("counter_trend_metric")

    def seg_effects(dim):
        dc = _col(df, dim)
        out = {}
        for val in df[dc].dropna().unique():
            s = _monthly(df, df[dc] == val, pcol, p_agg, today)
            eff, z = _worsening(s, onset, p_up_good, window)
            if eff is not None:
                out[val] = (eff, z)
        return dc, out

    # ── Overall: the problem must be visible ─────────────────────────────
    overall, oz = _worsening(_monthly(df, df.index == df.index, pcol, p_agg, today),
                             onset, p_up_good, window)
    stats["overall_worsening"] = overall
    if overall is not None:
        add("overall", overall > 0.0,
            f'{primary["label"]} is {overall:+.1%} {"worse" if overall > 0 else "better"} overall',
            "fail" if overall <= -0.02 else "warn")

    # ── Culprit segment ──────────────────────────────────────────────────
    cdim = culprit[0] if culprit and culprit[0] else dimensions[0]
    if _col(df, cdim) is None:
        add("culprit", False, f'Culprit dimension "{cdim}" is not a column in the data')
        return _finish(checks, stats)
    dc, eff = seg_effects(cdim)
    if len(eff) < 2:
        add("culprit", False, f'Not enough "{cdim}" segments with history to compare')
        return _finish(checks, stats)
    ranked = sorted(eff, key=lambda v: eff[v][0], reverse=True)
    cval = culprit[1] if culprit and culprit[1] in eff else ranked[0]
    if culprit and culprit[1] and culprit[1] not in eff:
        add("culprit_exists", False, f'Culprit "{culprit[1]}" is not a value of {cdim}')
    ce, cz = eff[cval]
    stats.update({"culprit": (cdim, cval), "culprit_effect": ce, "culprit_z": cz,
                  "segments": {str(k): round(v[0], 4) for k, v in eff.items()}})

    add("culprit_worst", ranked[0] == cval,
        f'{cval} is the worst {cdim} ({ce:+.1%})' if ranked[0] == cval else
        f'{cval} is {ranked.index(cval) + 1} of {len(ranked)} on {cdim} ({ce:+.1%}); '
        f'{ranked[0]} is worst ({eff[ranked[0]][0]:+.1%}) — the walkthrough names the wrong segment')
    add("culprit_strength", ce >= th["min_effect"],
        f'{cval} is {ce:+.1%} vs. baseline (needs >= {th["min_effect"]:.1%}; too small to see)'
        if ce < th["min_effect"] else f'{cval} is {ce:+.1%} vs. baseline')
    add("culprit_signal_vs_noise", cz >= th["min_z"],
        f'z = {cz:.1f} (needs >= {th["min_z"]:.1f}; lost in the month-to-month noise)'
        if cz < th["min_z"] else f'z = {cz:.1f}')
    if ce > MAX_EFFECT:
        add("culprit_plausible", False,
            f'{cval} is {ce:+.0%}, beyond {MAX_EFFECT:.0%}: reads as implausible', "warn")

    sibs = [eff[v][0] for v in eff if v != cval]
    med = float(np.median(sibs))
    stats["sibling_median"] = med
    add("siblings_local", med <= th["sibling_ratio"] * ce,
        f'other {cdim} values move {med:+.1%} (median) vs. {ce:+.1%} for {cval}'
        if med <= th["sibling_ratio"] * ce else
        f'other {cdim} values move {med:+.1%} (median), nearly as much as {cval} ({ce:+.1%}): '
        f'filtering reveals nothing')
    flat = [str(v) for v in eff if v != cval and eff[v][0] <= 0.5 * ce * 0.5]
    add("has_flat_segment", bool(flat),
        f'flat/improving {cdim}: {", ".join(flat[:3])}' if flat else
        f'no {cdim} value is flat — add one segment near 0 so the average hides the story',
        "warn")

    # ── Drill-down cell ──────────────────────────────────────────────────
    if detail and detail[0] and detail[1] and _col(df, detail[0]) and detail[0] != cdim:
        ddim, dval = detail
        ddc = _col(df, ddim)
        in_c = df[dc] == cval
        deff = {}
        for v in df.loc[in_c, ddc].dropna().unique():
            e, _z = _worsening(_monthly(df, in_c & (df[ddc] == v), pcol, p_agg, today),
                               onset, p_up_good, window)
            if e is not None:
                deff[v] = e
        if dval in deff and len(deff) > 1:
            de = deff[dval]
            rest = float(np.median([e for v, e in deff.items() if v != dval]))
            stats["detail"] = (ddim, dval, de)
            ok = de >= th["detail_ratio"] * max(rest, 0.0) and de > ce * 0.98
            add("detail_steeper", ok,
                f'{cval} x {dval} is {de:+.1%}, steeper than the rest of {cval} ({rest:+.1%})' if ok else
                f'{cval} x {dval} is {de:+.1%} vs. {rest:+.1%} for the rest of {cval}: '
                f'the drill-down doesn\'t get worse')
        else:
            add("detail_steeper", False, f'"{dval}" has no history within {cval}')

    # ── Counter-trend metric ─────────────────────────────────────────────
    if counter_metric:
        mc = next((m for m in metric_config if m["label"] == counter_metric), None)
        ccol = _col(df, counter_metric)
        if mc is None or ccol is None:
            add("counter_trend", False, f'Counter-trend metric "{counter_metric}" not in the data')
        else:
            up_good = mc.get("sentiment", "up_is_good") == "up_is_good"
            e, z = _worsening(_monthly(df, df.index == df.index, ccol, mc.get("agg", "Average"), today),
                              onset, up_good, window)
            stats["counter_effect"] = e
            ok = e is not None and e <= -th["min_counter"]
            add("counter_trend", ok,
                f'{counter_metric} improves {-e:.1%} while {primary["label"]} worsens' if ok else
                f'{counter_metric} moved {0 if e is None else -e:+.1%} (needs an improvement of '
                f'>= {th["min_counter"]:.1%})')

    # ── Supporting metrics follow the culprit (warn only) ────────────────
    follow, miss = [], []
    for mc in metric_config:
        if mc is primary or mc["label"] == counter_metric:
            continue
        col = _col(df, mc["label"])
        if col is None:
            continue
        up_good = mc.get("sentiment", "up_is_good") == "up_is_good"
        agg = mc.get("agg", "Average")
        e_c, _ = _worsening(_monthly(df, df[dc] == cval, col, agg, today), onset, up_good, window)
        e_o, _ = _worsening(_monthly(df, df[dc] != cval, col, agg, today), onset, up_good, window)
        if e_c is None or e_o is None:
            continue
        (follow if e_c > max(e_o, 0.0) + 0.01 else miss).append(mc["label"])
    if follow or miss:
        add("supporting_follow", bool(follow) and len(follow) >= len(miss),
            f'{len(follow)} of {len(follow) + len(miss)} supporting metrics are worse in {cval} than elsewhere'
            + (f' (not: {", ".join(miss[:3])})' if miss else ""), "warn")

    return _finish(checks, stats)


def _finish(checks, stats):
    failures = [c for c in checks if not c["ok"] and c["severity"] == "fail"]
    warnings = [c for c in checks if not c["ok"] and c["severity"] == "warn"]
    return {"ok": not failures, "checks": checks, "failures": failures,
            "warnings": warnings, "stats": stats}


def format_report(report: dict) -> str:
    """One line per check: ✓ pass, ✗ failure, ! warning."""
    lines = []
    for c in report["checks"]:
        mark = "✓" if c["ok"] else ("✗" if c["severity"] == "fail" else "!")
        lines.append(f'{mark} {c["name"]}: {c["message"]}')
    lines.append("signal: PASS" if report["ok"] else "signal: FAIL")
    return "\n".join(lines)


def culprit_from_multipliers(multipliers: dict, dimensions: list[str],
                             compound_multipliers: dict | None = None,
                             compound_dims: tuple | None = None):
    """Derive (culprit, detail) from generate_demo_data's multiplier inputs, so
    /build-demo scripts can verify without a signal_plan. Culprit = the highest
    multiplier on the first dimension that has any; detail = the highest
    compound cell inside that culprit."""
    culprit = detail = None
    for dim in dimensions:
        mm = multipliers.get(dim)
        if mm:
            culprit = (dim, max(mm, key=mm.get))
            break
    if culprit and compound_multipliers and compound_dims:
        d1, d2 = compound_dims
        if d1 == culprit[0]:
            cells = {k: v for k, v in compound_multipliers.items() if k[0] == culprit[1]}
            if cells:
                detail = (d2, max(cells, key=cells.get)[1])
    return culprit, detail
