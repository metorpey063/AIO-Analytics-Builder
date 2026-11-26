"""A picture of a deployed Tableau Next data app: `python3 -m dataapps next shot --slug S`.

Nothing outside the org can render a Next data app, so AIO signs in through the Salesforce CLI
(`sf org open --url-only`, the same session embed.py uses), opens the app, grows the window to the
app's full height and saves demos/{slug}/{slug}_data_app_next.jpg (recorded as `image` in the
checkpoint). It also keeps the app's build files (demos/{slug}/data_app_next_live/) for the Web UI's live
view. Read-only. Needs Playwright (`pip install playwright && python3 -m playwright install chromium`).

The app renders three frames deep: Lightning page -> salesforce.app iframe -> about:srcdoc (the page).
"""

import json
import os
import re
import time
from urllib.parse import urlsplit

from dataapps import common as C

WIDTH = 1440
RENDER_WAIT = 35     # seconds for the app's queries to come back
MAX_HEIGHT = 9000    # px; longer pages are cut off rather than producing a huge image


def live_dir(slug):
    """Where the app's build (its JS/CSS and their manifest) is kept for the live view in the Web UI."""
    return os.path.join(C.app_dir(slug), "data_app_next_live")


def _keep_build(page, seen):
    """Note the app's build responses (/sfpage/c__App/assets/*, and the page listing them); read after loading,
    since reading a body inside the sync event handler stalls the page."""
    def on_response(r):
        u = r.url.split("?")[0]
        if "/sfpage/" in u and (("/assets/" in u and re.search(r"\.(?:js|css)$", u))
                                or r.request.resource_type == "document"):
            seen.append(r)
    page.on("response", on_response)


def _read_build(seen):
    store = {}
    for r in seen:
        try:
            u = r.url.split("?")[0]
            name = u.rsplit("/", 1)[1]
            if "/assets/" in u and re.fullmatch(r"[\w.-]+\.(?:js|css)", name):
                store[name] = r.body()
            elif r.status == 200:
                m = re.search(r'<script type="application/json" id="data-app-assets">(.*?)</script>', r.text(), re.S)
                if m:
                    store["manifest.json"] = m.group(1).encode()
        except Exception:
            continue
    return store


def _save_build(slug, store):
    if "manifest.json" not in store:
        return None
    files = json.loads(store["manifest.json"])
    if not all(f in store for f in files.get("css", []) + files.get("js", [])):
        return None
    d = live_dir(slug)
    os.makedirs(d, exist_ok=True)
    for old in os.listdir(d):
        os.remove(os.path.join(d, old))
    for name, data in store.items():
        open(os.path.join(d, name), "wb").write(data)
    return d


def _app_frame(page):
    return next((f for f in page.frames if f.url == "about:srcdoc"), None)


def next_snapshot(slug):
    from dataapps import embed as E
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise SystemExit("Playwright isn't installed: pip install playwright && python3 -m playwright install chromium")
    cp = C.load_cp(slug, "next")
    if not cp.get("url"):
        raise SystemExit(f"No Tableau Next data app recorded in demos/{slug}.")
    res = E._sf(["org", "open", "--target-org", E.cli_alias(cp["profile"]), "--url-only",
                 "--path", urlsplit(cp["url"]).path], timeout=120)
    url = (res.get("result") or {}).get("url", "")
    if "frontdoor" not in url:
        raise SystemExit(f"Couldn't get a sign-in link from the Salesforce CLI ({res.get('message', 'no URL')}).")
    path = os.path.join(C.app_dir(slug), f"{slug}_data_app_next.jpg")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_context(viewport={"width": WIDTH, "height": 900}, device_scale_factor=1.5).new_page()
        seen = []
        _keep_build(page, seen)
        page.goto(url, wait_until="domcontentloaded", timeout=120_000)
        app = None
        for _ in range(30):   # the page frame appears once the app's bundle loads
            page.wait_for_timeout(2000)
            app = _app_frame(page)
            if app:
                break
        if not app:
            browser.close()
            raise SystemExit("The data app didn't load in the org (no page frame after a minute).")
        page.wait_for_timeout(RENDER_WAIT * 1000)
        top = page.query_selector("iframe").bounding_box()["y"]
        height = min(app.evaluate("document.documentElement.scrollHeight"), MAX_HEIGHT)
        page.set_viewport_size({"width": WIDTH, "height": int(top + height + 10)})   # the iframe grows with the window
        page.wait_for_timeout(8000)   # charts redraw at the new size
        height = min(app.evaluate("document.documentElement.scrollHeight"), MAX_HEIGHT)
        page.screenshot(path=path, type="jpeg", quality=82, clip={"x": 0, "y": top, "width": WIDTH, "height": height})
        build = _read_build(seen)
        browser.close()
    kept = _save_build(slug, build)
    cp = C.load_cp(slug, "next")   # re-read: a build may have saved meanwhile
    cp["image"], cp["image_at"] = path, time.strftime("%Y-%m-%d %H:%M")
    if kept:   # the live view in the Web UI runs this build, with AIO answering its queries
        cp["live_build"], cp["live_revision"] = kept, cp.get("revision")
    C.save_cp(slug, "next", cp)
    print(f"Picture of the app saved: {path}", flush=True)
    return path
