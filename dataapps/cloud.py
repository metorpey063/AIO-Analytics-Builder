"""Tableau Cloud data apps: Claude writes the page against AIO's runtime (assets/cloud/aio.js); AIO runs
every query through the VizQL Data Service, packages the .twbx from the tableau-mcp template, publishes
it with TSC and reads the rendered view back as an image.

The site needs Settings → Packages → Allow Packages (the view shows "Packages are not enabled on this
site" without it). Viewers need View + Full Data Query + API Access on the workbook and View + Connect +
API Access on the datasource; the SE who publishes has these as owner.
"""

import json
import os
import random
import re
import shutil
import string
import subprocess
import time
import zipfile

from dataapps import common as C

import aio_http as requests  # noqa: E402

CLOUD = os.path.join(C.ASSETS, "cloud")
MAX_AUTHOR_TRIES = 3
TYPE = {"REAL": "real", "INTEGER": "integer", "STRING": "string", "DATE": "date", "DATETIME": "datetime",
        "BOOLEAN": "boolean"}
SKIP_FIELDS = {"day_offset", "record id", "entity id", "number of records"}


class Site:
    """One Tableau Cloud connection, signed in with its PAT (sign out when done)."""

    def __init__(self, profile):
        import connections as conn
        self.profile = profile
        self.config = conn.load_config(profile, connection_type="tableau_cloud")
        self.base = self.config["tableau"]["server_url"].rstrip("/")
        self.server, self.token, self.site_id = conn.get_tableau_token(self.config)

    def headers(self):
        return {"X-Tableau-Auth": self.token, "Content-Type": "application/json", "Accept": "application/json"}

    def vds(self, endpoint, body):
        return requests.post(f"{self.base}/api/v1/vizql-data-service/{endpoint}", headers=self.headers(), json=body,
                             timeout=120)

    def close(self):
        try:
            self.server.auth.sign_out()
        except Exception:
            pass


def sources(profile):
    """Published datasources and projects on the site, with the AIO demos built on this connection first."""
    import tableauserverclient as TSC
    site = Site(profile)
    try:
        ds = [{"id": d.id, "name": d.name, "project": d.project_name}
              for d in TSC.Pager(site.server.datasources)]
        projects = [{"id": p.id, "name": p.name} for p in TSC.Pager(site.server.projects)]
    finally:
        site.close()
    return {"demos": C.aio_demos("cloud", profile), "datasources": sorted(ds, key=lambda d: d["name"].lower()),
            "projects": sorted(projects, key=lambda p: p["name"].lower())}


# ── Datasource profile and probes ────────────────────────────────────────────

def ds_profile(site, ds_id, hints):
    r = site.vds("read-metadata", {"datasource": {"datasourceLuid": ds_id}})
    if not r.ok:
        raise SystemExit(f"Couldn't read the datasource's fields: {r.status_code} {r.text[:300]}. The PAT's user "
                         "needs API Access on the datasource.")
    fields = r.json().get("data", [])
    prof = {"id": ds_id, "fields": fields, "dimensions": [], "measures": [], "date": None}
    for f in fields:
        cap, dt = f.get("fieldCaption"), f.get("dataType")
        if not cap or cap.lower() in SKIP_FIELDS or cap.endswith(" Target"):
            continue
        if dt in ("DATE", "DATETIME"):
            prof["date"] = prof["date"] or cap
        elif dt in ("REAL", "INTEGER"):
            h = hints.get(cap, {})
            fn = "AVG" if h.get("agg") == "average" else ("SUM" if h.get("agg") == "sum" else
                                                          ("SUM" if f.get("defaultAggregation") == "SUM" else "AVG"))
            prof["measures"].append({"caption": cap, "function": fn, "unit": h.get("unit", ""),
                                     "sentiment": h.get("sentiment", "")})
        elif dt in ("STRING", "BOOLEAN"):
            prof["dimensions"].append(cap)
    return prof


def run_query(site, ds_id, query):
    """(rows, error) for one VizQL Data Service query."""
    r = site.vds("query-datasource", {"datasource": {"datasourceLuid": ds_id}, "query": query})
    if not r.ok:
        try:
            body = r.json()
            msg = body.get("message") or body.get("error", {}).get("message") or r.text
        except ValueError:
            msg = r.text
        return [], f"{r.status_code} {str(msg)[:500]}"
    return r.json().get("data", []), None


def probes(site, prof):
    """Totals, the monthly trend and each dimension's earlier-vs-last-3-months change, as text for Claude."""
    ms = prof["measures"][:8]
    alias = {m["caption"]: re.sub(r"[^A-Za-z0-9]+", "_", m["caption"]).strip("_") for m in ms}
    meas = [{"fieldCaption": m["caption"], "function": m["function"], "fieldAlias": alias[m["caption"]]} for m in ms]
    out = []
    rows, err = run_query(site, prof["id"], {"fields": meas})
    out.append(f"Totals: {C.rows_preview(rows) if not err else 'error ' + err}")
    date = prof["date"]
    if date:
        rows, err = run_query(site, prof["id"], {"fields": [{"fieldCaption": date, "function": "TRUNC_MONTH", "fieldAlias": "month"}] + meas})
        rows = sorted(rows, key=lambda r: str(r.get("month")))
        out.append(f"Monthly trend: {C.rows_preview(rows, 30) if not err else 'error ' + err}")
    for d in prof["dimensions"][:6]:
        fields = [{"fieldCaption": d, "fieldAlias": "value"}]
        for m in ms:
            if date:
                fields.append({"fieldCaption": f"{m['caption']} before", "fieldAlias": f"{alias[m['caption']]}__before",
                               "calculation": f"{m['function']}(IF [{date}] < DATEADD('month', -3, TODAY()) THEN [{m['caption']}] END)"})
                fields.append({"fieldCaption": f"{m['caption']} last3m", "fieldAlias": f"{alias[m['caption']]}__last3m",
                               "calculation": f"{m['function']}(IF [{date}] >= DATEADD('month', -3, TODAY()) THEN [{m['caption']}] END)"})
            else:
                fields.append({"fieldCaption": m["caption"], "function": m["function"], "fieldAlias": alias[m["caption"]]})
        rows, err = run_query(site, prof["id"], {"fields": fields})
        out.append(f"By {d}, earlier months vs last 3 months: {C.rows_preview(rows, 50) if not err else 'error ' + err}")
    return "\n".join(out)


# ── Claude writes the page ───────────────────────────────────────────────────

def author_prompt(prof, probe_text, story, ask, title, current=None, feedback=None, problems=None):
    fields = {"dimensions": prof["dimensions"], "date": prof["date"],
              "measures": [{"caption": m["caption"], "aggregate_with": m["function"], "unit": m["unit"],
                            "lower_is_better": m["sentiment"] == "up_is_bad"} for m in prof["measures"]]}
    parts = [f"App title: {title}", "Datasource fields (use these captions exactly):\n" + json.dumps(fields, indent=1),
             "What the data shows (probe results; `__before` = earlier months, `__last3m` = last 3 months):\n" + probe_text]
    if story:
        parts.append("The demo's story (build the page around it):\n" + story)
    if ask:
        parts.append("What the SE asked for:\n" + ask)
    if current:
        parts.append("The current app (change it, keep what works):\n```json\n" + json.dumps(current)[:60000] + "\n```")
    if feedback:
        parts.append("Change requested:\n" + feedback)
    if problems:
        parts.append("Your last version failed these checks. Fix every one:\n- " + "\n- ".join(problems))
    parts.append('Return one JSON object in a ```json fence: {"title": "...", "summary": "2-3 sentences for the '
                 'presenter: what the page leads with and the drill path", "findings": ["..."], "queries": {id: VDS '
                 'query}, "app_js": "the whole app.js source"}')
    return "\n\n".join(parts)


def check_app(site, prof, queries, app_js):
    problems = []
    if not isinstance(queries, dict) or not queries:
        return ["`queries` must be a non-empty object of id -> query"]
    for qid, q in queries.items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", qid):
            problems.append(f'query id "{qid}" must be letters, digits and _')
        rows, err = run_query(site, prof["id"], q)
        if err:
            problems.append(f"query {qid} failed: {err}")
        elif not rows:
            problems.append(f"query {qid} returns no rows")
        else:
            missing = [f.get("fieldAlias") for f in q.get("fields", []) if f.get("fieldAlias") and f["fieldAlias"] not in rows[0]]
            if missing:
                problems.append(f"query {qid}: aliases {missing} are not in its rows")
    if "AIO.start(" not in app_js:
        problems.append("app_js must call AIO.start({...})")
    for bad in ("fetch(", "innerHTML", "import ", "require(", "eval("):
        if bad in app_js:
            problems.append(f"app_js must not use {bad.strip()}")
    # Query ids: `query: 'id'` (KPIs, trends) and the id before a chart's options (`'id', {x: …}`)
    refs = re.findall(r"""\bquery\s*:\s*['"]([^'"]+)['"]""", app_js)
    refs += re.findall(r"""['"]([^'"]+)['"]\s*,\s*\{\s*['"]?(?:x|columns|from)['"]?\s*:""", app_js)
    for ref in refs:
        if ref not in queries:
            problems.append(f'app_js uses query "{ref}" but `queries` has no such id')
    caps = {f.get("fieldCaption") for f in prof["fields"]}
    m = re.search(r"filters\s*:\s*\[([^\]]*)\]", app_js)
    for cap in re.findall(r"""['"]([^'"]+)['"]""", m.group(1) if m else ""):
        if cap not in caps:
            problems.append(f'filter bar field "{cap}" is not a field of the datasource')
    if shutil.which("node"):
        tmp = os.path.join(C.ROOT, "demos", ".dataapp_check.js")
        _write(tmp, app_js)
        r = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
        os.remove(tmp)
        if r.returncode:
            problems.append("app_js has a syntax error: " + r.stderr.strip().splitlines()[-1][:300])
    return problems


def author(site, prof, slug, title, story, ask, current=None, feedback=None):
    system = (C.read_asset("cloud_reference.md") + "\n\nYou are writing a Tableau Cloud data app for a Salesforce "
              "solution engineer's live demo. Use only the fields listed, by their exact captions. Every number in a "
              "headline must come from the probe results.")
    C.step("probe", "reading what the data shows")
    probe_text = probes(site, prof)
    C.step("probe", "done")
    problems = None
    for attempt in range(1, MAX_AUTHOR_TRIES + 1):
        C.step("author", f"Claude is writing the app (try {attempt} of {MAX_AUTHOR_TRIES})")
        out = C.ask_claude(system, author_prompt(prof, probe_text, story, ask, title, current, feedback, problems),
                           os.path.join(C.app_dir(slug), "data_app_cloud_claude.txt"))
        C.step("check", "running every query against the datasource")
        problems = check_app(site, prof, out.get("queries"), out.get("app_js") or "")
        if not problems:
            C.step("author", "done")
            C.step("check", "done")
            return out
        print(f"  {len(problems)} problem(s):", flush=True)
        for p in problems:
            print(f"   - {p}", flush=True)
    raise SystemExit("Claude's app still fails the checks after 3 tries (listed above). Try again, or simplify the request.")


# ── Package and publish ──────────────────────────────────────────────────────

def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _esc(v):
    return (str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("'", "&apos;")
            .replace('"', "&quot;"))


def _fill(text, ids):
    for k, v in ids.items():
        text = text.replace(k, v if k == "TODO-MANIFEST-ID" else _esc(v))
    if "TODO" in text:
        raise RuntimeError("a template placeholder was left unfilled")
    return text


def _wire_datasource(twb, ds_name, content_url, fields):
    """Point the template workbook at the published datasource (a sqlproxy connection, like Desktop does)."""
    key = "sqlproxy." + "".join(random.choices(string.ascii_lowercase + string.digits, k=22))
    recs, cols, insts = [], [], []
    for i, f in enumerate(fields):
        n, dt = f["fieldCaption"], TYPE.get(f.get("dataType"), "string")
        meas = dt in ("real", "integer")
        typ = "quantitative" if meas else ("ordinal" if dt in ("date", "datetime") else "nominal")
        agg = "Sum" if meas else "Count"
        recs.append(f"""          <metadata-record class='column'>
            <remote-name>{_esc(n)}</remote-name><remote-type>{5 if meas else 129}</remote-type>
            <local-name>[{_esc(n)}]</local-name><parent-name>[sqlproxy]</parent-name><remote-alias>{_esc(n)}</remote-alias>
            <ordinal>{i}</ordinal><layered>true</layered><local-type>{dt}</local-type><aggregation>{agg}</aggregation>
            <contains-null>true</contains-null>
            <attributes><attribute datatype='integer' name='field-type'>1</attribute><attribute datatype='integer' name='role'>{1 if meas else 0}</attribute></attributes>
          </metadata-record>""")
        role = "measure" if meas else "dimension"
        cols.append(f"            <column aggregation='{agg}' datatype='{dt}' name='[{_esc(n)}]' role='{role}' type='{typ}' />")
        inst = f"[sum:{_esc(n)}:qk]" if meas else f"[none:{_esc(n)}:nk]"
        insts.append(f"            <column-instance column='[{_esc(n)}]' derivation='{'Sum' if meas else 'None'}' "
                     f"name='{inst}' pivot='key' type='{typ}' />")
    root_ds = f"""<datasources>
    <datasource caption='{_esc(ds_name)}' inline='true' name='{key}' version='18.1'>
      <repository-location id='{_esc(content_url)}' path='/datasources' revision='1.0' />
      <connection channel='https' class='sqlproxy' dbname='{_esc(content_url)}' directory='dataserver' server-ds-friendly-name='{_esc(ds_name)}' username=''>
        <relation type='collection'><relation connection='{key}' name='sqlproxy' table='[sqlproxy]' type='table' /></relation>
        <metadata-records>
{chr(10).join(recs)}
        </metadata-records>
      </connection>
    </datasource>
  </datasources>"""
    view_ds = f"""<datasources>
            <datasource caption='{_esc(ds_name)}' name='{key}' />
          </datasources>
          <datasource-dependencies datasource='{key}'>
{chr(10).join(cols)}
{chr(10).join(insts)}
          </datasource-dependencies>"""
    i = twb.find("<worksheets>")
    return twb[:i].replace("<datasources />", root_ds, 1) + twb[i:].replace("<datasources />", view_ds, 1)


def package(slug, title, ds_name, content_url, fields, queries, app_js, source_build, version):
    """Build {slug} data app .twbx: the template workbook + manifest, AIO's runtime, the queries and the page."""
    pid = f"com.aio.dataapp.{re.sub(r'[^a-z0-9]+', '-', slug.lower()).strip('-')}"
    ids = {"TODO-MANIFEST-ID": pid, "TODO-MANIFEST-VERSION": version, "TODO App Name": title,
           "TODO Sheet Name": title, "TODO Author Name": "AIO Analytics Builder", "TODO-SOURCE-BUILD": source_build}
    out = os.path.join(C.app_dir(slug), "data_app_cloud")
    shutil.rmtree(out, ignore_errors=True)
    pkg = os.path.join(out, "ws", "Packages", pid)
    os.makedirs(os.path.join(pkg, "extensions"))
    os.makedirs(os.path.join(pkg, "content", "src"))
    twb = _wire_datasource(_fill(_read(os.path.join(CLOUD, "Data_App_Name.twb")), ids), ds_name, content_url, fields)
    _write(os.path.join(out, "ws", f"{title}.twb"), twb)
    _write(os.path.join(pkg, "manifest.json"), _fill(_read(os.path.join(CLOUD, "manifest.json")), ids))
    _write(os.path.join(pkg, "extensions", "data-app.trex"),
        _fill(_read(os.path.join(CLOUD, "data-app.trex")), ids))
    content = os.path.join(pkg, "content")
    _write(os.path.join(content, "index.html"),
        "<!doctype html>\n<html lang=\"en\">\n  <head>\n    <meta charset=\"utf-8\" />\n"
        "    <link rel=\"stylesheet\" href=\"src/aio.css\" />\n  </head>\n  <body>\n    <div id=\"app\"></div>\n"
        "    <script src=\"src/tableau.extensions.1.latest.min.js\"></script>\n    <script src=\"src/aio.js\"></script>\n"
        "    <script src=\"src/queries.js\"></script>\n    <script src=\"src/app.js\"></script>\n  </body>\n</html>\n")
    for f in ("aio.js", "aio.css", "tableau.extensions.1.latest.min.js"):
        shutil.copy(os.path.join(CLOUD, f), os.path.join(content, "src", f))
    _write(os.path.join(content, "src", "queries.js"),
        "// The queries this app runs, checked against the datasource by AIO before publishing\n"
        f"window.AIO_DATASOURCE = {json.dumps(ds_name)};\nwindow.AIO_QUERIES = {json.dumps(queries, indent=2)};\n")
    _write(os.path.join(content, "src", "app.js"), app_js)
    twbx = os.path.join(C.app_dir(slug), f"{slug}_data_app.twbx")
    with zipfile.ZipFile(twbx, "w", zipfile.ZIP_DEFLATED) as z:
        for dp, _, files in os.walk(os.path.join(out, "ws")):
            for f in files:
                full = os.path.join(dp, f)
                z.write(full, os.path.relpath(full, os.path.join(out, "ws")))
    return twbx


def packages_allowed(site):
    """False when the site has Packages turned off (Settings → Packages → Allow Packages)."""
    r = requests.get(f"{site.base}/api/exp/sites/{site.site_id}/packages/allowed-origins", headers=site.headers(), timeout=60)
    return not (r.status_code == 403 and "403157" in r.text)


def build(profile, ds_id, project_id, slug=None, ask="", feedback="", repackage=False):
    """Write (or revise), check, package, publish and verify a Tableau Cloud data app. repackage=True
    republishes the recorded app as it is (picks up a newer AIO runtime) without asking Claude again."""
    import tableauserverclient as TSC
    demo_slug, demo_cp = C.demo_for_source("cloud", ds_id)
    site = Site(profile)
    try:
        ds = site.server.datasources.get_by_id(ds_id)
        slug = slug or demo_slug or C.slugify(ds.name)
        cp = C.load_cp(slug, "cloud")
        if cp.get("datasource_id") and cp["datasource_id"] != ds_id:
            raise SystemExit(f"demos/{slug} already has a data app on another datasource. Pick another name.")
        C.step("source", f"reading {ds.name}")
        if not packages_allowed(site):
            raise SystemExit("Packages are turned off on this site, so the app can't render. A site admin turns them on "
                             "in Settings → Packages → Allow Packages, then run Build again.")
        prof = ds_profile(site, ds_id, C.metric_hints(demo_cp))
        company = (demo_cp or {}).get("company", "")
        title = cp.get("title") or (f"{company} Data App" if company else f"{ds.name} Data App")
        cp.update({"profile": profile, "datasource_id": ds_id, "datasource": ds.name, "project_id": project_id,
                   "demo": demo_slug or ""})
        C.save_cp(slug, "cloud", cp)
        C.step("source", "done")

        if repackage:
            if not cp.get("app"):
                raise SystemExit(f"No Tableau Cloud data app recorded in demos/{slug} to republish.")
            app = cp["app"]
        else:
            current = {"queries": cp["app"]["queries"], "app_js": cp["app"]["app_js"]} if feedback and cp.get("app") else None
            app = author(site, prof, slug, title, C.story_brief(demo_cp), ask, current, feedback or None)
        title = cp["title"] = cp.get("title") or app.get("title") or title
        cp["app"] = {k: app[k] for k in ("queries", "app_js", "summary", "findings") if k in app}
        C.save_cp(slug, "cloud", cp)

        C.step("package", "building the workbook")
        info = site.server.server_info.get()
        source_build = f"{info.product_version} ({info.build_number})"
        cp["version"] = f"1.0.{int(cp.get('version', '1.0.0').rsplit('.', 1)[-1]) + 1}" if cp.get("workbook_id") else "1.0.0"
        twbx = package(slug, title, ds.name, ds.content_url, prof["fields"], app["queries"], app["app_js"],
                       source_build, cp["version"])
        C.step("package", "done")

        C.step("publish", "publishing to Tableau Cloud")
        wb = site.server.workbooks.publish(TSC.WorkbookItem(project_id, name=title), twbx, TSC.Server.PublishMode.Overwrite)
        cp.update({"workbook_id": wb.id, "url": wb.webpage_url, "title": title})
        cp.setdefault("created", [])
        if wb.id not in cp["created"]:
            cp["created"].append(wb.id)
        C.save_cp(slug, "cloud", cp)
        C.step("publish", "done")

        C.step("verify", "rendering the view")
        site.server.workbooks.populate_views(wb)
        img = os.path.join(C.app_dir(slug), f"{slug}_data_app.png")
        for attempt in range(3):
            try:
                view = wb.views[0]
                site.server.views.populate_image(view, TSC.ImageRequestOptions(maxage=1, imageresolution="high", viz_width=1400, viz_height=2200))
                with open(img, "wb") as f:
                    f.write(view.image)
                break
            except Exception as e:
                if attempt == 2:
                    print(f"  couldn't render the view: {e}", flush=True)
                time.sleep(10)
        cp["image"] = img if os.path.exists(img) else ""
        cp["published"] = time.strftime("%Y-%m-%d %H:%M")
        C.save_cp(slug, "cloud", cp)
        C.step("verify", "done")
        print(f"\nRESULT {json.dumps({'slug': slug, 'url': cp['url'], 'workbook': wb.id, 'image': bool(cp['image']), 'summary': app.get('summary', '')})}")
        return cp
    finally:
        site.close()


def remove(slug):
    """Delete the workbook this slug published. Nothing else on the site is touched."""
    cp = C.load_cp(slug, "cloud")
    if not cp.get("workbook_id"):
        raise SystemExit(f"No Tableau Cloud data app recorded in demos/{slug}.")
    site = Site(cp["profile"])
    try:
        site.server.workbooks.delete(cp["workbook_id"])
        print(f"Deleted workbook {cp.get('title', cp['workbook_id'])}")
    except Exception as e:
        if "404" not in str(e):
            raise SystemExit(f"Couldn't delete the workbook: {e}")
        print("Workbook already gone")
    finally:
        site.close()
    os.remove(C.cp_path(slug, "cloud"))
