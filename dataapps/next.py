"""Tableau Next data apps: Claude writes the app from the semantic model and the demo's story; AIO checks
every query against the model, then creates, publishes and deploys it through the tableau-next-pilot MCP
(the data app tools: create_data_app, edit_data_app, publish_data_app, get_data_app_deploy_status).

Why queries are checked here: the MCP's own query check (check_data_app_queries) runs inside a preview
that only Claude Desktop / claude.ai render, so from AIO (and Claude Code) it stays "pending" forever.
The server still builds and checks the page itself when it publishes.
"""

import html
import json
import os
import re
import time

from dataapps import common as C

import aio_http as requests  # noqa: E402

API = "v65.0"
ALLOWED_IMPORTS = {
    "react",
    "@analytics/data-app-ui-kit/components/react/PageShell",
    "@analytics/data-app-ui-kit/components/react/connected/AppHeader",
    "@analytics/data-app-ui-kit/components/react/connected/FilterPanel",
    "@analytics/data-app-ui-kit/components/react/KpiStrip",
    "@analytics/data-app-ui-kit/components/react/connected/KpiTile",
    "@analytics/data-app-ui-kit/components/react/connected/FindingSection",
    "@analytics/data-app-ui-kit/components/react/ChartRow",
    "@analytics/data-app-ui-kit/components/react/connected/Chart",
    "@analytics/data-app-ui-kit/components/react/connected/DumbbellChart",
    "@analytics/data-app-ui-kit/components/react/connected/DataTable",
    "@analytics/data-app-ui-kit/components/react/CaveatBox",
}
AGG = {"sum": "SUM", "avg": "AVG", "min": "MIN", "max": "MAX", "count": "COUNT"}
AGG_FN = re.compile(r"\b(SUM|AVG|COUNTD?|MIN|MAX|MEDIAN)\s*\(", re.I)
# App filterType -> gateway unifiedFilter operator (the ones verified on the gateway)
FILTER_OPS = {"in": "In", "notIn": "NotIn", "match": "Equals"}
COMPARE_OPS = {">": "GreaterThan", "<": "LessThan"}
MAX_AUTHOR_TRIES = 3
MAX_PUBLISH_FIXES = 2


# ── Org, REST and MCP ─────────────────────────────────────────────────────────

def org_for(profile):
    import transfer_assets as xa
    return xa.Org(profile, allow_browser=False)


def rest(org, method, path, **kw):
    return requests.request(method, f"{org.instance}/services/data/{path}", headers=org.headers(), timeout=180, **kw)


def mcp_for(org):
    import sys
    sys.path.insert(0, os.path.join(C.ROOT, "web-ui"))
    from mcp_client import MCPClient
    client = MCPClient(org.config)
    if not client.available:
        raise SystemExit(f"{org.label} has no MCP login. Authorize MCP for this connection on Connections first.")
    return client


class MCPError(RuntimeError):
    pass


def mcp_call(client, tool, args):
    """Call a data app tool and return its JSON payload; an error result raises MCPError with its text."""
    try:
        res = client.call_tool(tool, args) or {}
    except RuntimeError as e:
        raise MCPError(str(e))
    text = "".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
    if res.get("isError"):
        raise MCPError(text or json.dumps(res)[:800])
    if res.get("structuredContent"):
        return res["structuredContent"]
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {"text": text}


# ── Sources ──────────────────────────────────────────────────────────────────

def sources(profile):
    """Semantic models and workspaces in the org, with the AIO demos built on this connection first."""
    org = org_for(profile)
    r = rest(org, "GET", f"{API}/ssot/semantic/models", params={"limit": 200})
    models = [{"apiName": m["apiName"], "label": html.unescape(m.get("label", m["apiName"]))}
              for m in (r.json().get("items", []) if r.ok else [])]
    r = rest(org, "GET", "v66.0/tableau/workspaces", params={"limit": 200})
    workspaces = [{"id": w["id"], "name": w["name"], "label": html.unescape(w.get("label", w["name"]))}
                  for w in (r.json().get("workspaces", []) if r.ok else [])]
    return {"demos": C.aio_demos("next", profile), "models": models, "workspaces": workspaces,
            "instance": org.instance}


def model_profile(org, sdm):
    """The fields the app can use: dimensions, measures, governed calcs and metrics, the date to trend on."""
    r = rest(org, "GET", f"{API}/ssot/semantic/models/{sdm}", params={"includeModelContent": "true"})
    if not r.ok:
        raise SystemExit(f"Couldn't read semantic model {sdm}: {r.status_code} {r.text[:300]}")
    m = r.json()
    prof = {"sdm": m["apiName"], "label": html.unescape(m.get("label", "")), "dimensions": [], "measures": [],
            "calc_measures": [], "calc_dimensions": [], "metrics": [], "date": None, "entity": None}
    for do in m.get("semanticDataObjects", []):
        obj = do["apiName"]
        for d in do.get("semanticDimensions", []):
            if d.get("dataObjectFieldName") == "entity_id__c":
                prof["entity"] = f"{obj}.{d['apiName']}"   # hidden, but a site map's trucks layer groups by it
            if not d.get("isVisible", True):
                continue
            item = {"ref": f"{obj}.{d['apiName']}", "label": html.unescape(d.get("label", "")),
                    "type": d.get("dataType"), "description": html.unescape(d.get("description", ""))}
            prof["dimensions"].append(item)
            if d.get("dataType") in ("Date", "DateTime") and not prof["date"]:
                prof["date"] = f"[{obj}].[{d['apiName']}]"
        for x in do.get("semanticMeasurements", []):
            if x.get("isVisible", True) and x.get("aggregationType") not in (None, "None"):
                prof["measures"].append({"ref": f"{obj}.{x['apiName']}", "label": html.unescape(x.get("label", "")),
                                         "aggregation": x.get("aggregationType"),
                                         "sentiment": x.get("sentiment", "")})
    for c in m.get("semanticCalculatedMeasurements", []):
        if c.get("isVisible", True):
            prof["calc_measures"].append({"apiName": c["apiName"], "label": html.unescape(c.get("label", "")),
                                          "dataType": c.get("dataType"), "expression": html.unescape(c.get("expression", "")),
                                          "directionality": c.get("directionality", "")})
    for c in m.get("semanticCalculatedDimensions", []):
        if c.get("isVisible", True):
            prof["calc_dimensions"].append({"apiName": c["apiName"], "label": html.unescape(c.get("label", "")),
                                            "dataType": c.get("dataType")})
            if c.get("dataType") in ("Date", "DateTime"):
                prof["date"] = f"[{c['apiName']}]"   # the self-healing Display Date beats the stored date
    for x in m.get("semanticMetrics", []):
        prof["metrics"].append({"apiName": x["apiName"], "label": html.unescape(x.get("label", ""))})
    return prof


# ── App query -> gateway request ───────────────────────────────────────────────

def _wire_field(f):
    alias = f.get("alias")
    if f.get("field"):
        obj, _, name = f["field"].rpartition(".")
        expr = {"tableField": {"tableName": obj, "name": name}} if obj else {"semanticField": {"name": name}}
        out = {"expression": expr, "alias": alias or name}
        if f.get("aggregation"):
            agg = AGG.get(f["aggregation"])
            if not agg:
                raise ValueError(f'aggregation "{f["aggregation"]}" is not one of sum, avg, min, max, count')
            return {**out, "semanticAggregationMethod": f"SEMANTIC_AGGREGATION_METHOD_{agg}", "rowGrouping": False}
        return {**out, "rowGrouping": True}
    if f.get("calculatedFieldApiName"):
        if f.get("role") not in ("measure", "dimension"):
            raise ValueError(f'{f["calculatedFieldApiName"]}: role must be "measure" or "dimension"')
        out = {"expression": {"semanticField": {"name": f["calculatedFieldApiName"]}},
               "alias": alias or f["calculatedFieldApiName"]}
        if f["role"] == "measure":
            return {**out, "semanticAggregationMethod": "SEMANTIC_AGGREGATION_METHOD_USER_AGG", "rowGrouping": False}
        return {**out, "rowGrouping": True}
    if f.get("calculation"):
        if not alias:
            raise ValueError(f'calculation "{f["calculation"][:40]}" needs an alias')
        if f.get("aggregation") or AGG_FN.search(f["calculation"]):
            return {"expression": {"calculatedField": {"name": alias, "expression": f["calculation"], "syntax": "Tua",
                                                       "calculatedMeasureExpression": {"measureOutputType": "SEMANTIC_MEASUREMENT_TYPE_NUMBER"}}},
                    "alias": alias, "semanticAggregationMethod": "SEMANTIC_AGGREGATION_METHOD_USER_AGG", "rowGrouping": False}
        return {"expression": {"calculatedField": {"name": alias, "expression": f["calculation"], "syntax": "Tua",
                                                   "calculatedDimensionExpression": {}}},
                "alias": alias, "rowGrouping": True}
    raise ValueError(f"field {json.dumps(f)[:80]} sets none of field / calculatedFieldApiName / calculation")


def _wire_filter(flt):
    """A gateway filter for an app filter, or None when the gateway form isn't verified (checked without it)."""
    ft, field = flt.get("filterType"), flt.get("field")
    if not isinstance(field, str):
        return None
    if ft in ("in", "notIn"):
        vals = flt.get("values")
        vals = vals if isinstance(vals, list) else [vals]
        return {"fields": [{"model": field}], "operator": FILTER_OPS[ft], "values": [str(v) for v in vals]} if vals else None
    if ft == "match":
        return {"fields": [{"model": field}], "operator": "Equals", "values": [str(flt.get("value"))]}
    if ft == "comparison" and flt.get("operator") in COMPARE_OPS:
        return {"fields": [{"model": field}], "operator": COMPARE_OPS[flt["operator"]], "values": [str(flt.get("value"))]}
    if ft == "nullity":
        return {"fields": [{"model": field}], "operator": "IsNull" if flt.get("isNull", True) else "NotIn", "values": []}
    return None


def to_gateway(kind, q):
    """(gateway body key, body) for an app query, plus the notes on parts not checked."""
    notes = []
    if kind == "metric":
        body = {"modelApiName": q["sourceName"], "submetricDefinition": {"metricApiName": q["metric"]}}
        if q.get("timeGrain"):
            body["timeGrain"] = q["timeGrain"].capitalize()
        if q.get("dimensions"):
            body["additionalDimensions"] = [{"tableFieldReference": {"tableApiName": d.rpartition(".")[0],
                                                                     "fieldApiName": d.rpartition(".")[2]}}
                                            for d in q["dimensions"]]
        if q.get("limit"):
            body["limitOptions"] = {"limit": q["limit"]}
        return "structuredMetricQuery", body, notes
    body = {"fields": [_wire_field(f) for f in q.get("fields", [])]}
    filters = []
    for flt in q.get("filters") or []:
        w = _wire_filter(flt)
        if w:
            filters.append(w)
        else:
            notes.append(f"{flt.get('filterType')} filter on {flt.get('field')} not checked")
    if filters:
        body["filter"] = {"unifiedFilter": {"filters": filters, "filterLogic": " AND ".join(str(i + 1) for i in range(len(filters)))}}
    opts = {}
    if q.get("limit"):
        opts["limitOptions"] = {"limit": q["limit"]}
    if q.get("sort"):
        opts["sortOrders"] = [{"simpleSortOrder": {"sortByFieldAlias": s["alias"], "sortingOrder": s.get("direction", "asc").upper()}}
                              for s in q["sort"]]
    if opts:
        body["options"] = opts
    return "structuredSemanticQuery", body, notes


def run_query(org, sdm, kind, q):
    """Run one app query through the semantic engine gateway: (rows as dicts, error text or None, notes)."""
    try:
        key, body, notes = to_gateway(kind, q)
    except (ValueError, KeyError) as e:
        return [], str(e), []
    r = rest(org, "POST", f"{API}/semantic-engine/gateway",
             json={"semanticModelApiName": sdm, "dataspace": "default", "source": "tua", key: body})
    if r.status_code not in (200, 201):
        try:
            msg = r.json()[0].get("message", r.text)
        except (ValueError, KeyError, IndexError, TypeError):
            msg = r.text
        msg = re.sub(r"TraceId: \S+ ", "", msg)
        return [], msg[:600], notes
    res = r.json().get("queryResults", {})
    meta = res.get("queryMetadata", {}).get("fields", {})
    cols = sorted(meta, key=lambda c: meta[c].get("placeInOrder", 0))
    rows = [dict(zip(cols, [html.unescape(v) if isinstance(v, str) else v for v in row.get("values", [])]))
            for row in res.get("queryData", {}).get("rows", [])]
    return rows, None, notes


# ── Probes: what the data shows, for the findings ────────────────────────────

def _raw_ref(expression):
    """`AVG([Obj].[field])` -> ('AVG', '[Obj].[field]'), so a governed calc can be split by period."""
    m = re.fullmatch(r"\s*(SUM|AVG|MIN|MAX)\(\s*(\[[^\]]+\]\.\[[^\]]+\])\s*\)\s*", expression or "", re.I)
    return (m.group(1).upper(), m.group(2)) if m else (None, None)


def probes(org, prof):
    """Totals, the monthly trend and each dimension's earlier-vs-last-3-months change, as text for Claude."""
    sdm, date = prof["sdm"], prof["date"]
    measures = [{"calculatedFieldApiName": c["apiName"], "role": "measure", "alias": c["apiName"]}
                for c in prof["calc_measures"]][:8]
    if not measures:
        measures = [{"field": m["ref"], "aggregation": "avg" if m["aggregation"] == "Average" else "sum",
                     "alias": m["ref"].rpartition(".")[2]} for m in prof["measures"]][:8]
    out = []
    rows, err, _ = run_query(org, sdm, "semantic", {"sourceName": sdm, "fields": measures})
    out.append(f"Totals: {C.rows_preview(rows) if not err else 'error ' + err}")
    if date:
        q = {"sourceName": sdm, "fields": [{"calculation": f"DATETRUNC('month', {date})", "alias": "month"}] + measures,
             "sort": [{"alias": "month", "direction": "asc"}]}
        rows, err, _ = run_query(org, sdm, "semantic", q)
        out.append(f"Monthly trend: {C.rows_preview(rows, 30) if not err else 'error ' + err}")
    split = []
    for c in prof["calc_measures"][:8]:
        fn, ref = _raw_ref(c["expression"])
        if fn and date:
            split.append((c["apiName"], fn, ref))
    dims = [d for d in prof["dimensions"] if d["type"] not in ("Date", "DateTime")][:6]
    for d in dims:
        alias = d["ref"].rpartition(".")[2]
        if split:
            fields = [{"field": d["ref"], "alias": alias}]
            for api, fn, ref in split:
                fields.append({"calculation": f"{fn}(IF {date} < DATEADD('month', -3, TODAY()) THEN {ref} END)", "alias": f"{api}__before"})
                fields.append({"calculation": f"{fn}(IF {date} >= DATEADD('month', -3, TODAY()) THEN {ref} END)", "alias": f"{api}__last3m"})
        else:
            fields = [{"field": d["ref"], "alias": alias}] + measures
        rows, err, _ = run_query(org, sdm, "semantic", {"sourceName": sdm, "fields": fields, "limit": 50})
        out.append(f"By {d['label']} ({d['ref']}), earlier months vs last 3 months: "
                   f"{C.rows_preview(rows, 50) if not err else 'error ' + err}")
    return "\n".join(out)


# ── Claude writes the app ────────────────────────────────────────────────────

def page_name(app_name):
    return app_name


def author_prompt(prof, probe_text, story, ask, app_name, label, current=None, feedback=None, problems=None):
    fields = {
        "semantic_model": prof["sdm"],
        "dimensions": [{k: d[k] for k in ("ref", "label", "type", "description")} for d in prof["dimensions"]],
        "measures (raw)": prof["measures"],
        "governed_calc_measures": [{k: c[k] for k in ("apiName", "label", "dataType", "directionality")} for c in prof["calc_measures"]],
        "calc_dimensions": prof["calc_dimensions"],
        "governed_metrics": prof["metrics"],
        "date_to_trend_on": prof["date"],
        "entity_id_field": prof.get("entity"),
    }
    parts = [f"App name (spec `name`): {app_name}\nPage file: src/pages/{page_name(app_name)}.tsx "
             f"(default export function {page_name(app_name)})\nApp label: {label}",
             "Semantic model fields:\n" + json.dumps(fields, indent=1),
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
    parts.append('Return one JSON object in a ```json fence: {"label": "...", "description": "the app\'s purpose in '
                 'one sentence (not its tech)", "summary": "2-3 sentences for the presenter: what the page leads with '
                 'and the drill path", "findings": ["..."], "spec": {the whole src/app.spec.json object}, '
                 '"page": "the whole .tsx source"}')
    return "\n\n".join(parts)


def check_app(org, prof, spec, page, app_name):
    """Every problem with Claude's app, or []: spec shape, page imports and ids, and each query's rows."""
    problems, notes = [], []
    if not isinstance(spec, dict) or not isinstance(spec.get("data"), dict):
        return ["spec must be an object with a `data` object"], notes
    if spec.get("name") != app_name:
        spec["name"] = app_name
    spec["specVersion"] = 1
    queries = spec["data"].get("queries") or []
    ids = [q.get("id") for q in queries]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        problems.append(f"duplicate query ids: {sorted(dup)}")
    filter_ids = [(f.get("filter") or {}).get("id") for f in spec["data"].get("filters") or []]
    for f in spec["data"].get("filters") or []:
        flt = f.get("filter") or {}
        if flt.get("sourceName") != prof["sdm"]:
            problems.append(f'filter {flt.get("id")}: sourceName must be "{prof["sdm"]}"')
        bad = set(flt) - {"id", "sourceName", "field", "filterType", "values", "value", "operator", "min", "max",
                          "isNull", "substring", "position", "start", "end", "unit", "amount", "default", "expression"}
        if bad:
            problems.append(f'filter {flt.get("id")}: unknown keys {sorted(bad)}')
        oq = ((f.get("options") or {}).get("options") or {}).get("queryId")
        if oq and oq not in ids:
            problems.append(f'filter {flt.get("id")}: options query "{oq}" is not in the spec')
    # Page: imports, default export, and every id it names
    for imp in re.findall(r"""import\s+[^'"]*?from\s+['"]([^'"]+)['"]""", page):
        if imp.startswith(".") and imp not in ("../components/SiteMap",):
            problems.append(f'import "{imp}": the only local import is "../components/SiteMap"')
        elif not imp.startswith(".") and imp not in ALLOWED_IMPORTS:
            problems.append(f'import "{imp}" is not in the reference list')
    if not re.search(rf"export\s+default\s+function\s+{re.escape(page_name(app_name))}\b", page):
        problems.append(f"the page must `export default function {page_name(app_name)}`")
    for prop, pool, what in (("queryId", ids, "query"), ("trendQueryId", ids, "query"), ("filterId", filter_ids, "filter"),
                             ("optionsId", ids, "query")):
        for ref in re.findall(rf"""\b{prop}\s*[=:]\s*\{{?\s*['"]([^'"]+)['"]""", page):
            if ref not in pool:
                problems.append(f'page uses {prop} "{ref}" but the spec has no {what} with that id')
    if "fetch(" in page or "dangerouslySetInnerHTML" in page:
        problems.append("the page must not call fetch or set raw HTML")
    # Queries: each must run and return rows
    used = set(re.findall(r"""(?:queryId|trendQueryId|optionsId)\s*[=:]\s*\{?\s*['"]([^'"]+)['"]""", page))
    for q in queries:
        inner = (q.get("query") or {}).get("query") or {}
        kind = (q.get("query") or {}).get("kind")
        if kind not in ("semantic", "metric"):
            problems.append(f'query {q.get("id")}: kind must be "semantic" or "metric"')
            continue
        if inner.get("sourceName") != prof["sdm"]:
            problems.append(f'query {q.get("id")}: sourceName must be "{prof["sdm"]}" (the semantic model)')
            continue
        if kind == "metric" and inner.get("sort"):
            problems.append(f'query {q.get("id")}: a metric query cannot sort')
        rows, err, qnotes = run_query(org, prof["sdm"], kind, inner)
        notes += [f'{q.get("id")}: {n}' for n in qnotes]
        if err:
            problems.append(f'query {q.get("id")} failed: {err}')
        elif not rows:
            problems.append(f'query {q.get("id")} returns no rows')
        else:
            q["_rows"] = len(rows)
        if q.get("id") not in used and q.get("id") not in [((f.get("options") or {}).get("options") or {}).get("queryId")
                                                           for f in spec["data"].get("filters") or []]:
            notes.append(f'{q.get("id")}: in the spec but not used on the page')
    for q in queries:
        q.pop("_rows", None)
    return problems, notes


def author(org, prof, slug, app_name, label, story, ask, current=None, feedback=None):
    """Claude writes (or revises) the app; AIO re-asks with the problems until every check passes."""
    system = (C.read_asset("next_reference.md").replace("{APP_NAME}", app_name).replace("{PAGE}", page_name(app_name))
              .replace("{APP_LABEL}", label)
              + "\n\nYou are writing a Tableau Next data app for a Salesforce solution engineer's live demo. Use only "
                "the fields listed, by their exact refs and apiNames. Every number in a headline must come from the "
                "probe results.")
    C.step("probe", "reading what the data shows")
    probe_text = probes(org, prof)
    C.step("probe", "done")
    problems = None
    for attempt in range(1, MAX_AUTHOR_TRIES + 1):
        C.step("author", f"Claude is writing the app (try {attempt} of {MAX_AUTHOR_TRIES})")
        out = C.ask_claude(system, author_prompt(prof, probe_text, story, ask, app_name, label, current, feedback, problems),
                           os.path.join(C.app_dir(slug), "data_app_next_claude.txt"))
        spec, page = out.get("spec"), out.get("page") or ""
        C.step("check", "running every query against the semantic model")
        problems, notes = check_app(org, prof, spec, page, app_name)
        for n in notes:
            print(f"  note: {n}", flush=True)
        if not problems:
            C.step("author", "done")
            C.step("check", "done")
            return out
        print(f"  {len(problems)} problem(s):", flush=True)
        for p in problems:
            print(f"   - {p}", flush=True)
    raise SystemExit("Claude's app still fails the checks after 3 tries (listed above). Try again, or simplify the request.")


# ── Draft, publish, deploy ────────────────────────────────────────────────────

def app_name_for(slug):
    """A valid DeveloperName: a letter first, letters/digits/single underscores, no trailing _, 40 chars max."""
    name = "AIO_" + re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9]+", "_", slug)).strip("_")
    return name[:40].rstrip("_")


def write_draft(client, cp, app):
    """Create the draft on the first build, then write the spec and page as one new revision. Drafts expire some
    time after publishing ("No data app draft …"): a revise then starts a new draft under the same app name,
    which publishes over the deployed app."""
    if cp.get("app_id"):
        try:
            info = mcp_call(client, "read_data_app_file", {"appId": cp["app_id"]})
            cp["revision"] = int(info.get("revision") or (info.get("dataApp") or {}).get("revision") or cp.get("revision", 1))
        except MCPError as e:
            if "No data app draft" not in str(e) and "NOT_FOUND" not in str(e):
                raise
            print(f"  the draft {cp['app_id']} has expired, starting a new draft of {cp['app_name']}", flush=True)
            cp.pop("app_id", None)
    if not cp.get("app_id"):
        # A name another app already has gets the smallest free number (Overview -> Overview2)
        base = cp["app_name"]
        for n in range(1, 6):
            try:
                res = mcp_call(client, "create_data_app", {"name": cp["app_name"], "label": app["label"],
                                                           "sdm": cp["sdm"], "description": app["description"]})
                break
            except MCPError as e:
                if n == 5 or not re.search(r"exist|duplicate|taken|in use", str(e), re.I):
                    raise SystemExit(f"Couldn't create the data app: {e}")
                cp["app_name"] = f"{base[:38]}{n + 1}"
                print(f"  {base} is taken, using {cp['app_name']}", flush=True)
        if cp["app_name"] != base:
            app["page"] = re.sub(rf"\bfunction\s+{re.escape(base)}\b", f"function {cp['app_name']}", app["page"])
        da = res.get("dataApp") or {}
        cp["app_id"], cp["revision"] = da["appId"], int(da.get("revision", 1))
        print(f"  created draft {cp['app_id']} ({cp['app_name']})", flush=True)
    page_path = f"src/pages/{page_name(cp['app_name'])}.tsx"
    spec = dict(app["spec"], name=cp["app_name"], label=app["label"])
    res = mcp_call(client, "edit_data_app", {"appId": cp["app_id"], "baseRevision": cp["revision"], "operations": [
        # AIO's own components ship with every app (written before the page that imports them)
        {"op": "write_file", "path": "src/components/SiteMap.tsx", "content": C.read_asset("next_sitemap.tsx")},
        {"op": "write_file", "path": "src/app.spec.json", "content": json.dumps(spec, indent=2) + "\n"},
        {"op": "write_file", "path": page_path, "content": app["page"]}]})
    cp["revision"] = int((res.get("dataApp") or {}).get("revision", cp["revision"] + 1))
    print(f"  wrote revision {cp['revision']}", flush=True)


def publish(client, cp):
    """Publish the latest revision; returns (ok, build findings text)."""
    for _ in range(4):
        try:
            res = mcp_call(client, "publish_data_app", {"appId": cp["app_id"], "revision": cp["revision"],
                                                        "analyticsWorkspaceId": cp["workspace_id"]})
        except MCPError as e:
            text = str(e)
            if "BUILD_PENDING" in text:
                time.sleep(20)
                continue
            if "BUILD_FAILED" in text or "findings" in text:
                return False, text[:4000]
            raise SystemExit(f"Publish failed: {text[:800]}")
        build = res.get("build") or {}
        if build.get("ok") is False:
            return False, json.dumps(build)[:4000]
        cp["job_id"] = res.get("jobId")
        if res.get("url"):
            cp["url"] = res["url"]
        return True, ""
    raise SystemExit("The server is still building the app after several minutes. Run Build again to retry the publish.")


def wait_deploy(client, cp, budget=600):
    start = time.time()
    while time.time() - start < budget:
        st = mcp_call(client, "get_data_app_deploy_status", {"jobId": cp["job_id"]})
        status = st.get("status")
        if status == "succeeded":
            if st.get("url", "").startswith("http"):
                cp["url"] = st["url"]
            return
        if status == "failed":
            raise SystemExit(f"Deploy failed: {json.dumps(st)[:800]}")
        print(f"  deploy {status}…", flush=True)
        time.sleep(15)
    raise SystemExit("Deploy still running after 10 minutes. Check the workspace in a few minutes.")


def build(profile, sdm, workspace, slug=None, ask="", feedback="", repackage=False):
    """Write (or revise), check, publish and deploy a Tableau Next data app. Prints `[step]` lines.
    repackage=True republishes the recorded app as it is (picks up newer AIO components), no Claude call."""
    org = org_for(profile)
    demo_slug, demo_cp = C.demo_for_source("next", sdm)
    slug = slug or demo_slug or C.slugify(sdm)
    cp = C.load_cp(slug, "next")
    if cp.get("sdm") and cp["sdm"] != sdm:
        raise SystemExit(f"demos/{slug} already has a data app on {cp['sdm']}. Pick another name.")
    C.step("source", f"reading {sdm}")
    prof = model_profile(org, sdm)
    ws = [w for w in sources(profile)["workspaces"] if workspace in (w["name"], w["id"])]
    if not ws:
        raise SystemExit(f"Workspace {workspace} not found in {org.label}.")
    company = (demo_cp or {}).get("company", "")
    cp.update({"profile": profile, "sdm": sdm, "workspace": ws[0]["name"], "workspace_id": ws[0]["id"],
               "demo": demo_slug or "", "instance": org.instance})
    cp.setdefault("app_name", app_name_for(slug))
    label = cp.get("label") or (f"{company} Data App" if company else f"{prof['label']} Data App")
    C.save_cp(slug, "next", cp)
    C.step("source", "done")

    current = None
    if feedback and cp.get("app"):
        current = {"spec": cp["app"]["spec"], "page": cp["app"]["page"]}
    if repackage:
        if not cp.get("app"):
            raise SystemExit(f"No Tableau Next data app recorded in demos/{slug} to republish.")
        app = dict(cp["app"])
    else:
        app = author(org, prof, slug, cp["app_name"], label, C.story_brief(demo_cp), ask, current, feedback or None)
    cp["label"] = app.get("label") or label
    app["label"] = cp["label"]
    app.setdefault("description", f"{prof['label']} data app")

    client = mcp_for(org)
    for attempt in range(MAX_PUBLISH_FIXES + 1):
        C.step("draft", "writing the app")
        write_draft(client, cp, app)
        cp["app"] = {k: app[k] for k in ("spec", "page", "summary", "findings") if k in app}
        C.save_cp(slug, "next", cp)
        C.step("draft", "done")
        C.step("publish", f"building revision {cp['revision']} on the server")
        ok, findings = publish(client, cp)
        if ok:
            break
        print(f"  build check failed:\n{findings[:2000]}", flush=True)
        if attempt == MAX_PUBLISH_FIXES:
            raise SystemExit("The server's build check still fails after 2 fixes (findings above).")
        C.step("author", "Claude is fixing the build findings")
        app = author(org, prof, slug, cp["app_name"], cp["label"], C.story_brief(demo_cp), ask,
                     {"spec": app["spec"], "page": app["page"]}, "Fix these build-check findings from the server:\n" + findings)
        app["label"] = cp["label"]
        app.setdefault("description", f"{prof['label']} data app")
    C.step("publish", "done")
    C.step("deploy", "deploying to the workspace")
    wait_deploy(client, cp)
    C.step("deploy", "done")

    C.step("verify", "checking the workspace")
    url = cp.get("url") or f"/tableau/dataApp/{cp['app_name']}"
    cp["url"] = url if url.startswith("http") else org.instance.replace(".my.salesforce.com", ".lightning.force.com") + url
    r = rest(org, "GET", f"v66.0/tableau/workspaces/{cp['workspace']}/assets", params={"limit": 200})
    assets = r.json().get("workspaceAssets", []) if r.ok else []
    found = [a for a in assets if a.get("name") == cp["app_name"]]
    if found:
        cp["asset_id"] = found[0].get("assetId")
    cp.setdefault("created", [])
    if cp["app_name"] not in cp["created"]:
        cp["created"].append(cp["app_name"])
    cp["published"] = time.strftime("%Y-%m-%d %H:%M")
    C.save_cp(slug, "next", cp)
    C.step("verify", "done" if found else "app not listed in the workspace yet (it can lag a minute)")
    print(f"\nRESULT {json.dumps({'slug': slug, 'url': cp['url'], 'app': cp['app_name'], 'revision': cp['revision'], 'summary': app.get('summary', '')})}")
    return cp


def remove(slug):
    """Delete the data app this slug created (its AnalyticsDashboard record). Nothing else is touched."""
    cp = C.load_cp(slug, "next")
    if not cp.get("app_name"):
        raise SystemExit(f"No Tableau Next data app recorded in demos/{slug}.")
    org = org_for(cp["profile"])
    r = rest(org, "DELETE", f"v66.0/tableau/dashboards/{cp['app_name']}")
    if r.status_code not in (200, 204, 404):
        raise SystemExit(f"Couldn't delete {cp['app_name']}: {r.status_code} {r.text[:300]}")
    print(f"Deleted data app {cp['app_name']}" + (" (already gone)" if r.status_code == 404 else ""))
    os.remove(C.cp_path(slug, "next"))
