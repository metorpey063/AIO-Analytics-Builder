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
            for i, mc in enumerate(metrics):
                base = entity[f"_base_{mc['field']}"]
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

                if up_good:
                    # Signal pushes value DOWN (decline)
                    value = base * (1 - mag * eff_ramp) + np.random.normal(0, ns)
                else:
                    # Signal pushes value UP (increase = bad)
                    value = base * (1 + mag * eff_ramp * 2.0) + np.random.normal(0, ns * abs(base))

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
