"""Walkthrough screenshots: `python3 -m revintel <demo> screenshots [--only 1,4] [--headed] [--list]`.

Reads out/shots.json (written by `walkthrough`: per step, the dashboard, the user to view it as, the
filter picks, what to scroll to / click), opens each dashboard in Chromium (Playwright) and saves
out/screenshots/{step}.jpg. Then rewrites the walkthrough, which embeds each image under its step.

Each user is signed in through the CLI session (`sf org open --url-only`) and then Login-As
(/servlet/servlet.su): Revenue Insights and the Command Center show the signed-in user, so the
admin's own view is the wrong one. Read-only: nothing in the org changes. `--list` prints the
plan without opening a browser; `--debug` prints the page's console errors and failed calls. Needs `pip install playwright && python3 -m playwright install chromium`.
"""

import html
import json
import os
from urllib.parse import quote, urlsplit

from revintel.config import C, OUT, opt
from revintel import apply as A

SHOTS = os.path.join(OUT, "screenshots")
VIEWPORT = {"width": 1600, "height": 1000}
BLOCKED = ("Resource Not Found", "Not Permitted", "Unable to open the")
RENDER_WAIT = 45
# Bottom edge of the full-width banners Salesforce stacks above the app while logged in as someone else
BANNERS_BOTTOM = """() => { let b = 0;
  for (const el of document.querySelectorAll('body *')) {
    const t = (el.innerText || '').trim();
    if (!(t.startsWith('Logged in as') || t.startsWith('To make use of all available features'))) continue;
    let e = el; while (e.parentElement && e.getBoundingClientRect().width < innerWidth - 4) e = e.parentElement;
    const r = e.getBoundingClientRect(); if (r.top < 200 && r.bottom < 200) b = Math.max(b, r.bottom); }
  return Math.round(b); }"""   # seconds for CRMA widgets to finish querying after the page loads


def _dashboard_ids(labels):
    """Dashboard label -> ID. `SCREENSHOT_DASHBOARDS` in the config wins; otherwise searched by label,
    preferring the Revenue Insights / EAM app folders (older copies live in other apps)."""
    found = dict(opt("SCREENSHOT_DASHBOARDS", {}))
    for label in labels:
        if label in found:
            continue
        res = A.rest(f"/services/data/v62.0/wave/dashboards?q={quote(label)}&pageSize=50")
        hits = [d for d in res.get("dashboards", []) if html.unescape(d.get("label", "")) == label]   # labels come back HTML-encoded
        hits.sort(key=lambda d: (d.get("folder", {}).get("label") not in ("Revenue Insights",
                                                                         "Einstein Account Management"),
                                 d.get("lastModifiedDate", "")))
        if not hits:
            raise SystemExit(f"Dashboard {label!r} not found. Add it to SCREENSHOT_DASHBOARDS in the config.")
        found[label] = hits[0]["id"]
    return found


def _user_id(shot):
    uid = C.USERS.get(shot["user_key"])
    if uid:
        return uid
    rows = A.query(f"SELECT Id FROM User WHERE Name = '{shot['user'].replace(chr(39), '')}' AND IsActive = true")
    if not rows:
        raise SystemExit(f"User {shot['user']!r} not found in {C.ORG_ALIAS}.")
    return rows[0]["Id"]


def _target(shot, dash):
    """Path the step opens: its dashboard, or a record page (`record`: [sObject, Name])."""
    if shot.get("record"):
        obj, name = shot["record"]
        rows = A.query(f"SELECT Id FROM {obj} WHERE Name = '{name.replace(chr(39), chr(92) + chr(39))}' LIMIT 1")
        if not rows:
            raise SystemExit(f"{obj} {name!r} not found in {C.ORG_ALIAS}.")
        return f"/lightning/r/{obj}/{rows[0]['Id']}/view"
    return f"/analytics/dashboard/{dash[shot['dashboard']]}"


def _frontdoor(path):
    return A.sf("org", "open", "--url-only", "--path", path)["url"]


def _find(page, make):
    """First visible match across the page and its frames (CRMA renders some widgets in iframes)."""
    for fr in page.frames:
        loc = make(fr)
        try:
            for i in range(min(loc.count(), 20)):   # labels repeat (filter + column header, hidden a11y copies)
                if loc.nth(i).is_visible():
                    return loc.nth(i)
        except Exception:
            continue
    return None


def _scroll_find(page, make, tries=10):
    """CRMA renders widgets as they scroll into view: wheel down until the target exists."""
    for _ in range(tries):
        hit = _find(page, make)
        if hit:
            return hit
        page.mouse.move(VIEWPORT["width"] / 2, VIEWPORT["height"] * 0.7)
        page.mouse.wheel(0, 700)
        page.wait_for_timeout(4000)
    return None


def _pick(page, label, value):
    """Filter widget: open it, type in the search box, choose the value, press Update (or Apply)."""
    w = _find(page, lambda f: f.get_by_text(label, exact=True))
    if not w:
        return f"filter {label!r} not on the page"
    w.click()
    page.wait_for_timeout(1500)
    box = (_find(page, lambda f: f.get_by_placeholder("Search for values..."))                     # Revenue Insights
           or _find(page, lambda f: f.locator("input[role='combobox'][aria-autocomplete='list']")))  # EAM (no placeholder)
    if box:
        box.fill(value)
        page.wait_for_timeout(2500)
    row = _find(page, lambda f: f.get_by_role("option", name=value))
    if row:   # EAM list: click the row's own control (clicking the label text only focuses it), check it took
        target = row.locator(f"[aria-label^='{value},']")
        (target.first if target.count() else row).click()
        page.wait_for_timeout(1000)
        if row.get_attribute("aria-selected") == "false":
            return f"{value!r} didn't select in the {label!r} filter"
    else:
        opt_ = (_find(page, lambda f: f.get_by_role("radio", name=value))
                or _find(page, lambda f: f.get_by_text(value, exact=True)))
        if not opt_:
            page.keyboard.press("Escape")
            return f"value {value!r} not in the {label!r} filter"
        opt_.click()
    upd = (_find(page, lambda f: f.get_by_role("button", name="Update", exact=True))     # Revenue Insights
           or _find(page, lambda f: f.get_by_role("button", name="Apply", exact=True)))  # EAM
    if upd:
        upd.click()
    return None


def _capture(page, shot, url):
    page.goto(url, wait_until="domcontentloaded", timeout=120_000)
    page.wait_for_timeout(RENDER_WAIT * 1000)
    for msg in BLOCKED:   # Salesforce's access dialogs: no point saving a picture of them
        if _find(page, lambda f: f.get_by_text(msg)):
            return [f"BLOCKED: {shot['user']} can't open {shot['dashboard']} ({msg}). Give them CRM Analytics + "
                    "Revenue Insights access and share the app, then run again."]
    notes = []
    for label, value in shot.get("filters", []):
        problem = _pick(page, label, value)
        if problem:
            notes.append(problem)
        else:
            page.wait_for_timeout(15_000)   # widgets re-query after a filter change
    if shot.get("scroll_to"):
        t = _scroll_find(page, lambda f: f.get_by_text(shot["scroll_to"]))
        if t:
            t.scroll_into_view_if_needed()
            t.evaluate("e => e.scrollIntoView({block: 'start'})")   # section heading at the top of the shot
            page.wait_for_timeout(3000)
        else:
            notes.append(f"{shot['scroll_to']!r} not on the page")
    if shot.get("click_any"):   # e.g. the one EAM tile (All / Most at Risk / Where to Sell) the account is in
        hit = next((h for h in (_find(page, lambda f, t=t: f.get_by_text(t, exact=True)) for t in shot["click_any"]) if h),
                   None)
        if hit:
            hit.click()
            page.wait_for_timeout(10_000)
        else:
            notes.append(f"none of {shot['click_any']} on the page")
    if shot.get("click"):
        c = _scroll_find(page, lambda f: f.get_by_text(shot["click"], exact=True), tries=3)
        if c:
            c.click()
            page.wait_for_timeout(8000)
        else:
            notes.append(f"{shot['click']!r} not clickable")
    os.makedirs(SHOTS, exist_ok=True)
    tips = page.locator(".slds-popover button[title*='lose'], .slds-popover button.slds-popover__close, "
                        ".slds-popover button[class*='close']")   # Salesforce's feature tips ("Slack in Salesforce")
    for i in range(min(tips.count(), 5)):
        try:
            if tips.nth(i).is_visible():
                tips.nth(i).click(timeout=3000)
        except Exception:
            pass
    page.mouse.move(VIEWPORT["width"] - 5, VIEWPORT["height"] - 5)   # no hover tooltip in the shot
    page.wait_for_timeout(1000)
    top = page.evaluate(BANNERS_BOTTOM) or 0   # crop the "Logged in as …" / verify-email banners
    page.screenshot(path=os.path.join(SHOTS, f"{shot['key']}.jpg"), type="jpeg", quality=85,
                    clip={"x": 0, "y": top, "width": VIEWPORT["width"], "height": VIEWPORT["height"] - top})
    return notes


def run(only=None, headed=False, list_only=False, debug=False):
    path = os.path.join(OUT, "shots.json")
    if not os.path.exists(path):
        from revintel import walkthrough
        walkthrough.build()
    shots = json.load(open(path))
    if only:
        shots = [s for s in shots if s["key"] in only]
    if not shots:
        raise SystemExit("No steps to capture.")
    if list_only:
        for s in shots:
            extra = "; ".join(f"{k}: {v}" for k, v in s.items() if k in ("filters", "scroll_to", "click", "click_any"))
            print(f"  {s['key']}. {s['title']}  [{s.get('dashboard') or ' '.join(s['record'])} as {s['user']}]  {extra}")
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("Playwright isn't installed: pip install playwright && python3 -m playwright install chromium")

    dash = _dashboard_ids(sorted({s["dashboard"] for s in shots if s.get("dashboard")}))
    org_id = A.sf("org", "display")["id"]
    problems = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not headed)
        for user_key in dict.fromkeys(s["user_key"] for s in shots):
            mine = [s for s in shots if s["user_key"] == user_key]
            uid = _user_id(mine[0])
            # One context per user: the CLI session, then Login-As that user, landing on the first dashboard
            ctx = browser.new_context(viewport=VIEWPORT, device_scale_factor=1.5)
            page = ctx.new_page()
            if debug:   # print what the page rejects (console errors, failed API calls)
                page.on("console", lambda m: m.type == "error" and print(f"     console: {m.text[:300]}", flush=True))
                page.on("response", lambda r: r.status >= 400 and print(f"     {r.status} {r.url[:200]}", flush=True))
            first = _target(mine[0], dash)
            su = f"/servlet/servlet.su?oid={org_id}&suorgadminid={uid}&retURL=%2F&targetURL={quote(first, safe='')}"
            print(f"Signing in as {mine[0]['user']}…", flush=True)
            page.goto(_frontdoor(su), wait_until="domcontentloaded", timeout=120_000)
            page.wait_for_timeout(5000)
            u = urlsplit(page.url)
            base = f"{u.scheme}://{u.netloc}"
            if "/secur/" in u.path or "login" in u.netloc:
                raise SystemExit(f"Login-As {mine[0]['user']} didn't go through (landed on {page.url}). Check that "
                                 "admins can log in as any user (Setup → Login Access Policies).")
            for s in mine:
                print(f"  {s['key']}. {s['title']} ({s.get('dashboard') or s['record'][1]})", flush=True)
                notes = _capture(page, s, base + _target(s, dash))
                for n in notes:
                    print(f"     ! {n}", flush=True)
                if notes:
                    problems[s["key"]] = notes
                if any(n.startswith("BLOCKED") for n in notes):
                    stale = os.path.join(SHOTS, f"{s['key']}.jpg")
                    if os.path.exists(stale):
                        os.remove(stale)
            try:   # end the Login-As session
                page.goto(f"{base}/secur/logout.jsp", timeout=30_000)
            except Exception:
                pass
            ctx.close()
        browser.close()

    from revintel import walkthrough
    out = walkthrough.build()
    print(f"\n{len(shots)} screenshot(s) in {SHOTS}; walkthrough rewritten: {out}")
    if problems:
        print(f"{len(problems)} step(s) captured without everything set up (see '!' lines). Check those images.")
