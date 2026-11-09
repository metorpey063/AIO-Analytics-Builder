"""
Reusable data generation module for AIO Analytics Builder.

Generates synthetic demo data with engineered signals. Config in, DataFrame out.
Validation is built in — generic dimension values are rejected before generation.

Usage:
    from data_generator import generate_demo_data

    df = generate_demo_data(
        metrics=METRIC_CONFIG,
        dimensions=["Region", "Client Segment", "Tenure Band", "Service Tier"],
        dimension_values={"Region": ["West Coast", "Northeast", ...], ...},
        signal_config={"magnitude": 0.37, "onset": -6, "shape": "accelerating"},
        multipliers={"Region": {"West Coast": 1.8, "Northeast": 0.4, ...}, ...},
    )
"""

import random
from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd

from data_validator import validate_dimension_values


# ── Signal ramp ──────────────────────────────────────────────────────────────

def signal_ramp(d: date, today: date, onset: int = -6, shape: str = "accelerating",
                duration: int = 6) -> float:
    """Compute signal strength at date d.

    Args:
        d: the row date
        today: reference date (build date)
        onset: months before today when signal starts (negative int)
        shape: "accelerating" (quadratic), "ramp" (linear), "step"
        duration: months from onset to full magnitude
    """
    months_from_today = (d.year - today.year) * 12 + (d.month - today.month)
    months_from_onset = months_from_today - onset
    if months_from_onset <= 0:
        return 0.0
    progress = min(1.0, months_from_onset / duration)
    if shape == "accelerating":
        return progress ** 2
    if shape == "step":
        return 1.0 if progress >= 0.3 else 0.0
    return progress


# ── Realism layers ───────────────────────────────────────────────────────────

# The worst segment's designed change never exceeds this share of its base
# value: 0.40 magnitude × a 2.5× culprit multiplier is a 100% drop otherwise.
MAX_DECLINE = 0.45
MAX_INCREASE = 0.60


def signal_scale(magnitude: float, multipliers) -> float:
    """Factor (≤ 1) for the signal magnitude so the worst segment's full
    effect is MAX_DECLINE. Scaling every segment by the same factor keeps the
    designed ratios (culprit vs moderate vs flat); clamping each segment
    instead would squash the culprit and the moderate segment together.
    """
    worst = max([m for m in multipliers if m > 0] or [1.0])
    return min(1.0, MAX_DECLINE / (magnitude * worst)) if magnitude > 0 else 1.0


def cap_signal(effect: float, worsens_upward: bool = False) -> float:
    """Safety clamp on a signal effect (magnitude × ramp × multiplier) —
    use signal_scale() first so this rarely binds."""
    return max(-0.15, min(MAX_INCREASE if worsens_upward else MAX_DECLINE, effect))


# Size-type dimension values: money/volume metrics should rank with company
# size (Enterprise deals > SMB deals), not randomly. Matched case-insensitively.
_SIZE_RANKS = [
    (("global", "strategic", "enterprise", "large", "tier 1", "key account", "premium"), 1.0),
    (("mid", "medium", "commercial", "corporate", "tier 2", "standard"), 0.0),
    (("small", "smb", "micro", "startup", "tier 3", "basic", "emerging"), -1.0),
]


def _size_rank(value: str):
    v = str(value).lower()
    for words, rank in _SIZE_RANKS:
        if any(w in v for w in words):
            return rank
    return None


class Realism:
    """Background variation so demo data doesn't look generated.

    Without it every segment averages to the middle of base_range, per-row
    noise cancels out once Tableau averages hundreds of rows, and trend lines
    sit dead flat until the signal starts. This adds, per metric:

    - segment levels: each value of each dimension gets its own level, so
      bars differ (Enterprise deal size above SMB), largest on the first dims
    - seasonality: a gentle yearly cycle, same phase for every segment
    - drift + shocks: each dimension-0 segment wanders month to month
      (AR(1)), plus a shared monthly shock — both survive aggregation
    - row noise relative to the value, not a fixed ±0.02

    All of it is multiplicative and centered on 1.0, and applied to the base
    BEFORE the signal, so the designed story (who declines, by how much,
    starting when) is unchanged. `strength` scales everything (0 = off).
    `neutral` is a set of (dimension, value) pairs that start exactly at the
    average level — the story's named culprit and drill-down segments, so the
    decline leaves them clearly lowest instead of a segment that merely
    started lower (Mid-Market at 15.7% vs the declining Enterprise at 17.3%).
    """

    def __init__(self, metrics, dimensions, dimension_values, dates, *,
                 seed: int = 42, strength: float = 1.0, neutral=()):
        rng = np.random.RandomState(seed)
        self.strength = strength
        self.dims = list(dimensions)
        self.date_index = {d: i for i, d in enumerate(dates)}
        n = len(dates)
        self.levels, self.season, self.paths, self.row_sd = {}, {}, {}, {}
        for mc in metrics:
            f = mc["field"]
            lo, hi = (mc.get("base_range") or [0.55, 0.85])[:2]
            is_rate = 0 <= lo and hi <= 1.0
            spread = (0.10 if is_rate else 0.22) * strength
            # Segment levels: dims 0-1 get the full spread, later dims less
            for di, dim in enumerate(self.dims):
                vals = dimension_values.get(dim, [])
                if not vals:
                    continue
                s = spread * (1.0 if di < 2 else 0.5)
                raw = 1 + rng.uniform(-s, s, len(vals))
                ranks = [_size_rank(v) for v in vals]
                if not is_rate and sum(r is not None for r in ranks) >= 2:
                    # Size dimension on a money/volume metric: order by size, with jitter
                    raw = np.array([1 + (r if r is not None else 0) * s * 1.5 + rng.uniform(-s, s) * 0.3
                                    for r in ranks])
                raw = raw / raw.mean()  # keep the overall average on base_range
                for v, lv in zip(vals, raw):
                    self.levels[(f, dim, v)] = 1.0 if (dim, v) in neutral else float(lv)
            # Seasonality: yearly sine, random phase per metric
            amp = rng.uniform(0.02, 0.04) * strength
            phase = rng.uniform(0, 12)
            self.season[f] = (amp, phase)
            # Drift + AR(1) shocks per dimension-0 segment, plus a shared shock
            shared = self._ar1(rng, n, 0.015 * strength)
            seg_vals = dimension_values.get(self.dims[0], []) if self.dims else []
            for v in seg_vals or [None]:
                slope = rng.uniform(-0.04, 0.04) * strength
                drift = slope * (np.linspace(-1, 1, n) if n > 1 else np.zeros(n))
                self.paths[(f, v)] = 1 + drift + self._ar1(rng, n, 0.03 * strength) + shared
            self.row_sd[f] = (0.05 if is_rate else 0.08) * strength

    @staticmethod
    def _ar1(rng, n, sd, phi=0.6):
        e = np.zeros(n)
        for t in range(n):
            e[t] = (phi * e[t - 1] if t else 0) + rng.normal(0, sd)
        return e

    def factor(self, field: str, row_dims: dict, d) -> float:
        """Multiplicative background factor for one metric on one row/date."""
        if not self.strength:
            return 1.0
        f = 1.0
        for dim in self.dims:
            f *= self.levels.get((field, dim, row_dims.get(dim)), 1.0)
        amp, phase = self.season.get(field, (0, 0))
        f *= 1 + amp * np.sin(2 * np.pi * (d.month + phase) / 12)
        t = self.date_index.get(d)
        seg = row_dims.get(self.dims[0]) if self.dims else None
        path = self.paths.get((field, seg)) if (field, seg) in self.paths else self.paths.get((field, None))
        if path is not None and t is not None:
            f *= max(0.5, float(path[t]))
        return f

    def row_noise(self, field: str, value: float, rng=None) -> float:
        """Random row-level noise, proportional to the value."""
        sd = self.row_sd.get(field, 0.0) * abs(value)
        return float((rng or np.random).normal(0, sd)) if sd else 0.0


# ── Noise scaling ────────────────────────────────────────────────────────────

DEFAULT_NOISE_SCALE = 0.015

def _noise_for_entity(entity: dict, noise_dim: str | None, noise_map: dict) -> float:
    if noise_dim and noise_dim in entity:
        return noise_map.get(entity[noise_dim], DEFAULT_NOISE_SCALE)
    return DEFAULT_NOISE_SCALE


# ── Core generator ───────────────────────────────────────────────────────────

def generate_demo_data(
    *,
    metrics: list[dict],
    dimensions: list[str],
    dimension_values: dict[str, list[str]],
    signal_config: dict | None = None,
    multipliers: dict[str, dict[str, float]] | None = None,
    compound_multipliers: dict[tuple[str, str], float] | None = None,
    compound_dims: tuple[str, str] | None = None,
    noise_dim: str | None = None,
    noise_map: dict[str, float] | None = None,
    history_months: int = 24,
    grain: str = "monthly",
    clients_per_cell: int = 2,
    roster_dims: list[str] | None = None,
    random_dims: list[str] | None = None,
    entity_prefix: str = "E",
    seed: int = 42,
    today: date | None = None,
    goal_columns: dict[str, float] | None = None,
    variability: float = 1.0,
) -> pd.DataFrame:
    """Generate synthetic demo data with engineered signals.

    Args:
        metrics: list of METRIC_CONFIG dicts. Each must have: label, field, sentiment, base_range.
                 First metric with is_primary=True (or index 0) is the primary signal carrier.
        dimensions: ordered list of dimension column names.
        dimension_values: dict mapping each dimension name to its list of real values.
                          REQUIRED — generic values are rejected.
        signal_config: {"magnitude": 0.37, "onset": -6, "shape": "accelerating",
                        "duration": 6, "supporting_magnitude": 0.12}
        multipliers: per-dimension multiplier maps.
                     e.g. {"Region": {"West Coast": 1.8, "Northeast": 0.4}}
                     Dimensions not in this dict get uniform multiplier 1.0.
        compound_multipliers: 2D multiplier table keyed on (dim1_val, dim2_val) tuples.
                              Only applied to the primary culprit segment.
        compound_dims: tuple of (dim1_name, dim2_name) for compound multipliers.
        noise_dim: dimension name to key noise scaling on (e.g. "Client Segment").
        noise_map: {dim_value: noise_scale} for the noise_dim.
        history_months: how many months of data.
        grain: "daily", "weekly", or "monthly".
        clients_per_cell: entities per cross-product cell of roster_dims.
        roster_dims: which dimensions form the cross-product roster.
                     Defaults to all dimensions with ≤8 values (to keep roster manageable).
        random_dims: dimensions assigned randomly per entity (not part of cross-product).
        entity_prefix: prefix for entity IDs.
        seed: random seed for reproducibility.
        today: reference date. Defaults to date.today().
        goal_columns: optional {column_label: constant_value} for goal/threshold columns.
        variability: strength of the background realism (segment levels,
                     seasonality, drift, shocks — see Realism). 1.0 default,
                     0 = flat background (signal only), 1.5 = noisier.

    Returns:
        DataFrame with columns: Record ID, Date, Entity ID, [dimensions...],
        [metrics...], Day_Offset, [goal columns...]
    """
    today = today or date.today()
    random.seed(seed)
    np.random.seed(seed)

    # ── Validate ─────────────────────────────────────────────────────────
    errors = validate_dimension_values(dimension_values, dimensions)
    if errors:
        msg = "Data generation blocked — dimension values failed validation:\n"
        msg += "\n".join(f"  - {e}" for e in errors)
        raise ValueError(msg)

    # ── Normalize metric field names ────────────────────────────────────
    # Column names come from mc["label"]. The DLO field name is
    # clean_field_name(label). mc["field"] MUST match that, otherwise
    # the SDM measurement_map lookup fails. Auto-fix any mismatches.
    import re as _re
    def _clean(name):
        c = _re.sub(r'[^a-z0-9_]', '_', name.lower().strip())
        c = _re.sub(r'_+', '_', c).strip('_')
        if c and c[0].isdigit(): c = "X" + c
        return c[:40]

    for mc in metrics:
        expected = _clean(mc["label"])
        if mc.get("field") != expected:
            mc["field"] = expected

    # ── Signal config defaults ───────────────────────────────────────────
    sc = signal_config or {}
    sig_magnitude = sc.get("magnitude", 0.37)
    sig_onset = sc.get("onset", -6)
    sig_shape = sc.get("shape", "accelerating")
    sig_duration = sc.get("duration", 6)
    sup_magnitude = sc.get("supporting_magnitude", 0.12)

    multipliers = multipliers or {}
    noise_map = noise_map or {}

    # ── Identify primary vs supporting metrics ───────────────────────────
    primary_idx = next((i for i, m in enumerate(metrics) if m.get("is_primary")), 0)
    primary_mc = metrics[primary_idx]

    # ── Build entity roster ──────────────────────────────────────────────
    # Determine which dims are cross-product (roster) and which are random
    if roster_dims is None:
        roster_dims = [d for d in dimensions if len(dimension_values.get(d, [])) <= 8]
    if random_dims is None:
        random_dims = [d for d in dimensions if d not in roster_dims]

    def _cross_product(dims_list, idx=0):
        if idx >= len(dims_list):
            return [{}]
        dim = dims_list[idx]
        vals = dimension_values.get(dim, [dim])
        rest = _cross_product(dims_list, idx + 1)
        return [{dim: v, **r} for v in vals for r in rest]

    cells = _cross_product(roster_dims)
    entities = []
    eid = 0
    for cell in cells:
        for _ in range(clients_per_cell):
            eid += 1
            entity = {
                "entity_id": f"{entity_prefix}-{eid:04d}",
                **cell,
            }
            for rd in random_dims:
                entity[rd] = random.choice(dimension_values.get(rd, [rd]))
            # Per-entity base values for each metric
            for mc in metrics:
                lo, hi = mc.get("base_range", [0.55, 0.85])
                entity[f"_base_{mc['field']}"] = random.uniform(lo, hi)
            entities.append(entity)

    # ── Date range ───────────────────────────────────────────────────────
    freq = {"daily": "D", "weekly": "W", "monthly": "MS"}.get(grain, "MS")
    periods = {"daily": history_months * 30, "weekly": history_months * 4,
               "monthly": history_months}.get(grain, history_months)
    start = today.replace(day=1) - timedelta(days=history_months * 30)
    dates = pd.date_range(start, periods=periods, freq=freq).date
    realism = Realism(metrics, dimensions, dimension_values, list(dates),
                      seed=seed, strength=variability)

    # Scale the primary signal so the worst segment drops at most MAX_DECLINE
    # (segment multipliers only — extreme 2D drill cells are held by cap_signal)
    all_mults = [m for mm in multipliers.values() for m in mm.values()]
    sig_magnitude *= signal_scale(sig_magnitude, all_mults)

    # ── Generate rows ────────────────────────────────────────────────────
    rows = []
    for entity in entities:
        # Compute combined multiplier for this entity
        dim_mults = []
        for dim_name, mult_map in multipliers.items():
            val = entity.get(dim_name)
            if val and val in mult_map:
                dim_mults.append(mult_map[val])
        if dim_mults:
            combined_mult = sum(dim_mults) / len(dim_mults)
        else:
            combined_mult = 1.0

        # Compound multiplier override (2D table)
        if compound_multipliers and compound_dims:
            d1, d2 = compound_dims
            key = (entity.get(d1, ""), entity.get(d2, ""))
            if key in compound_multipliers:
                combined_mult = compound_multipliers[key]

        ns = _noise_for_entity(entity, noise_dim, noise_map)

        for d in dates:
            ramp = signal_ramp(d, today, sig_onset, sig_shape, sig_duration)
            p_ramp = ramp * combined_mult
            s_ramp = ramp * combined_mult * 0.7
            day_offset = (d - today).days

            row = {
                "Record ID": f"{entity['entity_id']}_{d.strftime('%Y%m%d')}",
                "Date": d.isoformat(),
                "Entity ID": entity["entity_id"],
                "Day_Offset": day_offset,
            }

            # Dimension columns
            for dim in dimensions:
                row[dim] = entity.get(dim, "")

            # Metric columns
            row_dims = {dim: entity.get(dim) for dim in dimensions}
            for i, mc in enumerate(metrics):
                # Background realism first, then the designed signal on top
                base = entity[f"_base_{mc['field']}"] * realism.factor(mc["field"], row_dims, d)
                is_primary = (i == primary_idx)
                up_good = mc.get("sentiment", "up_is_good") == "up_is_good"

                if is_primary:
                    eff_ramp = p_ramp
                    mag = sig_magnitude
                else:
                    eff_ramp = s_ramp
                    mag = sup_magnitude
                    if is_primary:
                        pass
                    else:
                        # Supporting metrics lag — use s_ramp * 0.5 for headcount-type metrics
                        eff_ramp = s_ramp

                noise = realism.row_noise(mc["field"], base) + np.random.normal(0, ns * abs(base))
                if up_good:
                    # Signal pushes value DOWN (decline)
                    value = base * (1 - cap_signal(mag * eff_ramp)) + noise
                else:
                    # Signal pushes value UP (increase = bad)
                    value = base * (1 + cap_signal(mag * eff_ramp * 2.0, worsens_upward=True)) + noise

                # Clamp to reasonable bounds
                lo, hi = mc.get("base_range", [0.0, 1.0])
                if hi <= 1.5:
                    value = max(0.01, min(1.0, value))
                else:
                    value = max(0.01, value)

                row[mc["label"]] = round(value, 4) if hi <= 1.5 else round(value, 2)

            # Goal columns
            if goal_columns:
                for col_label, val in goal_columns.items():
                    row[col_label] = val

            rows.append(row)

    df = pd.DataFrame(rows)

    # ── Post-generation validation ───────────────────────────────────────
    from data_validator import validate_dataframe
    errors = validate_dataframe(df, dimensions)
    if errors:
        msg = "Generated data failed validation:\n"
        msg += "\n".join(f"  - {e}" for e in errors)
        raise ValueError(msg)

    return df
