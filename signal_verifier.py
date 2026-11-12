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
the counter-trend metric doesn't improve, or the plan names something the data
can't show (report["fixable_by_redraw"] is then False). Warnings never fail a
build: no flat segment, a close runner-up, supporting metrics not following,
culprit beyond the realism cap, settings that design a story inside the noise.

Noise is measured from the data (the same recent-vs-baseline change taken at
earlier points before the onset), not assumed, so one z cutoff works for a
quiet and a noisy background.
"""
from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd

# Thresholds. Worsening is a fraction: 0.10 = 10% worse than baseline. Noise is
# measured on the data itself (see _noise_sd), so the same cutoffs hold for a
# flat background (variability 0) and a noisy one (1.5): a gentle story passes
# when the background is quiet and fails when it would be lost in the wander.
MIN_EFFECT = 0.03              # below this a change is too small to see, however clean
FALLBACK_MIN_EFFECT = 0.10     # strength cutoff when the noise can't be measured
MIN_Z = 2.5                    # culprit effect vs. the same measurement taken before onset
SIBLING_RATIO = 0.65           # median sibling worsening <= this x culprit's
RUNNER_UP_RATIO = 0.85         # next-worst segment <= this x culprit's (warn)
DETAIL_RATIO = 1.15            # drill-down cell >= this x the rest of the culprit
MIN_COUNTER_EFFECT = 0.03      # counter-trend metric must improve at least this much
MAX_EFFECT = 0.55              # beyond this the decline reads as implausible (warn)
BASELINE_MONTHS = 12
MIN_BASELINE_MONTHS = 6        # a noise window needs this many baseline months
MIN_NOISE_WINDOWS = 8          # pooled windows needed for a noise estimate


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


def _monthly(df: pd.DataFrame, mask, value_col: str) -> pd.Series:
    """Metric by months-ago for the rows in mask, as the mean per row. Every
    check is a ratio to the baseline, so the mean is right for Sum metrics too,
    and unlike a monthly sum it isn't thrown by a partial current month or by
    months with 4 vs. 5 weeks (daily and weekly grain)."""
    return df.loc[mask].groupby("_m")[value_col].mean().sort_index()


def _change(series: pd.Series, recent_months, base_start: int, min_base: int):
    rec = series[series.index.isin(recent_months)]
    base = series[(series.index >= base_start) & (series.index < base_start + BASELINE_MONTHS)]
    if len(rec) == 0 or len(base) < min_base or base.mean() == 0:
        return None
    return float(rec.mean() / base.mean() - 1.0)


def _worsening(series: pd.Series, onset: int, up_good: bool, window: int):
    """Recent change vs. the pre-onset baseline, signed so >0 = worse."""
    change = _change(series, range(window), onset, 3)
    if change is None:
        return None
    return -change if up_good else change


def _noise_sd(series_list, onset: int, window: int):
    """How much the worsening measure moves with no signal: the same recent-vs-
    baseline change, taken at every earlier position inside the pre-onset months
    and pooled over the series given (the segments of one dimension). Unlike
    month-to-month differences this keeps drift, AR(1) persistence and the
    season the window sits in, which are what make a quiet segment look worse.
    Root mean square around zero, so a shared drift counts as noise.
    Returns (sd, windows); sd is None with too little history before onset."""
    changes = []
    for s in series_list:
        last = int(s.index.max()) if len(s) else -1
        for shift in range(onset, last + 1):
            months = range(shift, shift + window)
            if not all(m in s.index for m in months):
                continue
            c = _change(s, months, shift + window, MIN_BASELINE_MONTHS)
            if c is not None:
                changes.append(c)
    if len(changes) < MIN_NOISE_WINDOWS:
        return None, len(changes)
    return float(np.sqrt(np.mean(np.square(changes)))), len(changes)


def expected_effect(magnitude: float, onset_months: int, *, shape: str = "accelerating",
                    duration: int | None = None, culprit_mult: float = 2.0,
                    worst_mult: float | None = None, up_is_good: bool = True,
                    bad_boost: float = 1.0, max_effect: float | None = None,
                    window: int | None = None) -> float:
    """The worsening the chosen signal settings should give the culprit over the
    verifier's recent window (same maths as the generators: scaled magnitude x
    ramp x multiplier, capped). `culprit_mult` is the culprit's average
    multiplier; `worst_mult` the largest one the generator scales the signal
    by (defaults to culprit_mult). `bad_boost` is the extra factor up_is_bad
    metrics get (2.0 in data_generator, 1.0 in the Web UI generator).
    `max_effect` is the most the value clamps allow (a rate can't pass 100%).
    verify_signal compares it to the measured noise and warns when the settings
    design a story inside it."""
    from data_generator import cap_signal, signal_scale
    onset = max(2, abs(int(onset_months)))
    window = window or min(3, onset)
    duration = duration or onset
    mag = magnitude * signal_scale(magnitude, [worst_mult or culprit_mult])
    vals = []
    for k in range(window):                       # k months before the latest month
        progress = max(0.0, min(1.0, (onset - k) / duration))
        ramp = progress ** 2 if shape == "accelerating" else (
            (1.0 if progress >= 0.3 else 0.0) if shape == "step" else progress)
        eff = mag * ramp * culprit_mult * (1.0 if up_is_good else bad_boost)
        eff = cap_signal(eff, worsens_upward=not up_is_good)
        vals.append(min(eff, max_effect) if max_effect is not None else eff)
    return float(np.mean(vals))


def _thresholds(noise_sd: float | None) -> dict:
    """Cutoffs for this build. Strength has a fixed floor (visible on a chart);
    the z cutoff is against the measured noise, so it is what adapts to a quiet
    or noisy background. Without a noise estimate the strength floor rises."""
    return {
        "noise_sd": None if noise_sd is None else round(noise_sd, 4),
        "min_effect": MIN_EFFECT if noise_sd is not None else FALLBACK_MIN_EFFECT,
        "min_z": MIN_Z,
        "sibling_ratio": SIBLING_RATIO,
        "runner_up_ratio": RUNNER_UP_RATIO,
        "detail_ratio": DETAIL_RATIO,
        "min_counter": MIN_COUNTER_EFFECT,
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
    signal_dims: list[str] | None = None,
) -> dict:
    """Check the DataFrame against the story's signal plan.

    `signal_plan` is the story's {culprit:{dimension,value}, culprit_detail:{...},
    counter_trend_metric}. Without one, pass `culprit`/`detail`/`counter_metric`
    directly (e.g. derived from generate_demo_data's multipliers); with neither,
    the worst segment of the first dimension is checked as the culprit.

    `signal_dims` are the dimensions the generator puts the signal on; a culprit
    named on any other dimension can't be met. `expected` (see expected_effect)
    is what the settings should produce: a warning says when it's inside the
    measured noise. The cutoffs used are in stats["thresholds"].

    Returns {"ok", "checks": [{name, ok, severity, message}], "failures",
    "warnings", "stats", "fixable_by_redraw"}. fixable_by_redraw is False when a
    failure comes from the plan or the settings (a value that isn't in the data,
    too little history), so another draw would miss the same way.
    """
    today = today or date.today()
    plan = signal_plan or {}
    df = df.copy()
    dcol = _col(df, date_col) or date_col
    df["_m"] = [_months_ago(d, today) for d in df[dcol]]
    onset = max(2, abs(int(onset_months)))
    window = min(3, onset)

    checks: list[dict] = []
    stats: dict = {"onset_months": onset, "window_months": window, "expected_effect": expected}

    def add(name, ok, message, severity="fail", redraw=True):
        checks.append({"name": name, "ok": bool(ok), "severity": severity, "message": message,
                       "redraw": redraw})

    if not metric_config or not dimensions:
        add("inputs", False, "No metrics or dimensions to verify", redraw=False)
        return _finish(checks, stats)

    primary = next((m for m in metric_config if m.get("is_primary")), metric_config[0])
    pcol = _col(df, primary["label"])
    if pcol is None:
        add("inputs", False, f'Primary metric column "{primary["label"]}" not in the data', redraw=False)
        return _finish(checks, stats)
    p_up_good = primary.get("sentiment", "up_is_good") == "up_is_good"

    # Resolve culprit / detail / counter-trend from args, then plan, then the data
    if culprit is None and plan.get("culprit"):
        c = plan["culprit"]
        culprit = (c.get("dimension"), c.get("value"))
    if detail is None and plan.get("culprit_detail"):
        c = plan["culprit_detail"]
        detail = (c.get("dimension"), c.get("value"))
    counter_metric = counter_metric or plan.get("counter_trend_metric")
    counter_mc = ccol = None
    if counter_metric:
        counter_mc = next((m for m in metric_config if m["label"] == counter_metric), None)
        ccol = _col(df, counter_metric)
        if counter_mc is None or ccol is None:
            add("counter_trend", False, f'Counter-trend metric "{counter_metric}" not in the data',
                redraw=False)
            counter_mc = None
        elif counter_mc is primary:
            add("counter_trend", False, f'Counter-trend metric "{counter_metric}" is the primary metric: '
                f'it can\'t worsen and improve at once', redraw=False)
            counter_mc = None

    def seg_series(dim):
        dc = _col(df, dim)
        return dc, {val: _monthly(df, df[dc] == val, pcol) for val in df[dc].dropna().unique()}

    # ── Overall: the problem must be visible ─────────────────────────────
    overall = _worsening(_monthly(df, slice(None), pcol), onset, p_up_good, window)
    stats["overall_worsening"] = overall
    if overall is not None:
        add("overall", overall > 0.0,
            f'{primary["label"]} is {overall:+.1%} {"worse" if overall > 0 else "better"} overall',
            "fail" if overall <= -0.02 else "warn")

    # ── Culprit segment ──────────────────────────────────────────────────
    cdim = culprit[0] if culprit and culprit[0] else dimensions[0]
    if _col(df, cdim) is None:
        add("culprit", False, f'Culprit dimension "{cdim}" is not a column in the data', redraw=False)
        return _finish(checks, stats)
    if signal_dims is not None and cdim not in signal_dims:
        add("culprit", False, f'Culprit dimension "{cdim}" isn\'t one the generator signals on '
            f'({", ".join(signal_dims) or "none"})', redraw=False)
        return _finish(checks, stats)
    dc, series = seg_series(cdim)
    eff = {v: e for v, s in series.items()
           if (e := _worsening(s, onset, p_up_good, window)) is not None}
    if len(eff) < 2:
        add("culprit", False, f'Not enough "{cdim}" segments with history before the onset to compare',
            redraw=False)
        return _finish(checks, stats)
    if culprit and culprit[1] and culprit[1] not in eff:
        stats["culprit"] = (cdim, culprit[1])
        add("culprit_exists", False, f'Culprit "{culprit[1]}" is not a value of {cdim} in the data',
            redraw=False)
        return _finish(checks, stats)

    sd, n_windows = _noise_sd(list(series.values()), onset, window)
    th = _thresholds(sd)
    stats.update({"thresholds": th, "noise_windows": n_windows})
    ranked = sorted(eff, key=eff.get, reverse=True)
    cval = culprit[1] if culprit and culprit[1] else ranked[0]
    ce = eff[cval]
    cz = ce / sd if sd else None
    stats.update({"culprit": (cdim, cval), "culprit_effect": ce, "culprit_z": cz,
                  "segments": {str(k): round(v, 4) for k, v in eff.items()}})

    add("culprit_worst", ranked[0] == cval,
        f'{cval} is the worst {cdim} ({ce:+.1%})' if ranked[0] == cval else
        f'{cval} is {ranked.index(cval) + 1} of {len(ranked)} on {cdim} ({ce:+.1%}); '
        f'{ranked[0]} is worst ({eff[ranked[0]]:+.1%}) — the walkthrough names the wrong segment')
    add("culprit_strength", ce >= th["min_effect"],
        f'{cval} is {ce:+.1%} vs. baseline (needs >= {th["min_effect"]:.1%}; too small to see)'
        if ce < th["min_effect"] else f'{cval} is {ce:+.1%} vs. baseline')
    if sd is None:
        add("culprit_signal_vs_noise", False,
            f'noise not measured: too little history before the onset (needs {MIN_BASELINE_MONTHS}+ '
            f'baseline months behind each earlier window)', "warn")
    else:
        add("culprit_signal_vs_noise", cz >= th["min_z"],
            f'z = {cz:.1f} against {sd:.1%} background noise (needs >= {th["min_z"]:.1f}; '
            f'lost in the noise)' if cz < th["min_z"] else f'z = {cz:.1f} against {sd:.1%} background noise')
        if expected is not None and expected < th["min_z"] * sd:
            add("designed_vs_noise", False,
                f'the settings design a {expected:.0%} decline, inside the {sd:.1%} background noise: '
                f'raise the magnitude or lower variability', "warn")
    if ce > MAX_EFFECT:
        add("culprit_plausible", False,
            f'{cval} is {ce:+.0%}, beyond {MAX_EFFECT:.0%}: reads as implausible', "warn")

    sibs = {v: e for v, e in eff.items() if v != cval}
    med = float(np.median(list(sibs.values())))
    stats["sibling_median"] = med
    add("siblings_local", med <= th["sibling_ratio"] * ce,
        f'other {cdim} values move {med:+.1%} (median) vs. {ce:+.1%} for {cval}'
        if med <= th["sibling_ratio"] * ce else
        f'other {cdim} values move {med:+.1%} (median), nearly as much as {cval} ({ce:+.1%}): '
        f'filtering reveals nothing')
    runner = max(sibs, key=sibs.get)
    if ranked[0] == cval and sibs[runner] > th["runner_up_ratio"] * ce:
        add("culprit_margin", False,
            f'{runner} ({sibs[runner]:+.1%}) is close behind {cval} ({ce:+.1%}): '
            f'"where is it worst?" has two answers', "warn")
    flat = [str(v) for v, e in sibs.items() if e <= 0.25 * ce]
    add("has_flat_segment", bool(flat),
        f'flat/improving {cdim}: {", ".join(flat[:3])}' if flat else
        f'no {cdim} value is flat — add one segment near 0 so the average hides the story',
        "warn")

    # ── Drill-down cell ──────────────────────────────────────────────────
    if detail and detail[0] and detail[1]:
        ddim, dval = detail
        ddc = _col(df, ddim)
        if ddc is None or ddim == cdim:
            add("detail_steeper", False,
                f'Drill-down dimension "{ddim}" ' + ("is the culprit's own dimension"
                                                     if ddim == cdim else "is not a column in the data"),
                redraw=False)
        elif dval not in set(df[ddc].dropna().unique()):
            add("detail_steeper", False, f'Drill-down "{dval}" is not a value of {ddim} in the data',
                redraw=False)
        else:
            in_c = df[dc] == cval
            deff = {v: e for v in df.loc[in_c, ddc].dropna().unique()
                    if (e := _worsening(_monthly(df, in_c & (df[ddc] == v), pcol),
                                        onset, p_up_good, window)) is not None}
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
    if counter_mc is not None:
        up_good = counter_mc.get("sentiment", "up_is_good") == "up_is_good"
        e = _worsening(_monthly(df, slice(None), ccol), onset, up_good, window)
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
        e_c = _worsening(_monthly(df, df[dc] == cval, col), onset, up_good, window)
        e_o = _worsening(_monthly(df, df[dc] != cval, col), onset, up_good, window)
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
            "warnings": warnings, "stats": stats,
            "fixable_by_redraw": all(c["redraw"] for c in failures)}


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
    /build-demo scripts can verify without a signal_plan. The culprit is on the
    compound table's first dimension when there is one (that table is the
    story's drill path), otherwise on the dimension holding the largest
    multiplier; its value is that dimension's highest multiplier (or highest
    average compound cell). Detail = the highest compound cell inside it."""
    culprit = detail = None
    d1 = d2 = None
    if compound_multipliers and compound_dims:
        d1, d2 = compound_dims
    if d1 and multipliers.get(d1):
        mm = multipliers[d1]
        culprit = (d1, max(mm, key=mm.get))
    elif d1:
        by_v1: dict = {}
        for (v1, _v2), m in compound_multipliers.items():
            by_v1.setdefault(v1, []).append(m)
        if by_v1:
            culprit = (d1, max(by_v1, key=lambda v: np.mean(by_v1[v])))
    if culprit is None:
        ranked = [(m, dim, v) for dim in dimensions for v, m in (multipliers.get(dim) or {}).items()]
        if ranked:
            _m, dim, v = max(ranked, key=lambda t: t[0])
            culprit = (dim, v)
    if culprit and d1 == culprit[0]:
        cells = {k: v for k, v in compound_multipliers.items() if k[0] == culprit[1]}
        if cells:
            detail = (d2, max(cells, key=cells.get)[1])
    return culprit, detail
