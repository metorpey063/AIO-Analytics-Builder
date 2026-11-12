"""Roadmap voting for the AIO Web UI.

Votes and SE suggestions live in the Tableau Next & Slack org (Roadmap_Item__c,
Roadmap_Vote__c) behind a public Apex REST endpoint on the AIO Roadmap Site
(roadmap/metadata/classes/AIORoadmapApi.cls). Each voter ranks a top 3
(1st = 3 points, 2nd = 2, 3rd = 1); items rank by points. Voters are anonymous:
each AIO install gets a random ID, stored outside the repo.

ROADMAP.md's "Top Priorities" list is the curated source; `sync` pushes it to
the org (owner only, needs the Salesforce CLI alias).

CLI:
  python3 roadmap_votes.py list            items + votes from the org
  python3 roadmap_votes.py sync [--alias]  push ROADMAP.md Top Priorities to the org
"""
import argparse
import json
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent
ROADMAP_PATH = PROJECT_ROOT / "ROADMAP.md"
# Public guest endpoint (not a secret: it only lists items and records anonymous votes)
SITE_URL = "https://trailsignup-5a85b0dc8e453e.my.salesforce-sites.com/aioroadmap"
API_URL = f"{SITE_URL}/services/apexrest/aio/roadmap"
ORG_ALIAS = "tab-next-and-slack-org-yvh6i7"
VOTER_ID_PATH = Path.home() / ".aio" / "roadmap_voter_id"
TIMEOUT = 8
CACHE_SECONDS = 30

_cache = {"at": 0.0, "items": None}


class RoadmapError(Exception):
    pass


def voter_id() -> str:
    """This install's anonymous voter ID (created on first use)."""
    try:
        vid = VOTER_ID_PATH.read_text().strip()
        if re.fullmatch(r"[A-Za-z0-9-]{16,64}", vid):
            return vid
    except OSError:
        pass
    vid = str(uuid.uuid4())
    VOTER_ID_PATH.parent.mkdir(parents=True, exist_ok=True)
    VOTER_ID_PATH.write_text(vid)
    return vid


def parse_priorities(limit=5) -> list:
    """ROADMAP.md Top Priorities as {key, title, status, summary, rank} dicts."""
    if not ROADMAP_PATH.exists():
        return []
    items = []
    in_section = False
    for line in ROADMAP_PATH.read_text().splitlines():
        if line.startswith("## "):
            if in_section:
                break
            in_section = line.strip() == "## Top Priorities"
            continue
        m = re.match(r"^\d+\.\s+\*\*([^*]+)\*\*\s*\|\s*([^|]+?)\s*\|\s*(.+)$", line) if in_section else None
        if m:
            title = m.group(1).strip()
            items.append({"key": item_key(title), "title": title, "status": m.group(2),
                          "summary": m.group(3).strip(), "rank": len(items) + 1})
            if len(items) >= limit:
                break
    return items


def item_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:100]


def _check(r):
    try:
        body = r.json()
    except ValueError:
        raise RoadmapError(f"Roadmap service returned HTTP {r.status_code}")
    if r.status_code >= 400:
        msg = body.get("error") if isinstance(body, dict) else None
        if not msg and isinstance(body, list) and body:
            msg = body[0].get("message")
        raise RoadmapError(msg or f"Roadmap service returned HTTP {r.status_code}")
    return body


def list_items(use_cache=True) -> list:
    if use_cache and _cache["items"] is not None and time.time() - _cache["at"] < CACHE_SECONDS:
        return _cache["items"]
    try:
        r = requests.get(API_URL, params={"voter": voter_id()}, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise RoadmapError(f"Can't reach the roadmap service ({type(e).__name__})")
    items = _check(r).get("items", [])
    _cache.update(at=time.time(), items=items)
    return items


def _post(payload: dict) -> dict:
    try:
        r = requests.post(API_URL, json={**payload, "voter": voter_id()}, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise RoadmapError(f"Can't reach the roadmap service ({type(e).__name__})")
    _cache["items"] = None
    return _check(r)


def set_picks(item_ids: list) -> list:
    """Set this install's ranked picks (up to 3, first choice first). Returns the updated items."""
    items = _post({"action": "picks", "itemIds": list(item_ids)}).get("items", [])
    _cache.update(at=time.time(), items=items)
    return items


def suggest(title: str, summary: str = "") -> dict:
    """Add a suggestion (live immediately; it takes the suggester's next free pick). Returns {item}."""
    return _post({"action": "suggest", "title": title, "summary": summary})


def sync(alias=ORG_ALIAS) -> list:
    """Upsert ROADMAP.md Top Priorities into the org; clear the rank on roadmap items no longer listed."""
    priorities = parse_priorities()
    if not priorities:
        raise RoadmapError("No Top Priorities found in ROADMAP.md")
    for p in priorities:
        _sf_rest(alias, "PATCH", f"sobjects/Roadmap_Item__c/Item_Key__c/{p['key']}", {
            "Name": p["title"], "Summary__c": p["summary"], "Status__c": p["status"],
            "Source__c": "Roadmap", "Priority_Rank__c": p["rank"]})
    keys = ",".join(f"'{p['key']}'" for p in priorities)
    stale = _sf(alias, ["data", "query", "-q",
                        f"SELECT Id FROM Roadmap_Item__c WHERE Source__c = 'Roadmap' "
                        f"AND Priority_Rank__c != null AND Item_Key__c NOT IN ({keys})"])
    for row in stale.get("records", []):
        # Off the top list: keep the item and its votes, drop the rank
        _sf_rest(alias, "PATCH", f"sobjects/Roadmap_Item__c/{row['Id']}", {"Priority_Rank__c": None})
    _cache["items"] = None
    return priorities


def _sf_rest(alias, method, path, body):
    out = subprocess.run(["sf", "api", "request", "rest", f"/services/data/v62.0/{path}", "-X", method,
                          "-b", json.dumps(body), "-o", alias], capture_output=True, text=True)
    text = out.stdout.strip()
    if out.returncode != 0 or '"errorCode"' in text:
        raise RoadmapError((text or out.stderr.strip())[:300])
    return json.loads(text) if text.startswith("{") else {}


def _sf(alias, args) -> dict:
    out = subprocess.run(["sf", *args, "-o", alias, "--json"], capture_output=True, text=True)
    try:
        body = json.loads(out.stdout)
    except ValueError:
        raise RoadmapError(out.stderr.strip()[:300] or "sf CLI failed")
    if body.get("status") != 0:
        raise RoadmapError(body.get("message", "sf CLI failed")[:300])
    return body.get("result") or {}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["list", "sync"])
    ap.add_argument("--alias", default=ORG_ALIAS)
    args = ap.parse_args()
    try:
        if args.command == "sync":
            for p in sync(args.alias):
                print(f"{p['rank']}. {p['title']} ({p['status']})")
        for it in list_items(use_cache=False):
            rank = f"#{it['rank']}" if it.get("rank") else "  "
            print(f"{rank:>3} {it.get('points', 0):>3} pts {it['votes']:>3} voters  {it['title']}  [{it['status']}]")
    except RoadmapError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
