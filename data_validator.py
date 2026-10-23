"""
Data quality gates for AIO Analytics Builder.

Import and call these before and after data generation to ensure
dimension values are real company-specific terms, never generic placeholders.
"""

import re


GENERIC_PATTERN = re.compile(
    r'^[A-Za-z][A-Za-z_\s]+[_\s](\d+)$'
)


def _is_generic(value: str) -> bool:
    """True if the value looks like a placeholder (e.g. 'Service_Tier 1', 'Client_Segment 3')."""
    return bool(GENERIC_PATTERN.match(value.strip()))


def validate_dimension_values(dimension_values: dict, dimensions: list) -> list:
    """Pre-generation check: ensure DIMENSION_VALUES is populated with real values.

    Args:
        dimension_values: dict mapping dimension names to lists of values
        dimensions: list of dimension column names the build expects

    Returns:
        List of error strings. Empty = passed.
    """
    errors = []

    if not dimension_values:
        errors.append(
            "DIMENSION_VALUES is empty or missing. Every dimension must have "
            "real, company-specific values — never use generic placeholders. "
            "Research the company and define values like: "
            '{"Region": ["West Coast", "Northeast", ...], "Service Tier": ["PEO Essentials", "PEO Dedicated", ...]}'
        )
        return errors

    for dim in dimensions:
        matched_key = None
        for key in dimension_values:
            if key.lower().replace("_", " ").strip() == dim.lower().replace("_", " ").strip():
                matched_key = key
                break
        if not matched_key:
            errors.append(
                f'Dimension "{dim}" has no entry in DIMENSION_VALUES. '
                f"Add realistic values for this dimension."
            )
            continue

        vals = dimension_values[matched_key]
        if not vals or len(vals) < 2:
            errors.append(
                f'Dimension "{dim}" has fewer than 2 values — add more realistic options.'
            )
            continue

        generic_vals = [v for v in vals if _is_generic(str(v))]
        if generic_vals:
            errors.append(
                f'Dimension "{dim}" contains generic placeholder values: {generic_vals}. '
                f"Replace with real company-specific terms."
            )

    return errors


def validate_dataframe(df, dimensions: list) -> list:
    """Post-generation check: scan the DataFrame for generic dimension values.

    Args:
        df: pandas DataFrame with generated data
        dimensions: list of dimension column names to check

    Returns:
        List of error strings. Empty = passed.
    """
    errors = []

    for dim in dimensions:
        col = None
        for c in df.columns:
            if c.lower().replace("_", " ").strip() == dim.lower().replace("_", " ").strip():
                col = c
                break
        if col is None:
            continue

        unique_vals = df[col].dropna().unique()
        generic_vals = [str(v) for v in unique_vals if _is_generic(str(v))]
        generic_ratio = len(generic_vals) / max(len(unique_vals), 1)

        if generic_ratio > 0.5:
            errors.append(
                f'Column "{col}" has {len(generic_vals)}/{len(unique_vals)} generic values: '
                f"{generic_vals[:5]}. This data will look fake in the dashboard. "
                f"Define DIMENSION_VALUES with real company terms and regenerate."
            )

    return errors
