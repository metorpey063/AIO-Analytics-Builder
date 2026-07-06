"""
Waste Connections — Route Operations & Workforce Demo
Use case : Route cost per ton rising due to workforce turnover in specific regions
Persona  : Lee Kamar, BI Manager
Output   : Tableau Next (Data Cloud + Semantic Model + Dashboard)

Story: Route costs are climbing in the Southern and Central regions.
Drilling in reveals: stops per route are declining (fewer pickups per truck per day).
The root cause: voluntary turnover spiked among experienced drivers (2-5yr tenure)
in those regions, leaving routes understaffed and forcing overtime/temp coverage.
The safety incident rate is also ticking up — new/temp drivers have higher TRIR.
"""

import sys, os, json, time, uuid, math, requests
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from connections import load_config, get_sf_token, get_dc_token, sf_headers, dc_headers

# ── Settings ─────────────────────────────────────────────────────────────────
HISTORY_MONTHS        = 24
GRAIN                 = "monthly"
SIGNAL_MAGNITUDE      = 0.25
SIGNAL_ONSET          = -6
SIGNAL_SHAPE          = "accelerating"
SUPPORTING_MAGNITUDE  = 0.15
PROFILE_KEY           = "tableau_next_slack"

TODAY        = date.today()
COMPANY      = "Waste Connections"
SLUG         = "waste_connections"
USE_CASE     = "route_ops"
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
CHECKPOINT_F = os.path.join(SCRIPT_DIR, f"{SLUG}_{USE_CASE}_checkpoint.json")

print(f"""
╔══════════════════════════════════════════════════════════╗
  Waste Connections — Route Operations & Workforce
  History: {HISTORY_MONTHS}mo  Grain: {GRAIN}
  Signal: {int(SIGNAL_MAGNITUDE*100)}% cost increase, onset {SIGNAL_ONSET}mo
  Shape: {SIGNAL_SHAPE}
╚══════════════════════════════════════════════════════════╝
""")

# ── Checkpoint helpers ────────────────────────────────────────────────────────
def load_cp():
    if os.path.exists(CHECKPOINT_F):
        with open(CHECKPOINT_F) as f:
            return json.load(f)
    return {"all_ws_apis": [], "all_sdm_apis": [], "all_viz_apis": [], "all_dash_apis": []}

def save_cp(cp):
    with open(CHECKPOINT_F, "w") as f:
        json.dump(cp, f, indent=2)

cp = load_cp()

# ── Signal function ──────────────────────────────────────────────────────────
def signal_ramp(d, onset=SIGNAL_ONSET, duration=6, shape=SIGNAL_SHAPE):
    if isinstance(d, (datetime, pd.Timestamp)):
        d = d.date()
    months_from_today = (d.year - TODAY.year) * 12 + (d.month - TODAY.month)
    months_from_onset = months_from_today - onset
    if months_from_onset <= 0:
        return 0.0
    progress = min(1.0, months_from_onset / duration)
    if shape == "accelerating":
        return progress ** 2
    elif shape == "ramp":
        return progress
    elif shape == "step":
        return 1.0 if progress >= 0.3 else 0.0
    return progress

# ── Dimension definitions ────────────────────────────────────────────────────
REGIONS = ["Western", "Southern", "Central", "Eastern", "Canada", "MidSouth"]

DISTRICTS = {
    "Western":  ["Pacific Northwest", "Northern California", "Southern California", "Mountain West"],
    "Southern": ["Gulf Coast", "Southeast Texas", "Florida Panhandle", "Carolinas"],
    "Central":  ["Great Plains", "Upper Midwest", "Missouri Valley", "Ozarks"],
    "Eastern":  ["Mid-Atlantic", "New England", "Great Lakes", "Ohio Valley"],
    "Canada":   ["Ontario", "Alberta", "British Columbia", "Quebec"],
    "MidSouth": ["Tennessee Valley", "Mississippi Delta", "Arkansas", "Oklahoma"],
}

SERVICE_TYPES = ["Residential", "Commercial", "Industrial", "E&P"]
ROLE_TYPES = ["Driver", "Mechanic", "Operator", "Helper"]
TENURE_BANDS = ["< 1 Year", "1-2 Years", "2-5 Years", "5-10 Years", "10+ Years"]
FLEET_AGE_BANDS = ["New (0-2yr)", "Mid-Life (3-5yr)", "Aging (6-8yr)", "End-of-Life (9+yr)"]

# ── Signal multipliers ───────────────────────────────────────────────────────
# Southern and Central are the problem regions
REGION_SIGNAL_MULT = {
    "Southern": 1.8,
    "Central":  1.4,
    "MidSouth": 0.8,
    "Eastern":  0.4,
    "Western":  0.2,
    "Canada":  -0.10,  # counter-trend: actually improving
}

# Commercial service type hit hardest (larger routes, more complex)
SERVICE_SIGNAL_MULT = {
    "Commercial":  1.5,
    "Industrial":  1.1,
    "Residential": 0.6,
    "E&P":         0.3,
}

# 2-5yr tenure drivers leaving (the experienced ones)
TENURE_SIGNAL_MULT = {
    "2-5 Years":  2.5,  # the exodus
    "1-2 Years":  1.5,
    "5-10 Years": 0.8,
    "< 1 Year":   0.3,  # new hires replacing
    "10+ Years":  0.2,  # lifers staying
}

# Aging fleet compounds the cost issue
FLEET_AGE_SIGNAL_MULT = {
    "End-of-Life (9+yr)": 1.8,
    "Aging (6-8yr)":      1.3,
    "Mid-Life (3-5yr)":   0.7,
    "New (0-2yr)":        0.3,
}

# ── Data generation ──────────────────────────────────────────────────────────
print("Phase 0 — Generating synthetic route operations data...")

np.random.seed(42)

# Date range
start_date = TODAY - relativedelta(months=HISTORY_MONTHS)
dates = pd.date_range(start=start_date, end=TODAY, freq="MS")

# Generate district-level data (one row per district per service type per month)
rows = []
record_counter = 0

for d in dates:
    ramp = signal_ramp(d.date())

    for region in REGIONS:
        region_mult = REGION_SIGNAL_MULT[region]
        districts = DISTRICTS[region]

        for district in districts:
            for service_type in SERVICE_TYPES:
                record_counter += 1
                svc_mult = SERVICE_SIGNAL_MULT[service_type]

                # Combined signal
                if region_mult > 0:
                    combined = ramp * region_mult * svc_mult
                else:
                    combined = ramp * region_mult  # counter-trend flat

                # Base values (healthy period)
                base_cost_per_ton = np.random.uniform(38, 52)  # $38-52 industry range
                base_stops_per_route = np.random.uniform(180, 320)  # depends on service type
                if service_type == "Residential":
                    base_stops_per_route = np.random.uniform(250, 350)
                elif service_type == "Commercial":
                    base_stops_per_route = np.random.uniform(80, 150)
                elif service_type == "Industrial":
                    base_stops_per_route = np.random.uniform(15, 40)
                else:  # E&P
                    base_stops_per_route = np.random.uniform(8, 20)

                base_fleet_util = np.random.uniform(0.85, 0.95)
                base_turnover = np.random.uniform(0.015, 0.030)  # monthly rate
                base_trir = np.random.uniform(1.5, 3.5)
                base_tenure = np.random.uniform(3.5, 6.5)  # years

                # Apply signal
                noise_cost = np.random.normal(0, 0.03)
                noise_stops = np.random.normal(0, 0.02)
                noise_fleet = np.random.normal(0, 0.015)
                noise_turnover = np.random.normal(0, 0.005)

                # Primary metrics get full signal
                cost_per_ton = base_cost_per_ton * (1 + SIGNAL_MAGNITUDE * combined + noise_cost)
                stops_per_route = base_stops_per_route * (1 - SUPPORTING_MAGNITUDE * combined + noise_stops)

                # Supporting metrics get softer signal
                fleet_util = base_fleet_util * (1 - SUPPORTING_MAGNITUDE * combined * 0.7 + noise_fleet)
                turnover_rate = base_turnover * (1 + SIGNAL_MAGNITUDE * combined * 0.8 + noise_turnover)
                trir = base_trir * (1 + SUPPORTING_MAGNITUDE * combined * 0.6 + np.random.normal(0, 0.05))
                avg_tenure = base_tenure * (1 - SUPPORTING_MAGNITUDE * combined * 0.5 + np.random.normal(0, 0.02))

                # Assign a dominant tenure band and fleet age for this row
                if combined > 0.5:
                    tenure_band = np.random.choice(TENURE_BANDS, p=[0.30, 0.25, 0.20, 0.15, 0.10])
                    fleet_age = np.random.choice(FLEET_AGE_BANDS, p=[0.15, 0.25, 0.35, 0.25])
                else:
                    tenure_band = np.random.choice(TENURE_BANDS, p=[0.15, 0.20, 0.25, 0.25, 0.15])
                    fleet_age = np.random.choice(FLEET_AGE_BANDS, p=[0.25, 0.35, 0.25, 0.15])

                role_type = np.random.choice(ROLE_TYPES, p=[0.55, 0.20, 0.15, 0.10])

                # Truck count for this district/service combo
                truck_count = {"Residential": np.random.randint(8, 25),
                               "Commercial": np.random.randint(5, 15),
                               "Industrial": np.random.randint(2, 8),
                               "E&P": np.random.randint(1, 5)}[service_type]

                # Revenue and tons (derived)
                tons_collected = truck_count * stops_per_route * np.random.uniform(0.02, 0.08)  # tons per stop varies
                revenue = tons_collected * cost_per_ton * np.random.uniform(1.15, 1.35)  # margin on top of cost

                rows.append({
                    "Record ID": f"WC-{record_counter:06d}_{d.strftime('%Y%m')}",
                    "Date": d.date().isoformat(),
                    "Region": region,
                    "District": district,
                    "Service Type": service_type,
                    "Role Type": role_type,
                    "Tenure Band": tenure_band,
                    "Fleet Age": fleet_age,
                    "Route Cost Per Ton": round(max(25, cost_per_ton), 2),
                    "Stops Per Route": round(max(5, stops_per_route), 0),
                    "Fleet Utilization Rate": round(max(0.50, min(0.99, fleet_util)), 4),
                    "Voluntary Turnover Rate": round(max(0.005, min(0.12, turnover_rate)), 4),
                    "Safety Incident Rate": round(max(0.5, trir), 2),
                    "Avg Driver Tenure Years": round(max(0.5, avg_tenure), 1),
                    "Truck Count": truck_count,
                    "Tons Collected": round(max(10, tons_collected), 0),
                    "Revenue": round(max(500, revenue), 0),
                })

df = pd.DataFrame(rows)

print(f"  Generated {len(df)} rows across {len(dates)} months")
print(f"  Regions: {df['Region'].nunique()} | Districts: {df['District'].nunique()}")
print(f"  Date range: {df['Date'].min()} to {df['Date'].max()}")

# Sanity check signal
recent = df[df["Date"] >= (TODAY - timedelta(days=60)).isoformat()]
older = df[df["Date"] < (TODAY - timedelta(days=365)).isoformat()]
print(f"\n  Signal check (Southern + Commercial):")
south_comm_recent = recent[(recent["Region"] == "Southern") & (recent["Service Type"] == "Commercial")]
south_comm_older = older[(older["Region"] == "Southern") & (older["Service Type"] == "Commercial")]
print(f"    Cost/ton (recent):  ${south_comm_recent['Route Cost Per Ton'].mean():.2f}")
print(f"    Cost/ton (>12mo):   ${south_comm_older['Route Cost Per Ton'].mean():.2f}")
print(f"    Turnover (recent):  {south_comm_recent['Voluntary Turnover Rate'].mean():.3f}")
print(f"    Turnover (>12mo):   {south_comm_older['Voluntary Turnover Rate'].mean():.3f}")
print(f"    Stops/route (recent): {south_comm_recent['Stops Per Route'].mean():.0f}")
print(f"    Stops/route (>12mo):  {south_comm_older['Stops Per Route'].mean():.0f}")

# Counter-trend check
canada_recent = recent[recent["Region"] == "Canada"]
canada_older = older[older["Region"] == "Canada"]
print(f"\n  Counter-trend (Canada):")
print(f"    Cost/ton (recent):  ${canada_recent['Route Cost Per Ton'].mean():.2f}")
print(f"    Cost/ton (>12mo):   ${canada_older['Route Cost Per Ton'].mean():.2f}")

# ── Metric config ────────────────────────────────────────────────────────────
METRIC_CONFIG = [
    {
        "label": "Route Cost Per Ton",
        "field": "Route Cost Per Ton",
        "agg": "Average",
        "pulse_agg": "AGGREGATION_AVERAGE",
        "description": "Average cost in dollars to collect and transport one ton of waste. Rising costs signal route inefficiency, understaffing, or aging fleet.",
        "why_it_matters": "Direct profitability metric — when cost per ton rises without volume growth, margins erode. The first sign of operational strain.",
        "singular": "route cost per ton", "plural": "route costs per ton",
        "sentiment": "Down",
    },
    {
        "label": "Voluntary Turnover Rate",
        "field": "Voluntary Turnover Rate",
        "agg": "Average",
        "pulse_agg": "AGGREGATION_AVERAGE",
        "description": "Monthly rate of voluntary employee departures as a fraction of total headcount. Higher = more people choosing to leave.",
        "why_it_matters": "Leading indicator of route disruption — when experienced drivers leave, routes go understaffed, costs spike, and safety degrades.",
        "singular": "voluntary turnover rate", "plural": "voluntary turnover rates",
        "sentiment": "Down",
    },
    {
        "label": "Stops Per Route",
        "field": "Stops Per Route",
        "agg": "Average",
        "pulse_agg": "AGGREGATION_AVERAGE",
        "description": "Average number of collection stops completed per truck route per day. Declining stops = fewer pickups per driver shift.",
        "why_it_matters": "Efficiency metric — fewer stops means either understaffed routes, longer dwell times, or route design problems.",
        "singular": "stop per route", "plural": "stops per route",
        "sentiment": "Up",
    },
    {
        "label": "Fleet Utilization Rate",
        "field": "Fleet Utilization Rate",
        "agg": "Average",
        "pulse_agg": "AGGREGATION_AVERAGE",
        "description": "Percentage of available trucks actively deployed on routes each day. Below 85% signals excess idle fleet or maintenance backlogs.",
        "why_it_matters": "Capital efficiency metric — idle trucks are sunk cost. Low utilization often correlates with driver shortages or maintenance delays.",
        "singular": "fleet utilization rate", "plural": "fleet utilization rates",
        "sentiment": "Up",
    },
    {
        "label": "Safety Incident Rate",
        "field": "Safety Incident Rate",
        "agg": "Average",
        "pulse_agg": "AGGREGATION_AVERAGE",
        "description": "Total Recordable Incident Rate (TRIR) — number of workplace injuries per 200,000 hours worked. Industry average is 3.0-5.0.",
        "why_it_matters": "Lagging safety metric — rising TRIR correlates with inexperienced drivers replacing tenured ones. Also carries regulatory and insurance cost implications.",
        "singular": "safety incident", "plural": "safety incidents",
        "sentiment": "Down",
    },
    {
        "label": "Avg Driver Tenure Years",
        "field": "Avg Driver Tenure Years",
        "agg": "Average",
        "pulse_agg": "AGGREGATION_AVERAGE",
        "description": "Average years of service for active drivers in a district. Declining tenure = experienced workforce being replaced by newer hires.",
        "why_it_matters": "Workforce depth metric — experienced drivers run more efficient routes, have fewer incidents, and know their territory. Tenure loss = institutional knowledge loss.",
        "singular": "year of driver tenure", "plural": "years of driver tenure",
        "sentiment": "Up",
    },
]

DIM_DESCRIPTIONS = {
    "Region": "Waste Connections operating region (Western, Southern, Central, Eastern, Canada, MidSouth). Use to identify which regions are experiencing the worst cost and turnover trends.",
    "District": "Operational district within a region. Use for granular geographic drill-down to identify specific problem areas.",
    "Service Type": "Type of waste collection service (Residential, Commercial, Industrial, E&P). Commercial routes show the sharpest cost increases due to complexity and driver skill requirements.",
    "Role Type": "Employee role classification (Driver, Mechanic, Operator, Helper). Drivers are the critical role — their turnover directly impacts route capacity.",
    "Tenure Band": "Employee tenure grouping. The 2-5 Year band is the 'experience sweet spot' — these employees leaving signals a systemic retention problem, not normal attrition.",
    "Fleet Age": "Vehicle age band (New 0-2yr, Mid-Life 3-5yr, Aging 6-8yr, End-of-Life 9+yr). Aging fleet correlates with higher maintenance costs and lower utilization.",
}

# ── Save CSV ─────────────────────────────────────────────────────────────────
csv_path = os.path.join(SCRIPT_DIR, f"{SLUG}_{USE_CASE}_{TODAY.strftime('%Y%m%d')}.csv")
df.to_csv(csv_path, index=False)
print(f"\n  Saved CSV: {csv_path}")
print(f"  Shape: {df.shape}")

cp["csv_done"] = True
cp["csv_path"] = csv_path
cp["build_date"] = TODAY.isoformat()
save_cp(cp)

print("\n✓ Phase 0 complete — data generated.")
