"""Load the customer config for a Revenue Intelligence demo folder.

The CLI sets REVINTEL_DEMO to the demo folder before importing the other revintel modules,
which then do `from revintel.config import C, DEMO_DIR`. The folder holds the customer config
(`config.py`, or a single `*_config.py`), its pool seed JSON files, and an `out/` folder.
"""

import glob
import json
import types
import importlib.util
import os

DEMO_DIR = os.path.abspath(os.environ.get("REVINTEL_DEMO", "."))


def _find_config(folder):
    for name in ("config.py", "config.json"):
        path = os.path.join(folder, name)
        if os.path.exists(path):
            return path
    found = sorted(glob.glob(os.path.join(folder, "*_config.py")))
    if len(found) != 1:
        raise SystemExit(f"Expected config.py, config.json (or one *_config.py) in {folder}, found {found or 'none'}. "
                         f"Start from revintel/config_template.py.")
    return found[0]


def _load(folder):
    path = _find_config(folder)
    if path.endswith(".json"):   # web UI writes config.json; same keys as the Python template
        mod = types.SimpleNamespace(**json.load(open(path)))
        nu = os.path.join(folder, "new_users.json")
        if os.path.exists(nu):
            mod.USERS.update(json.load(open(nu)))
        return mod
    spec = importlib.util.spec_from_file_location("revintel_customer_config", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


C = _load(DEMO_DIR)
OUT = os.path.join(DEMO_DIR, "out")


def opt(name, default):
    """Optional config setting with the KnowBe4-proven default."""
    return getattr(C, name, default)


# Org field names for the renewal story (set any to None in config if the org lacks it)
FIELDS = {"atr": "ATR__c", "product_churn": "Product_Churn_ACV__c", "closed_lost_atr": "Closed_Lost_ATR__c",
          "primary_reason": "Primary_Loss_Reason__c", "secondary_reason": "Secondary_Loss_Reason__c",
          "commentary": "Loss_Commentary__c", **opt("FIELDS", {})}
OPP_TYPES = {"new": "New Business", "addon": "Add-On Business", "renewal": "Existing Business",
             **opt("OPP_TYPES", {})}
NB_STAGES = {"early": "Targeting", "mid": "Needs Analysis", "late": "Proposal", **opt("NB_STAGES", {})}
RENEWAL_STAGES = {"early": "Created", "mid": "Initial Renewal Discovery", "late": "Negotiations",
                  "confirmed": "Confirmed Renewal", "past_due": "Negotiations",
                  "risk_contraction": "At Risk (Contraction)", "risk_timing": "At Risk (Timing)",
                  **opt("RENEWAL_STAGES", {})}
