#!/usr/bin/env python3
"""Dashboard Composer Runner — bridge between dashboard_composer and the Tableau Next API.

Reads a checkpoint from a completed demo build, runs the story-driven
dashboard composer, creates real visualizations via viz_builder, and
assembles a dashboard via the REST API.

Usage:
    python compose_dashboard_runner.py --slug meridian
    python compose_dashboard_runner.py --slug meridian --demo-dir demos/meridian
    python compose_dashboard_runner.py --slug meridian --max-vizzes 4 --skip-metrics
"""

import argparse
import json
import os
import re
import sys
import uuid
import time
import requests
from datetime import datetime

# ── Project imports ────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from connections import get_sf_token, sf_headers, load_config
from dashboard_composer import (
    compose_dashboard,
    plan_to_build_specs,
    plan_to_grid_layout,
    DashboardPlan,
)
from viz_builder import build_viz_payload


# ── Helpers ────────────────────────────────────────────────────────────────────

def _clean_field_name(label: str) -> str:
    """Convert a dimension label or field name to the snake_case key used in
    dim_field_map / measurement_map.  e.g. 'Service Line' -> 'service_line'."""
    clean = label.lower().strip()
    for ch in " -/()&":
        clean = clean.replace(ch, "_")
    while "__" in clean:
        clean = clean.replace("__", "_")
    clean = clean.strip("_")
    return clean


def load_checkpoint(demo_dir: str, slug: str) -> dict:
    """Load and validate the checkpoint JSON."""
    cp_path = os.path.join(demo_dir, f"{slug}_checkpoint.json")
    if not os.path.exists(cp_path):
        print(f"  ERROR: Checkpoint not found at {cp_path}")
        sys.exit(1)
    with open(cp_path) as f:
        cp = json.load(f)

    # Validate required keys
    required = ["ws_api", "sdm_api", "do_api"]
    missing = [k for k in required if not cp.get(k)]
    if missing:
        print(f"  ERROR: Checkpoint missing required keys: {missing}")
        print(f"  Run /build-demo first to create the SDM and workspace.")
        sys.exit(1)

    return cp


def save_checkpoint(cp: dict, demo_dir: str, slug: str):
    cp_path = os.path.join(demo_dir, f"{slug}_checkpoint.json")
    with open(cp_path, "w") as f:
        json.dump(cp, f, indent=2)


def fetch_field_maps(sf_token: str, sf_instance: str, sdm_api: str, do_api: str):
    """Fetch dim_field_map and measurement_map from the SDM API if not in checkpoint."""
    h = sf_headers(sf_token)
    url = f"{sf_instance}/services/data/v65.0/ssot/semantic/models/{sdm_api}/data-objects/{do_api}"
    r = requests.get(url, headers=h)
    r.raise_for_status()
    do_data = r.json()

    dim_map = {}
    for dim in do_data.get("semanticDimensions", []):
        base = dim.get("dataObjectFieldName", "").replace("__c", "")
        api = dim.get("apiName", "")
        if base and api:
            dim_map[base] = api

    meas_map = {}
    for meas in do_data.get("semanticMeasurements", []):
        base = meas.get("dataObjectFieldName", "").replace("__c", "")
        api = meas.get("apiName", "")
        if base and api:
            meas_map[base] = api

    return dim_map, meas_map


def _build_metric_field_bridge(metric_configs: list, measurement_map: dict) -> dict:
    """Build a lookup from metric_config 'field' names to measurement_map keys.

    Metric configs use short field names (e.g. 'readmission_rate_30d') while
    measurement_map uses DC schema field names (e.g. 'X30day_readmission_rate').
    This function bridges the gap using the metric label as an intermediary and
    falling back to fuzzy substring matching.

    Returns: {metric_config_field: measurement_map_key}
    """
    bridge = {}
    mm_keys = list(measurement_map.keys())
    mm_keys_lower = {k.lower(): k for k in mm_keys}

    for mc in metric_configs:
        field = mc.get("field", "")
        label = mc.get("label", "")
        clean_field = _clean_field_name(field)

        # Already in measurement_map? No bridge needed.
        if clean_field in measurement_map or field in measurement_map:
            continue

        # Strategy 1: Clean the label the same way DC cleans CSV column names.
        # DC removes special chars, replaces spaces/hyphens with underscores,
        # and prepends X for digit-leading names.
        label_clean = _clean_field_name(label)
        if label_clean and label_clean[0].isdigit():
            label_clean = "X" + label_clean
        if label_clean in measurement_map:
            bridge[clean_field] = label_clean
            bridge[field] = label_clean
            continue

        # Strategy 2: Normalized substring matching on both field and label.
        # Strips non-alpha chars so '30day_readmission_rate' matches
        # 'readmission_rate_30d' or '30_day_readmission_rate'.
        def _alpha_normalize(s):
            """Strip to lowercase alpha only for substring comparison."""
            return re.sub(r'[^a-z]', '', s.lower())

        label_norm = _alpha_normalize(label)
        field_norm = _alpha_normalize(clean_field)

        best_match = None
        best_len = 0  # prefer longest key (most specific match)
        for mk in mm_keys:
            mk_norm = _alpha_normalize(mk)
            # Check if the label or field is substantially contained in the key
            # or vice versa. Use the longer overlap as the score.
            if (label_norm in mk_norm or mk_norm in label_norm or
                    field_norm in mk_norm or mk_norm in field_norm):
                if len(mk) > best_len:
                    best_len = len(mk)
                    best_match = mk
        if best_match:
            bridge[clean_field] = best_match
            bridge[field] = best_match
            continue

        # Strategy 3: Token-based fuzzy matching with split number-word compounds.
        # Splits '30day' -> '30', 'day' for better token matching.
        def _split_tokens(s):
            tokens = set(s.lower().replace("_", " ").split())
            expanded = set()
            for t in tokens:
                t = t.lstrip("x") if len(t) > 1 else t
                # Split number-word compounds: '30day' -> '30', 'day'
                parts = re.findall(r'[a-z]+|\d+', t)
                expanded.update(parts)
            return {t for t in expanded if not t.isdigit()}

        field_tokens = _split_tokens(clean_field)
        label_tokens = _split_tokens(_clean_field_name(label))
        combined_tokens = field_tokens | label_tokens

        best_match = None
        best_score = 0.0
        for mk in mm_keys:
            mk_tokens = _split_tokens(mk)
            overlap = len(combined_tokens & mk_tokens)
            if overlap < 2:
                continue
            union_size = len(combined_tokens | mk_tokens)
            score = overlap / union_size if union_size else 0
            if score > best_score:
                best_score = score
                best_match = mk
        if best_match and best_score > 0:
            bridge[clean_field] = best_match
            bridge[field] = best_match

    return bridge


def resolve_field(raw_name: str, dim_field_map: dict, measurement_map: dict,
                  display_date_api: str = None,
                  metric_field_bridge: dict = None) -> str:
    """Resolve a raw field name (from METRIC_CONFIG or DIMENSIONS) to an SDM apiName.

    Tries multiple lookup strategies:
      1. Special 'date' handling via display_date_api
      2. Exact match in measurement_map (for DC schema field names)
      3. metric_field_bridge lookup (metric_config field -> DC schema field)
      4. Exact match in dim_field_map (for dimension names)
      5. Cleaned version (label -> snake_case) in dim_field_map
      6. Case-insensitive fuzzy match on both maps
      7. Fallback: return raw_name + '1' (common SDM auto-suffix pattern)
    """
    clean = _clean_field_name(raw_name)
    metric_field_bridge = metric_field_bridge or {}

    # Special case: date field
    if clean == "date":
        if display_date_api:
            return display_date_api
        if "date" in dim_field_map:
            return dim_field_map["date"]
        return "date1"

    # Try measurement map first (metric fields)
    if clean in measurement_map:
        return measurement_map[clean]
    if raw_name in measurement_map:
        return measurement_map[raw_name]

    # Try the metric field bridge (maps short field names to DC schema names)
    bridged_key = metric_field_bridge.get(clean) or metric_field_bridge.get(raw_name)
    if bridged_key and bridged_key in measurement_map:
        return measurement_map[bridged_key]

    # Try dim_field_map
    if clean in dim_field_map:
        return dim_field_map[clean]
    if raw_name in dim_field_map:
        return dim_field_map[raw_name]

    # Case-insensitive fallback on both maps
    clean_lower = clean.lower()
    for k, v in dim_field_map.items():
        if k.lower() == clean_lower:
            return v
    for k, v in measurement_map.items():
        if k.lower() == clean_lower:
            return v

    # Substring containment: if the cleaned field name is contained in a
    # measurement_map key (or vice versa), use it.
    for k, v in measurement_map.items():
        if clean_lower in k.lower() or k.lower() in clean_lower:
            return v

    # Last resort: append '1' (common SDM auto-suffix)
    print(f"    WARNING: Could not resolve field '{raw_name}' (clean: '{clean}') — using fallback '{clean}1'")
    return f"{clean}1"


def resolve_spec_field_map(spec_field_map: dict, dim_field_map: dict,
                           measurement_map: dict, display_date_api: str = None,
                           metric_field_bridge: dict = None) -> dict:
    """Resolve all fields in a build spec's field_map to SDM apiNames.

    Returns a dict with the same keys but resolved values.
    """
    resolved = {}
    for slot, raw_name in spec_field_map.items():
        if not raw_name:
            continue
        resolved[slot] = resolve_field(
            raw_name, dim_field_map, measurement_map,
            display_date_api, metric_field_bridge
        )
    return resolved


def create_viz(sf_token: str, sf_instance: str, payload: dict) -> str | None:
    """POST a visualization and return the created apiName, or None on failure."""
    h = sf_headers(sf_token)
    url = f"{sf_instance}/services/data/v66.0/tableau/visualizations"
    r = requests.post(url, headers=h, params={"minorVersion": "12"}, json=payload)
    if r.status_code in (200, 201):
        name = r.json().get("name", payload.get("name"))
        return name
    print(f"    ERROR creating viz '{payload.get('label', '?')}': {r.status_code}")
    try:
        print(f"    {r.text[:400]}")
    except Exception:
        pass
    return None


def delete_viz(sf_token: str, sf_instance: str, viz_api: str):
    """Delete a visualization (cleanup)."""
    h = sf_headers(sf_token)
    url = f"{sf_instance}/services/data/v66.0/tableau/visualizations/{viz_api}"
    requests.delete(url, headers=h, params={"minorVersion": "12"})


def delete_dashboard(sf_token: str, sf_instance: str, dash_api: str):
    """Delete a dashboard (cleanup)."""
    h = sf_headers(sf_token)
    url = f"{sf_instance}/services/data/v66.0/tableau/dashboards/{dash_api}"
    requests.delete(url, headers=h)


def create_dashboard(sf_token: str, sf_instance: str, payload: dict) -> str | None:
    """POST a dashboard and return the created apiName, or None on failure."""
    h = sf_headers(sf_token)
    url = f"{sf_instance}/services/data/v66.0/tableau/dashboards"
    r = requests.post(url, headers=h, params={"minorVersion": "12"}, json=payload)
    if r.status_code in (200, 201):
        name = r.json().get("name", payload.get("name"))
        return name
    print(f"    ERROR creating dashboard: {r.status_code}")
    try:
        print(f"    {r.text[:500]}")
    except Exception:
        pass
    return None


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Dashboard Composer Runner")
    parser.add_argument("--slug", required=True, help="Demo slug (e.g. 'meridian')")
    parser.add_argument("--demo-dir", default=None,
                        help="Demo directory (default: demos/{slug})")
    parser.add_argument("--max-vizzes", type=int, default=5,
                        help="Maximum number of visualizations to create (default: 5)")
    parser.add_argument("--max-kpi-metrics", type=int, default=4,
                        help="Maximum KPI metric tiles (default: 4)")
    parser.add_argument("--skip-metrics", action="store_true",
                        help="Skip metric widgets in the dashboard")
    parser.add_argument("--signal-direction", default="down", choices=["up", "down"],
                        help="Direction of the demo signal (default: down)")
    parser.add_argument("--signal-months", type=int, default=6,
                        help="Number of months the signal has been active (default: 6)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview only — don't create anything on the org")
    parser.add_argument("--cleanup-first", action="store_true",
                        help="Delete existing composed vizzes/dashboard before creating new ones")
    args = parser.parse_args()

    demo_dir = args.demo_dir or os.path.join(ROOT, "demos", args.slug)
    if not os.path.isdir(demo_dir):
        print(f"  ERROR: Demo directory not found: {demo_dir}")
        sys.exit(1)

    # ── Step 1: Load checkpoint ───────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print(f"  Dashboard Composer Runner — {args.slug}")
    print(f"{'=' * 70}")

    cp = load_checkpoint(demo_dir, args.slug)
    ws_api = cp["ws_api"]
    sdm_api = cp["sdm_api"]
    do_api = cp["do_api"]
    display_date_api = cp.get("display_date_api")
    company = cp.get("company", args.slug.replace("_", " ").title())

    print(f"\n  Workspace:  {ws_api}")
    print(f"  SDM:        {sdm_api}")
    print(f"  DO:         {do_api}")
    print(f"  Company:    {company}")

    # ── Step 2: Authenticate ──────────────────────────────────────────────────
    if not args.dry_run:
        print(f"\n  Authenticating to Salesforce...")
        sf_token, sf_instance = get_sf_token()
        print(f"  Authenticated: {sf_instance}")
    else:
        sf_token, sf_instance = None, None
        print(f"\n  [DRY RUN] Skipping authentication")

    # ── Step 3: Resolve field maps ────────────────────────────────────────────
    dim_field_map = cp.get("dim_field_map") or {}
    measurement_map = cp.get("measurement_map") or {}

    if not dim_field_map or not measurement_map:
        if args.dry_run:
            print(f"  WARNING: No field maps in checkpoint and --dry-run prevents fetching from API.")
            print(f"  Field resolution will use fallback patterns.")
        else:
            print(f"\n  Field maps not in checkpoint — fetching from SDM API...")
            dim_field_map, measurement_map = fetch_field_maps(
                sf_token, sf_instance, sdm_api, do_api
            )
            # Save to checkpoint for future runs
            cp["dim_field_map"] = dim_field_map
            cp["measurement_map"] = measurement_map
            save_checkpoint(cp, demo_dir, args.slug)
            print(f"  Loaded {len(dim_field_map)} dimensions, {len(measurement_map)} measurements")

    # ── Step 4: Extract story config ──────────────────────────────────────────
    story = cp.get("story", {})
    metric_configs = story.get("metric_config", [])
    dimensions = story.get("dimensions", [])
    dimension_values = story.get("dimension_values", {})

    if not metric_configs:
        print(f"  ERROR: No metric_config found in checkpoint story.")
        print(f"  The checkpoint must have story.metric_config from the build phase.")
        sys.exit(1)

    if not dimensions:
        print(f"  WARNING: No dimensions in story config — dashboard composition may be limited.")

    use_case_label = story.get("headline", "Analytics Dashboard")

    # Build the metric field bridge (maps short config field names to DC schema names)
    metric_bridge = _build_metric_field_bridge(metric_configs, measurement_map)
    if metric_bridge:
        print(f"\n  Metric field bridge ({len(metric_bridge)} mappings):")
        seen = set()
        for k, v in metric_bridge.items():
            if k not in seen:
                print(f"    {k:35s} -> {v} -> {measurement_map.get(v, '?')}")
                seen.add(k)

    print(f"\n  Metrics:    {len(metric_configs)}")
    for mc in metric_configs:
        print(f"    - {mc['label']} ({mc.get('field', '?')}, {mc.get('agg', '?')})")
    print(f"  Dimensions: {dimensions}")

    # ── Step 5: Compose the dashboard plan ────────────────────────────────────
    print(f"\n  Composing dashboard plan...")
    plan = compose_dashboard(
        company=company,
        use_case_label=use_case_label,
        metric_configs=metric_configs,
        dimensions=dimensions,
        dimension_values=dimension_values,
        story=story,
        signal_direction=args.signal_direction,
        signal_months=args.signal_months,
        max_kpi_metrics=args.max_kpi_metrics,
        max_vizzes=args.max_vizzes,
    )

    # ── Step 6: Print the ASCII preview ───────────────────────────────────────
    print(f"\n{plan.ascii_preview()}")
    print(f"\n  Components: {len(plan.all_components)}")
    print(f"    KPI tiles:     {sum(len(c.metric_configs) for c in plan.metric_components)}")
    print(f"    Visualizations: {len(plan.viz_components)}")

    build_specs = plan_to_build_specs(plan)
    print(f"\n  Build specs:")
    for i, spec in enumerate(build_specs):
        print(f"    {i+1}. [{spec['story_role']:12s}] {spec['template_name']:20s} -> {spec['viz_label']}")
        for slot, raw in spec["field_map"].items():
            resolved = resolve_field(raw, dim_field_map, measurement_map, display_date_api, metric_bridge)
            print(f"       {slot:15s} = {raw:30s} -> {resolved}")

    if args.dry_run:
        print(f"\n  [DRY RUN] Preview complete. No assets created.")
        # Also show the grid layout
        grid_layout = plan_to_grid_layout(plan)
        print(f"\n  Grid layout ({grid_layout['grid']['columnCount']} cols, {grid_layout['total_rows']} rows):")
        for item in grid_layout["components"]:
            c = item["component"]
            p = item["position"]
            print(f"    {c.component_type:15s} row={p['row']:3d} col={p['column']:2d} "
                  f"span={p['rowspan']}x{p['colspan']}  \"{c.title}\"")
        return

    # ── Step 7: Cleanup prior composed assets ─────────────────────────────────
    if args.cleanup_first:
        print(f"\n  Cleaning up prior composed assets...")
        for v in cp.get("composed_viz_apis", []):
            delete_viz(sf_token, sf_instance, v)
            print(f"    Deleted viz: {v}")
        if cp.get("composed_dash_api"):
            delete_dashboard(sf_token, sf_instance, cp["composed_dash_api"])
            print(f"    Deleted dashboard: {cp['composed_dash_api']}")
        cp["composed_viz_apis"] = []
        cp["composed_dash_api"] = None
        save_checkpoint(cp, demo_dir, args.slug)

    # ── Step 8: Create visualizations ─────────────────────────────────────────
    print(f"\n  Creating visualizations...")
    created_viz_apis = []
    created_viz_labels = []
    ts = datetime.now().strftime("%H%M")

    # Augment the measurement map with bridged entries so viz_builder can
    # resolve metric_config field names (e.g. 'readmission_rate_30d') directly.
    augmented_meas_map = dict(measurement_map)
    for short_field, dc_key in metric_bridge.items():
        if dc_key in measurement_map and short_field not in augmented_meas_map:
            augmented_meas_map[short_field] = measurement_map[dc_key]

    for i, spec in enumerate(build_specs):
        # Build the resolved field_map for viz_builder
        resolved_fields = {}
        for slot, raw in spec["field_map"].items():
            resolved_fields[slot] = resolve_field(
                raw, dim_field_map, measurement_map, display_date_api, metric_bridge
            )

        # Generate a unique viz name
        viz_name = f"{args.slug}_{spec['viz_name']}_{ts}"[:80]

        print(f"\n    [{i+1}/{len(build_specs)}] {spec['viz_label']}")
        print(f"      Template: {spec['template_name']}")
        print(f"      Fields: {resolved_fields}")

        try:
            payload = build_viz_payload(
                template_name=spec["template_name"],
                viz_name=viz_name,
                viz_label=spec["viz_label"],
                sdm_api=sdm_api,
                ws_api=ws_api,
                do_api=do_api,
                field_map=spec["field_map"],          # raw field names for template slot matching
                dim_field_map=dim_field_map,
                measurements=augmented_meas_map,      # includes bridged metric_config field names
                validate=True,
            )
        except Exception as e:
            print(f"      ERROR building payload: {e}")
            continue

        viz_api = create_viz(sf_token, sf_instance, payload)
        if viz_api:
            created_viz_apis.append(viz_api)
            created_viz_labels.append(spec["viz_label"])
            print(f"      Created: {viz_api}")
            # Track for cleanup
            cp.setdefault("all_viz_apis", []).append(viz_api)
            save_checkpoint(cp, demo_dir, args.slug)
        else:
            print(f"      FAILED — skipping this viz")
            # Small delay before next attempt
            time.sleep(1)

    if not created_viz_apis:
        print(f"\n  ERROR: No visualizations were created. Cannot build dashboard.")
        sys.exit(1)

    print(f"\n  Created {len(created_viz_apis)}/{len(build_specs)} visualizations")

    # ── Step 9: Assemble dashboard ────────────────────────────────────────────
    print(f"\n  Assembling dashboard...")

    # Resolve metric widget APIs
    metric_apis = []
    if not args.skip_metrics:
        metric_apis = cp.get("metric_apis", [])
        if not metric_apis:
            # Fallback: try created_metrics dict
            created_metrics = cp.get("created_metrics", {})
            if created_metrics:
                # Match metric_configs order to created_metrics
                for mc in metric_configs[:args.max_kpi_metrics]:
                    mtc = created_metrics.get(mc["label"], "")
                    if mtc:
                        metric_apis.append(mtc)

    if metric_apis:
        print(f"  Metric widgets: {len(metric_apis)}")
        for m in metric_apis:
            print(f"    - {m}")
    else:
        print(f"  No metric widgets (skip_metrics={args.skip_metrics}, "
              f"metric_apis in checkpoint={bool(cp.get('metric_apis'))})")

    # Build the grid layout from the plan
    grid_layout = plan_to_grid_layout(plan)
    grid = grid_layout["grid"]

    # Build widgets dict and page_widgets list
    widgets = {}
    page_widgets = []

    # Add metric widgets from the KPI row positions in the grid layout
    metric_idx = 0
    viz_idx = 0

    for item in grid_layout["components"]:
        comp = item["component"]
        pos = item["position"]

        if comp.component_type == "kpi_tile" and metric_idx < len(metric_apis):
            wname = f"w_mtc_{metric_idx}"
            widgets[wname] = {
                "name": wname,
                "type": "metric",
                "source": {"name": metric_apis[metric_idx]},
                "parameters": {
                    "metricOption": {"sdmApiName": sdm_api},
                },
                "actions": [],
            }
            page_widgets.append({
                "name": wname,
                "row": pos["row"],
                "column": pos["column"],
                "rowspan": pos["rowspan"],
                "colspan": pos["colspan"],
            })
            metric_idx += 1

        elif comp.component_type != "kpi_tile" and viz_idx < len(created_viz_apis):
            wname = f"w_viz_{viz_idx}"
            widgets[wname] = {
                "name": wname,
                "type": "visualization",
                "source": {"name": created_viz_apis[viz_idx]},
                "parameters": {},
                "actions": [],
            }
            page_widgets.append({
                "name": wname,
                "row": pos["row"],
                "column": pos["column"],
                "rowspan": pos["rowspan"],
                "colspan": pos["colspan"],
            })
            viz_idx += 1

    # A container widget is required for the dashboard to be valid
    widgets["w_container"] = {
        "name": "w_container",
        "type": "container",
        "parameters": {"widgetStyle": {}},
        "actions": [],
    }

    dash_name = f"{args.slug}_composed_{datetime.now().strftime('%Y%m%d_%H%M')}"
    dash_label = f"{company} — {use_case_label}"
    page_name = str(uuid.uuid4())

    bg_color = plan.brand.get("dashboard_bg", "#F3F3F3")
    gutter_color = plan.brand.get("gutter_color", "#F3F3F3")

    dash_payload = {
        "name": dash_name,
        "label": dash_label,
        "workspaceIdOrApiName": ws_api,
        "widgets": widgets,
        "layouts": [{
            "name": "default",
            "columnCount": grid["columnCount"],
            "rowHeight": grid["rowHeight"],
            "maxWidth": grid.get("maxWidth", 1200),
            "style": {
                "backgroundColor": bg_color,
                "gutterColor": gutter_color,
                "cellSpacingX": 8,
                "cellSpacingY": 8,
            },
            "pages": [{
                "name": page_name,
                "label": "Overview",
                "widgets": page_widgets,
            }],
        }],
    }

    print(f"\n  Dashboard payload:")
    print(f"    Name:    {dash_name}")
    print(f"    Label:   {dash_label}")
    print(f"    Grid:    {grid['columnCount']} cols x {grid['rowHeight']}px rows")
    print(f"    Widgets: {len(widgets)} ({metric_idx} metrics, {viz_idx} vizzes, 1 container)")

    dash_api = create_dashboard(sf_token, sf_instance, dash_payload)
    if dash_api:
        print(f"\n  Dashboard created: {dash_api}")
    else:
        print(f"\n  Dashboard creation failed — vizzes are still available individually:")
        for v in created_viz_apis:
            print(f"    - {v}")
        dash_api = dash_name  # Use the intended name for checkpoint

    # ── Step 10: Update checkpoint ────────────────────────────────────────────
    cp["composed_viz_apis"] = created_viz_apis
    cp["composed_viz_labels"] = created_viz_labels
    cp["composed_dash_api"] = dash_api
    cp.setdefault("all_dash_apis", []).append(dash_api)
    save_checkpoint(cp, demo_dir, args.slug)

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print(f"  DONE")
    print(f"{'=' * 70}")
    print(f"\n  Visualizations ({len(created_viz_apis)}):")
    for label, api in zip(created_viz_labels, created_viz_apis):
        print(f"    {label:40s} -> {api}")
    print(f"\n  Dashboard: {dash_api}")
    print(f"\n  All assets saved to checkpoint: {os.path.join(demo_dir, f'{args.slug}_checkpoint.json')}")
    print(f"\n  To clean up and rebuild:")
    print(f"    python compose_dashboard_runner.py --slug {args.slug} --cleanup-first")
    print()


if __name__ == "__main__":
    main()
