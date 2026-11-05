"""
Capture: Sales Insights Package & Deploy exports -> one portable package + data contract.

Maintainer-only. Reads the six dashboard packages exported from the Tableau Next & Slack org
(each holds that dashboard's vizzes plus the full ExtendedSalesInsights SDM), keeps only the
part of the SDM the six dashboards need, and rewrites its data objects from DMOs to
placeholder DLOs. Run again whenever Sales Insights changes.

    python3 -m salesinsights capture --from demos/sales_insights_packages

Writes salesinsights/package/sales_insights_package.json and data_contract.json.
"""

import html
import json
import os
import re
from collections import deque

DASHBOARDS = ["Sales_Performance", "Team_Performance", "Leaderboard",
              "Sales_Stage_Progression", "Sales_Stage_Conversion", "Lead_Analysis"]
HUB = "Opportunity"  # every object must join to this one (directly or through a bridge)
PKG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "package")

# Read-only or org-specific keys the create APIs reject or don't need
STRIP = {"baseModelApiName", "id", "logicalViewId", "createdBy", "createdDate", "lastModifiedBy",
         "lastModifiedDate", "standardDataObjectFieldName", "dataDefinedGoals"}
TYPE_MAP = {"Text": "Text", "Number": "Number", "Currency": "Number", "Percentage": "Number",
            "Date": "Date", "DateTime": "DateTime", "Boolean": "Boolean"}

# Deliberate fixes to source calcs, applied at capture. Keep this list short: everything else is verbatim.
# Semantic-layer string comparison is case-sensitive (verified 2026-11-05), and the data stores flags as
# lowercase 'true'/'false' like the source org, so this one literal never matched (empty Neglected views).
SOURCE_FIXES = {
    "Total_Neglected_Opportunities_RI_clc": [("[Opportunity].[Is_Closed]) = 'False'", "[Opportunity].[Is_Closed]) = 'false'")],
}

QREF = re.compile(r"\[([^\[\]]+)\]\.\[([^\[\]]+)\]")
UREF = re.compile(r"\[([^\[\]]+)\]")


def _clean(o):
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items() if k not in STRIP}
    if isinstance(o, list):
        return [_clean(x) for x in o]
    return o


def _walk(o, fn):
    if isinstance(o, dict):
        fn(o)
        for v in o.values():
            _walk(v, fn)
    elif isinstance(o, list):
        for v in o:
            _walk(v, fn)


class _Model:
    """Index over the source SDM: data objects, logical views, calcs, params, metrics, joins."""

    def __init__(self, comp):
        sm = comp["semanticModel"]
        self.sm = sm
        self.dos = {o["apiName"]: o for o in sm["semanticDataObjects"]}
        self.lvs = {lv["apiName"]: lv for lv in sm.get("semanticLogicalViews", [])}
        self.calcs = {c["apiName"]: c for c in comp["dimensions"] + comp["measurements"]}
        self.calc_kind = {c["apiName"]: "dimensions" for c in comp["dimensions"]}
        self.calc_kind.update({c["apiName"]: "measurements" for c in comp["measurements"]})
        self.params = {p["apiName"]: p for p in sm.get("semanticParameters", [])}
        self.metrics = {m["apiName"]: m for m in comp["metrics"]}
        self.rels = sm.get("semanticRelationships", [])

    def fields_of(self, node):
        if node in self.dos:
            o = self.dos[node]
            return {f["apiName"]: f for f in o.get("semanticDimensions", []) + o.get("semanticMeasurements", [])}
        if node in self.lvs:
            out = {}
            for o in self.lvs[node].get("semanticDataObjects", []):
                for f in o.get("semanticDimensions", []) + o.get("semanticMeasurements", []):
                    out[f["apiName"]] = f
            for u in self.lvs[node].get("semanticUnions", []):
                for mf in u.get("semanticMappedFields", []):
                    out[mf["apiName"]] = mf
                for o in u.get("semanticDataObjects", []):
                    for f in o.get("semanticDimensions", []):
                        out[f["apiName"]] = f
            return out
        return {}


class _Need:
    """What the dashboards need: fields per object, calcs, parameters, metrics."""

    def __init__(self, m):
        self.m = m
        self.fields = {}       # node -> set(field apiName)
        self.calcs = set()
        self.params = set()
        self.metrics = set()
        self.unresolved = set()

    def field(self, obj, fld):
        if not fld:
            return
        if not obj:
            if fld in self.m.calcs:
                self.calc(fld)
            elif fld in self.m.params:
                self.params.add(fld)
            else:
                self.unresolved.add(f"?.{fld}")
            return
        if obj == "Parameters":
            self.params.add(fld)
        elif obj in self.m.dos or obj in self.m.lvs:
            if fld in self.m.fields_of(obj):
                self.fields.setdefault(obj, set()).add(fld)
            elif fld in self.m.calcs:
                self.calc(fld)
            else:
                self.unresolved.add(f"{obj}.{fld}")
        elif fld in self.m.calcs:
            self.calc(fld)
        else:
            self.unresolved.add(f"{obj}.{fld}")

    def calc(self, name):
        if name in self.calcs:
            return
        if name not in self.m.calcs:
            self.unresolved.add(name)
            return
        self.calcs.add(name)
        expr = html.unescape(self.m.calcs[name].get("expression") or "")
        for obj, fld in QREF.findall(expr):
            self.field(obj, fld)
        for ref in UREF.findall(QREF.sub("", expr)):
            if ref in self.m.calcs:
                self.calc(ref)
            elif ref in self.m.params:
                self.params.add(ref)

    def ref(self, r):
        if not r:
            return
        if r.get("calculatedFieldApiName"):
            self.calc(r["calculatedFieldApiName"])
        t = r.get("tableFieldReference")
        if t:
            self.field(t.get("tableApiName"), t.get("fieldApiName"))

    def metric(self, name):
        if name in self.metrics:
            return
        mt = self.m.metrics.get(name)
        if not mt:
            self.unresolved.add("metric:" + name)
            return
        self.metrics.add(name)
        self.ref(mt.get("measurementReference"))
        self.ref(mt.get("timeDimensionReference"))
        for d in mt.get("additionalDimensions") or []:
            self.ref(d)
        for d in (mt.get("insightsSettings") or {}).get("insightsDimensionsReferences") or []:
            self.ref(d)


def _trace_dashboard(need, comp, reqs):
    dash = comp["dashboard"]
    for w in dash["widgets"].values():
        pr = w.get("parameters") or {}
        fo = pr.get("filterOption")
        if fo:
            need.field(fo.get("objectName"), fo.get("fieldName"))
        if w.get("type") == "metric":
            need.metric((w.get("source") or {}).get("name"))
        if w.get("type") == "parameter" and pr.get("parameterName"):
            need.params.add(pr["parameterName"])

        def tok(o):
            ts = o.get("tokenSpec")
            if isinstance(ts, dict):
                if ts.get("metricApiName"):
                    need.metric(ts["metricApiName"])
                else:
                    need.field(ts.get("objectName"), ts.get("fieldName"))
        _walk(w, tok)
    for v in comp["visualizations"].values():
        for f in (v.get("fields") or {}).values():
            if f.get("type") == "Field":
                need.field(f.get("objectName"), f.get("fieldName"))
            elif f.get("type") == "Parameter":
                need.params.add(f.get("fieldName") or f.get("parameterName"))
    for mname in reqs.get("metrics", []):
        need.metric(mname)
    for f in reqs.get("fields", []):
        need.field(f.get("objectName"), f.get("fieldName"))
    for p in reqs.get("listParameters", []):
        need.params.add(p)


def _connect(m, need):
    """Pick the joins: shortest path from every needed object to the hub through source joins.
    Adds bridge objects (e.g. Opportunity_Product for Product). Returns the chosen relationships."""
    allowed = set(m.dos) | {lv for lv in m.lvs if lv in need.fields}
    adj = {}
    for r in m.rels:
        a, b = r["leftSemanticDefinitionApiName"], r["rightSemanticDefinitionApiName"]
        if a in allowed and b in allowed:
            adj.setdefault(a, []).append((b, r))
            adj.setdefault(b, []).append((a, r))
    chosen = {}
    nodes = set(need.fields) | {HUB}
    for start in sorted(nodes):
        if start == HUB:
            continue
        # 0-1 BFS: stepping onto an object we already need is free, a new (bridge) object costs 1,
        # so equal-length paths never pull in tables the dashboards don't read
        prev, cost = {start: None}, {start: 0}
        q = deque([start])
        while q:
            n = q.popleft()
            for nb, r in adj.get(n, []):
                c = cost[n] + (0 if nb in nodes else 1)
                if c < cost.get(nb, 1 << 30):
                    cost[nb], prev[nb] = c, (n, r)
                    (q.appendleft if c == cost[n] else q.append)(nb)
        if HUB not in prev:
            raise SystemExit(f"capture: {start} has no join path to {HUB} in the source SDM")
        n = HUB
        while prev[n]:
            p, r = prev[n]
            chosen[r["apiName"]] = r
            need.fields.setdefault(n, set())
            need.fields.setdefault(p, set())
            n = p
    # Keep every other source join among the chosen objects too (the source query paths)
    for r in m.rels:
        a, b = r["leftSemanticDefinitionApiName"], r["rightSemanticDefinitionApiName"]
        if a in need.fields and b in need.fields:
            chosen[r["apiName"]] = r
    for r in chosen.values():
        for c in r.get("criteria", []):
            for side in ("left", "right"):
                node = r[f"{side}SemanticDefinitionApiName"]
                fld = c[f"{side}SemanticFieldApiName"]
                if c.get(f"{side}FieldType") == "SemanticField" or fld in m.calcs:
                    need.calc(fld)
                else:
                    need.field(node, fld)
    return list(chosen.values())


def _calc_order(m, names):
    """Dependencies first (calcs reference other calcs by bare [name] or [Obj].[name])."""
    deps = {}
    for n in names:
        expr = html.unescape(m.calcs[n].get("expression") or "")
        refs = {f for _, f in QREF.findall(expr)} | set(UREF.findall(QREF.sub("", expr)))
        deps[n] = {r for r in refs if r in names and r != n}
    order, done = [], set()

    def visit(n, stack=()):
        if n in done:
            return
        if n in stack:
            raise SystemExit(f"capture: calc dependency cycle at {n}")
        for d in sorted(deps[n]):
            visit(d, stack + (n,))
        done.add(n)
        order.append(n)
    for n in sorted(names):
        visit(n)
    return order


def _dlo_field(api):
    return api + "__c"


DMO_ONLY = {"standardDataObjectName", "storageDataType"}  # tie a DO to a standard DMO; DLOs reject them
# Keep tableType: "Shared" marks dimension tables (Account, User, ...) that several fact tables join to.
# Without it the multi-fact joins are rejected as cyclic.


def _data_object(m, name, fields):
    o = {k: v for k, v in _clean(m.dos[name]).items() if k not in DMO_ONLY}
    for f in o.get("semanticDimensions", []) + o.get("semanticMeasurements", []):
        for k in DMO_ONLY:
            f.pop(k, None)
    keep = lambda lst: [dict(f, dataObjectFieldName=_dlo_field(f["apiName"])) for f in lst if f["apiName"] in fields]
    o["semanticDimensions"] = keep(o.get("semanticDimensions", []))
    o["semanticMeasurements"] = keep(o.get("semanticMeasurements", []))
    o.update(dataObjectName="{{DLO:%s}}" % name, dataObjectType="Dlo", shouldIncludeAllFields=False)
    return o


def _logical_view(m, name, fields):
    """Union views: members become their own DLO tables. Custom-SQL views copy as-is."""
    lv = _clean(m.lvs[name])
    tables = {}
    for u in lv.get("semanticUnions", []):
        mapped = {mf["apiName"]: mf for mf in u.get("semanticMappedFields", [])}
        want = set()
        for f in fields:
            if f in mapped:
                want |= {x["fieldApiName"] for x in mapped[f]["fields"]}
            else:
                want.add(f)
        u["semanticMappedFields"] = [mf for mf in u.get("semanticMappedFields", []) if mf["apiName"] in fields]
        for mem in u["semanticDataObjects"]:
            kept = [{k: v for k, v in dict(d, dataObjectFieldName=_dlo_field(d["apiName"])).items() if k not in DMO_ONLY}
                    for d in mem.get("semanticDimensions", []) if d["apiName"] in want]
            for k in DMO_ONLY:
                mem.pop(k, None)
            mem.update(semanticDimensions=kept, semanticMeasurements=[], dataObjectType="Dlo",
                       dataObjectName="{{DLO:%s}}" % mem["apiName"], shouldIncludeAllFields=False)
            tables[mem["apiName"]] = kept
    return lv, tables


def _table(name, flds):
    cols = [{"name": "Record_Id", "dataType": "Text", "isPrimaryKey": True}]
    for f in sorted(flds, key=lambda x: x["apiName"]):
        cols.append({"name": f["apiName"], "dataType": TYPE_MAP.get(f.get("dataType"), "Text"),
                     "label": f.get("label", f["apiName"])})
    return {"schema": "si_" + name.lower(), "fields": cols}


def capture(src_dir):
    comps = {}
    for d in DASHBOARDS:
        p = json.load(open(os.path.join(src_dir, d + ".json")))
        comps[d] = (p["components"], p.get("requirements", {}))
    first = comps[DASHBOARDS[0]][0]
    m = _Model(first)
    need = _Need(m)
    vizzes, dashboards = {}, {}
    for d, (comp, reqs) in comps.items():
        _trace_dashboard(need, comp, reqs)
        vizzes.update(comp["visualizations"])
        dashboards[d] = comp["dashboard"]
    rels = _connect(m, need)
    rels = _connect(m, need)  # second pass: calc-dim joins may have pulled in new objects
    if need.unresolved:
        raise SystemExit(f"capture: unresolved references: {sorted(need.unresolved)}")

    data_objects, logical_views, contract = [], [], {}
    for node in sorted(need.fields):
        if node in m.dos:
            o = _data_object(m, node, need.fields[node])
            data_objects.append(o)
            contract[node] = _table(node, o["semanticDimensions"] + o["semanticMeasurements"])
        else:
            lv, tables = _logical_view(m, node, need.fields[node])
            logical_views.append(lv)
            for t, flds in tables.items():
                contract[t] = _table(t, flds)
    calcs = [dict(_clean(m.calcs[n]), _kind=m.calc_kind[n]) for n in _calc_order(m, need.calcs)]
    for c in calcs:
        c["expression"] = html.unescape(c.get("expression") or "")
        for old, new in SOURCE_FIXES.get(c["apiName"], []):
            if old not in c["expression"]:
                raise SystemExit(f"capture: source fix for {c['apiName']} no longer applies; review SOURCE_FIXES")
            c["expression"] = c["expression"].replace(old, new)
    sm = m.sm
    package = {
        "source": {"sdm": sm["apiName"], "label": sm["label"], "dashboards": DASHBOARDS},
        "semanticModel": {"label": "Sales Insights", "description": sm.get("description", ""),
                          "businessPreferences": sm.get("businessPreferences", ""),
                          "dataObjects": data_objects, "logicalViews": logical_views,
                          "parameters": [_clean(m.params[p]) for p in sorted(need.params)],
                          "calcs": calcs,
                          "relationships": [_clean(r) for r in sorted(rels, key=lambda r: r["apiName"])],
                          "metrics": [_clean(m.metrics[x]) for x in sorted(need.metrics)]},
        "visualizations": {k: vizzes[k] for k in sorted(vizzes)},
        "dashboards": {d: dashboards[d] for d in DASHBOARDS},
    }
    os.makedirs(PKG_DIR, exist_ok=True)
    with open(os.path.join(PKG_DIR, "sales_insights_package.json"), "w") as f:
        json.dump(package, f, indent=1, sort_keys=False)
    with open(os.path.join(PKG_DIR, "data_contract.json"), "w") as f:
        json.dump(contract, f, indent=1)

    s = package["semanticModel"]
    print(f"objects: {len(data_objects)} DOs + {len(logical_views)} logical views -> {len(contract)} tables, "
          f"{sum(len(t['fields']) - 1 for t in contract.values())} fields")
    for t, spec in contract.items():
        print(f"  {t:30} {len(spec['fields']) - 1:3} fields")
    print(f"calcs: {len(s['calcs'])}  parameters: {len(s['parameters'])}  metrics: {len(s['metrics'])}  "
          f"relationships: {len(s['relationships'])}")
    print(f"vizzes: {len(vizzes)}  dashboards: {len(dashboards)}")
    print(f"wrote {PKG_DIR}")
    return package, contract
