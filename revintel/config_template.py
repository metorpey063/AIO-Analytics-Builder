"""Customer config for a Revenue Intelligence demo — copy to demos/<slug>/config.py and fill in.

The /update-rev-intel skill fills this in with the user after `inspect` (org facts) and the
design conversation (customer + use case). Everything the shared revintel engine needs about the
customer's story lives here; the engine has no customer-specific code. Worked example:
demos/knowbe4_renewals/kb4_config.py (KnowBe4 security-awareness renewals, BRD CFP-1033).

The web UI can write the same keys as config.json (tuples become lists).
Pool accounts go in pool_seed.json:
  [{"id": "001…", "segment": "NAMR_ENT", "type": "Enterprise", "name": "…", "country": "…",
    "state": "…", "city": "…", "industry": "…", "orig_name": "<name before re-skin>"}, …]
"""

# ── Org (from `inspect`) ──────────────────────────────────────────────────────
ORG_ALIAS = "<sf CLI alias>"
REFRESH_APPS = ["Einstein_Account_Management", "Revenue_Insights"]   # CRMA app API names to refresh
SEED = 1                                    # change to get a different (still deterministic) story
EXT_PREFIX = "AIO-<CUST>"                   # Opportunity.Demo_External_ID__c prefix (one per customer)
POOL_PREFIX = "AIO-POOL"                    # Account.Demo_External_ID__c prefix (shared demo pool)
CUSTOMER_LABEL = "<Customer>"               # used in account descriptions
STD_PRICEBOOK = "<01s… IsStandard price book>"
RT = {"new": "<012… new-business record type>", "renewal": "<012… Renewal record type>"}
RENEWAL_RECORD_TYPE = "Renewal"             # developer name of RT["renewal"]
POOL_RECORD_TYPE = "Business_Account"       # account RT the pool uses (EAM Account filter → this only)
POOL_RECORD_TYPE_PROFILES = ["Admin"]       # profiles that need that RT visible
NEW_BUSINESS_PROCESS = None                 # e.g. "Simple Sales Process" to (re)enable NB_STAGES on it

# Org picklist values (defaults shown; override only what differs — see `inspect` stages)
NB_STAGES = {"early": "Targeting", "mid": "Needs Analysis", "late": "Proposal"}
RENEWAL_STAGES = {"early": "Created", "mid": "Initial Renewal Discovery", "late": "Negotiations",
                  "confirmed": "Confirmed Renewal", "past_due": "Negotiations",
                  "risk_contraction": "At Risk (Contraction)", "risk_timing": "At Risk (Timing)"}
OPP_TYPES = {"new": "New Business", "addon": "Add-On Business", "renewal": "Existing Business"}
FIELDS = {"atr": "ATR__c", "product_churn": "Product_Churn_ACV__c", "closed_lost_atr": "Closed_Lost_ATR__c",
          "primary_reason": "Primary_Loss_Reason__c", "secondary_reason": "Secondary_Loss_Reason__c",
          "commentary": "Loss_Commentary__c"}   # set any to None if the org doesn't have it

# ── People (USERS keys are used everywhere below) ─────────────────────────────
USERS = {"ceo": "<005…>", "leader": "<005…>"}          # existing personas: key -> User Id
NEW_USERS = []          # (key, first, last, title, time zone) — fictional personas created by `team people`
SALES_LEADER, SALES_LEADER_ROLE, CEO = "leader", "VP of Sales", "ceo"
MANAGERS = {}           # HR line: user key -> manager key
LEADS = {}              # lead key -> [rep keys under them]; 7–9 leads show on the leader's Revenue Insights view
LEAD_ROLES = []         # (role name, developer name, existing devname to reuse or None, lead key)
SUB_ROLES = []          # (role name, developer name, parent lead key, [member keys])
EXTRA_TEAM = []         # other team keys (e.g. a split-role rep outside the lead roles)
STRETCH = {}            # user key -> quota stretch (<1 beats quota, >1 falls behind) — part of the story
OTHER_DEMO_OWNER = None     # User Id to take other demos' opps owned by the team (keeps attainment clean)
OTHER_QUOTA_OWNERS = []     # User Ids whose quotas also roll into the CEO's
ROLES_UNDER_CEO = []        # role names to move out of the leader's roll-up (e.g. "Director of Channel Sales")
NEW_USER_PROFILE = "SDO-Sales"
QUOTA_START, QUOTA_COUNT = (2025, 10), 18    # first quota month, number of months
QUOTA_FLOOR = 0.3                            # monthly quota ≥ this × the rep's average month
ROLE_FORECAST_TYPES = ["OpportunityAmount"]  # role-based types to quota (Revenue Insights uses these)
TERRITORY_FORECAST_TYPE = None               # territory forecast type developer name, if any

# ── Territories (forecast hierarchy; can differ from the HR/role line) ───────
TERRITORY_MODEL = "<0MA… active model>"
TERRITORY_TYPE = "<0M5… territory type>"
TERRITORIES = {}        # developer name -> (Id or None to create, parent devname, forecast manager key)
TERRITORY_LABELS = {}   # developer name -> label for territories created here
TERRITORY_USERS = []    # (territory devname, user key, role in territory)
TERRITORY_USERS_REMOVE = []

# ── Products (standard price book entries) ────────────────────────────────────
PRODUCTS = {}           # key -> {"pbe": "<01u…>", "list": annual price per ~2,000 users, "label": "…"}
CORE_PRODUCT = "<key>"  # always owned; seat add-ons, contraction and upsell use it
CHURN_PRODUCT = None    # product dropped on renewals whenever held (product-churn story)
LAUNCHED_PRODUCTS = {}  # key -> months since launch (can't be sold before)
CORE_TIERS = {}         # Account.Type -> tier label shown on the core product ("Diamond", …)
UNIT = {}               # key -> "users" / "mailboxes" / …
ATTACH = {"Enterprise": {}, "Mid-Market": {}, "Small Business": {}}   # initial attach rate by Account.Type
DROP_WEIGHTS = {}       # products dropped on won renewals when CHURN_PRODUCT isn't held
EXPANSION_WEIGHTS = {}  # which products expansions sell (whitespace closes)
PIPELINE_PRODUCTS = []  # gap-fill open pipeline: first product the account doesn't own

# ── Story ─────────────────────────────────────────────────────────────────────
# One segment per (region × size) team. mult: culprit 1.5–2.5, moderate ~1, flat 0.3, counter-trend -0.05…-0.15
SEGMENTS = {
    # "NAMR_ENT": {"territory": "NAMR_ENT_Renewals", "owner": "<user key>", "region": "NAMR", "mult": -0.10,
    #              "expansion_p": .85, "engagement": .90, "coupled_p": .20,
    #              "risk_mix": {"At Risk (Timing)": .6, "At Risk (Contraction)": .3, "At Risk (Full Churn)": .1},
    #              "reasons": {"Product Gaps/Performance": (.6, ["Lack of AI features"])},
    #              optional: "attach": {...}, "boost": {"<product>": 4}, "expansion_win_p": .7,
    #                        "renewal_upsell_p": .3, "employees": (40, 149)},
}
OWNER_SPLITS = {}       # segment -> (lead key, N): the N largest accounts become that lead's own book
SIGNAL = {              # accelerating ramps; product drops lead full churn (leading indicator)
    "drop":  {"onset": -10, "duration": 8, "base": .03, "mag": .80, "cap": .85},
    "churn": {"onset": -6,  "duration": 6, "base": .02, "mag": .18, "cap": .35},
    "contraction": {"onset": -8, "duration": 7, "base": .10, "mag": .15},
    "risk":  {"base": .12, "mag": .30, "horizon_days": 240},
}
REASON_THRESHOLD = 0.25 # loss reasons required when > this share of ATR is lost
FOCUS = {"segments": (), "months_ahead": 2, "counter_trend_risk_p": .15, "max_risk_p": .25, "upsell_p": .30}
#   FOCUS: segments whose open renewal lands this month … month+N (a forecast-window ask from the AE)
EMPLOYEES = {"Enterprise": (5000, 15000), "Mid-Market": (1000, 4999), "Small Business": (150, 999)}
CONTACT_TITLES = ["CIO", "IT Director", "Program Manager", "VP Operations", "Procurement Lead", "CFO"]
CONTACTS_PER_SEGMENT = {"Enterprise": 6, "Mid-Market": 4, "Small Business": 3}
TASK_SUBJECTS = ["Call – renewal check-in", "Email – usage report", "Call – adoption review", "Email – renewal quote"]
EVENT_SUBJECTS = {"upcoming": "QBR – programme review", "past": "Renewal planning meeting"}
SEAT_ADDON_NEXT_STEP = "Hand off to CSM; provision the new users."
NEXT_STEPS = {}         # stage name -> next-step text ({lead} = lead product label, {add} = product to position)
COMMENTARY = {}         # secondary loss reason -> loss commentary text
# loss_reasons.json (Primary -> valid Secondary values, from the org's dependent picklist) is
# validated against SEGMENTS reasons when present.
