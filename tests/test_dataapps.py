"""dataapps: the app-query -> gateway translation, the app checks, and the Cloud .twbx packaging.

No org or network needed (queries are mocked): python3 -m unittest tests.test_dataapps -v
"""
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dataapps import cloud, common, next as nxt  # noqa: E402

SDM = "VV_Demo_Analytics_834"
PROF = {"sdm": SDM, "label": "VV", "dimensions": [], "measures": [], "calc_measures": [], "calc_dimensions": [],
        "metrics": [], "date": "[Display_Date]"}


class Gateway(unittest.TestCase):
    def test_field_kinds(self):
        key, body, notes = nxt.to_gateway("semantic", {"sourceName": SDM, "fields": [
            {"field": "VV_Demo_Fact.sailing_region", "alias": "region"},
            {"field": "VV_Demo_Fact.firstcontact_resolution", "aggregation": "avg", "alias": "a"},
            {"calculatedFieldApiName": "fcr_clc", "role": "measure", "alias": "fcr"},
            {"calculation": "DATETRUNC('month', [Display_Date])", "alias": "month"},
            {"calculation": "AVG([VV_Demo_Fact].[x]) * 100", "alias": "pct"}],
            "sort": [{"alias": "month", "direction": "asc"}], "limit": 10})
        self.assertEqual(key, "structuredSemanticQuery")
        f = body["fields"]
        self.assertEqual(f[0]["expression"], {"tableField": {"tableName": "VV_Demo_Fact", "name": "sailing_region"}})
        self.assertTrue(f[0]["rowGrouping"])
        self.assertEqual(f[1]["semanticAggregationMethod"], "SEMANTIC_AGGREGATION_METHOD_AVG")
        self.assertEqual(f[2]["semanticAggregationMethod"], "SEMANTIC_AGGREGATION_METHOD_USER_AGG")
        self.assertIn("calculatedDimensionExpression", f[3]["expression"]["calculatedField"])   # no aggregate: dimension
        self.assertIn("calculatedMeasureExpression", f[4]["expression"]["calculatedField"])     # AVG(...): measure
        self.assertEqual(body["options"]["sortOrders"][0]["simpleSortOrder"]["sortingOrder"], "ASC")
        self.assertEqual(body["options"]["limitOptions"], {"limit": 10})

    def test_bad_aggregation_is_an_error(self):
        rows, err, _ = nxt.run_query(None, SDM, "semantic", {"sourceName": SDM, "fields": [
            {"field": "O.f", "aggregation": "average", "alias": "x"}]})
        self.assertIn("not one of", err)

    def test_unverified_filters_are_noted_not_sent(self):
        _, body, notes = nxt.to_gateway("semantic", {"sourceName": SDM, "fields": [{"field": "O.d", "alias": "d"}],
                                                     "filters": [{"field": "O.d", "filterType": "in", "values": ["A"]},
                                                                 {"field": "O.dt", "filterType": "relativeDate",
                                                                  "unit": "month", "amount": 3}]})
        self.assertEqual(body["filter"]["unifiedFilter"]["filters"][0]["operator"], "In")
        self.assertEqual(len(body["filter"]["unifiedFilter"]["filters"]), 1)
        self.assertEqual(len(notes), 1)

    def test_metric_query(self):
        key, body, _ = nxt.to_gateway("metric", {"sourceName": SDM, "metric": "fcr_mtc", "timeGrain": "month"})
        self.assertEqual(key, "structuredMetricQuery")
        self.assertEqual(body["submetricDefinition"], {"metricApiName": "fcr_mtc"})
        self.assertEqual(body["timeGrain"], "Month")


class AppName(unittest.TestCase):
    def test_valid_developer_name(self):
        for slug in ("vv_demo", "acme__retention_", "x" * 80, "3m company"):
            name = nxt.app_name_for(slug)
            self.assertRegex(name, r"^[A-Za-z][A-Za-z0-9_]*$")
            self.assertNotIn("__", name)
            self.assertFalse(name.endswith("_"))
            self.assertLessEqual(len(name), 40)


GOOD_PAGE = """import { PageShell } from '@analytics/data-app-ui-kit/components/react/PageShell';
import { KpiTile } from '@analytics/data-app-ui-kit/components/react/connected/KpiTile';
export default function AIO_vv_demo() {
  return <PageShell><KpiTile queryId="kpi" label="X" trendQueryId="trend" /></PageShell>;
}"""


def spec(*ids, filters=None):
    q = lambda i: {"id": i, "query": {"kind": "semantic", "query": {"sourceName": SDM, "fields": [
        {"calculatedFieldApiName": "x_clc", "role": "measure", "alias": "x"}]}}}
    return {"specVersion": 1, "name": "AIO_vv_demo", "data": {"queries": [q(i) for i in ids], "filters": filters or []}}


class NextChecks(unittest.TestCase):
    def check(self, s, page, rows=([{"x": 1}], None, [])):
        with mock.patch.object(nxt, "run_query", return_value=rows):
            return nxt.check_app(None, PROF, s, page, "AIO_vv_demo")[0]

    def test_good_app_passes(self):
        self.assertEqual(self.check(spec("kpi", "trend"), GOOD_PAGE), [])

    def test_missing_query_id(self):
        self.assertTrue(any('"trend"' in p for p in self.check(spec("kpi"), GOOD_PAGE)))

    def test_unknown_import(self):
        page = "import { Foo } from '@analytics/data-app-ui-kit/components/react/Foo';\n" + GOOD_PAGE
        self.assertTrue(any("Foo" in p for p in self.check(spec("kpi", "trend"), page)))

    def test_wrong_source_and_empty_rows(self):
        s = spec("kpi", "trend")
        s["data"]["queries"][0]["query"]["query"]["sourceName"] = "VV_Demo_Fact"
        problems = self.check(s, GOOD_PAGE, rows=([], None, []))
        self.assertTrue(any("sourceName" in p for p in problems))
        self.assertTrue(any("no rows" in p for p in problems))

    def test_query_error_is_reported(self):
        problems = self.check(spec("kpi", "trend"), GOOD_PAGE, rows=([], "Missing reference x", []))
        self.assertTrue(any("Missing reference" in p for p in problems))


CLOUD_JS = """AIO.start({title: 'T', filters: ['Region'], render: function (app) {
  app.kpis([{label: 'A', query: 'kpi', field: 'a', trend: {query: 'trend', x: 'm', y: 'a'}}]);
  app.line(app.section('Headline, with commas', 'And text.'), 'trend', {x: 'm', y: 'a'});
}});"""


class CloudChecks(unittest.TestCase):
    prof = {"id": "ds", "fields": [{"fieldCaption": "Region"}, {"fieldCaption": "A"}]}
    queries = {"kpi": {"fields": [{"fieldCaption": "A", "function": "AVG", "fieldAlias": "a"}]},
               "trend": {"fields": [{"fieldCaption": "Date", "function": "TRUNC_MONTH", "fieldAlias": "m"},
                                    {"fieldCaption": "A", "function": "AVG", "fieldAlias": "a"}]}}

    def check(self, queries, js):
        def fake(site, ds, q):
            return [{f["fieldAlias"]: 1 for f in q["fields"]}], None
        with mock.patch.object(cloud, "run_query", side_effect=fake):
            return cloud.check_app(None, self.prof, queries, js)

    def test_good_app_passes(self):
        # Section headlines and text are not mistaken for query ids
        self.assertEqual(self.check(self.queries, CLOUD_JS), [])

    def test_unknown_query_and_filter_field(self):
        js = CLOUD_JS.replace("'trend', {x", "'nope', {x").replace("['Region']", "['Territory']")
        problems = self.check(self.queries, js)
        self.assertTrue(any('"nope"' in p for p in problems))
        self.assertTrue(any("Territory" in p for p in problems))

    def test_forbidden_calls(self):
        problems = self.check(self.queries, CLOUD_JS + "\nfetch('/x');")
        self.assertTrue(any("fetch" in p for p in problems))


class CloudPackage(unittest.TestCase):
    def test_twbx_has_template_runtime_and_wired_datasource(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(common, "ROOT", tmp):
            twbx = cloud.package("acme_demo", "Acme & Co App", "Acme - Demo", "AcmeDemo",
                                 [{"fieldCaption": "Region", "dataType": "STRING"},
                                  {"fieldCaption": "Rate", "dataType": "REAL"},
                                  {"fieldCaption": "Date", "dataType": "DATETIME"}],
                                 {"kpi": {"fields": []}}, "AIO.start({title:'x', render: function(){}});",
                                 "2026.3.4 (20263.26.1118.1554)", "1.0.0")
            names = zipfile.ZipFile(twbx).namelist()
            pkg = "Packages/com.aio.dataapp.acme-demo/"
            for f in ("manifest.json", "extensions/data-app.trex", "content/index.html", "content/src/aio.js",
                      "content/src/aio.css", "content/src/queries.js", "content/src/app.js",
                      "content/src/tableau.extensions.1.latest.min.js"):
                self.assertIn(pkg + f, names)
            twb = zipfile.ZipFile(twbx).read("Acme & Co App.twb").decode()
            self.assertNotIn("TODO", twb)
            self.assertIn("class='sqlproxy'", twb)
            self.assertIn("dbname='AcmeDemo'", twb)
            self.assertIn("Acme &amp; Co App", twb)
            queries_js = zipfile.ZipFile(twbx).read(pkg + "content/src/queries.js").decode()
            self.assertIn('window.AIO_DATASOURCE = "Acme - Demo"', queries_js)


class History(unittest.TestCase):
    def test_push_history_keeps_the_last_versions(self):
        cp = {"app": {"v": 0}, "published": "t0"}
        for i in range(1, 14):
            common.push_history(cp)
            cp["app"] = {"v": i}
        self.assertEqual(len(cp["history"]), 10)
        self.assertEqual(cp["history"][-1]["app"], {"v": 12})
        self.assertEqual(cp["history"][0]["app"], {"v": 3})

    def test_no_app_no_history(self):
        cp = {}
        common.push_history(cp)
        self.assertNotIn("history", cp)


class Embed(unittest.TestCase):
    def test_connected_app_token_shape(self):
        import base64
        from dataapps import embed
        tok = embed._jwt("client-1", "secret-id", "s3cret", "se@example.com")
        head, body, sig = tok.split(".")
        pad = lambda x: x + "=" * (-len(x) % 4)
        h = json.loads(base64.urlsafe_b64decode(pad(head)))
        b = json.loads(base64.urlsafe_b64decode(pad(body)))
        self.assertEqual((h["alg"], h["kid"], h["iss"]), ("HS256", "secret-id", "client-1"))
        self.assertEqual((b["aud"], b["sub"], b["scp"]), ("tableau", "se@example.com", ["tableau:views:embed"]))
        self.assertTrue(sig)

    def test_origin_forms(self):
        from dataapps import embed
        self.assertEqual(embed._origin_forms("http://localhost:5100/"), {"http://localhost:5100", "localhost:5100"})


class Checkpoints(unittest.TestCase):
    def test_story_brief_names_the_plan(self):
        cp = {"company": "Virgin Voyages", "story": {"headline": "Satisfaction is slipping"},
              "story_config": {"signal_plan": {"culprit": {"dimension": "Sailing Region", "value": "Mediterranean"},
                                               "counter_trend_metric": "Onboard Spend Index"},
                               "metric_config": [{"label": "FCR", "agg": "Average", "sentiment": "up_is_good",
                                                  "unit": "percent"}]}}
        text = common.story_brief(cp)
        self.assertIn("Sailing Region = Mediterranean", text)
        self.assertIn("Onboard Spend Index", text)
        self.assertIn("FCR (Average, higher is better, percent)", text)
        self.assertEqual(common.metric_hints(cp)["FCR"]["agg"], "average")


if __name__ == "__main__":
    unittest.main()


SCENARIO = {
    "company": "Coeur Mining", "title": "Haul Parking", "headline": "Queue wait is up at South Ridge",
    "entity": {"name": "Haul Truck", "prefix": "HT", "count": 12},
    "events": {"name": "Haul Cycle", "per_day": 20, "days": 365},
    "dimensions": [
        {"name": "Truck Class", "values": ["CAT 777G", "CAT 785D"], "per_entity": True},
        {"name": "Loader", "values": ["Loader L1", "Loader L2"]},
        {"name": "Mineral", "derived_from": "Loader", "map": {"Loader L1": "Silver", "Loader L2": "Gold"}},
        {"name": "Parking Spot", "values": ["P-01", "P-02", "P-03", "P-04"]},
        {"name": "Parking Zone", "derived_from": "Parking Spot",
         "map": {"P-01": "Central Lot", "P-02": "Central Lot", "P-03": "South Ridge Lot", "P-04": "South Ridge Lot"}}],
    "layout": {"Parking Spot": {"P-01": [20, 50], "P-02": [25, 50], "P-03": [80, 90], "P-04": [85, 90]},
               "Loader": {"Loader L1": [20, 10], "Loader L2": [70, 10]}},
    "measures": [
        {"label": "Queue Wait (Min)", "agg": "Average", "sentiment": "up_is_bad", "base_range": [3.5, 6.0],
         "distance": {"from": "Parking Spot", "to": "Loader", "per_unit": 0.03}, "is_primary": True},
        {"label": "Cycle Time (Min)", "agg": "Average", "sentiment": "up_is_bad", "base_range": [25, 32]},
        {"label": "Payload Per Cycle (Tonnes)", "agg": "Average", "sentiment": "up_is_good", "base_range": [95, 110]}],
    "signal": {"measure": "Queue Wait (Min)", "culprit": {"dimension": "Parking Zone", "value": "South Ridge Lot"},
               "culprit_detail": {"dimension": "Mineral", "value": "Silver"}, "magnitude": 0.5,
               "onset_months_ago": 3, "counter_trend_metric": "Payload Per Cycle (Tonnes)"}}


class Scenario(unittest.TestCase):
    def test_good_design_has_no_problems(self):
        from dataapps import scenario
        self.assertEqual(scenario.design_problems(SCENARIO), [])

    def test_design_problems_are_caught(self):
        from dataapps import scenario
        bad = json.loads(json.dumps(SCENARIO))
        bad["dimensions"][2]["map"].pop("Loader L2")                     # map misses a source value
        bad["layout"]["Parking Spot"]["P-01"] = [120, 5]                  # off the grid
        bad["signal"]["culprit"]["value"] = "North Lot"                   # not a value
        bad["signal"]["counter_trend_metric"] = "Queue Wait (Min)"        # same as the primary
        bad["events"]["days"] = 90
        problems = " | ".join(scenario.design_problems(bad))
        for text in ("map is missing", "between 0 and 100", "North Lot", "different measure", "at least 300"):
            self.assertIn(text, problems)

    def test_generated_table_is_in_the_fact_schema(self):
        from dataapps import scenario
        df = scenario.generate(SCENARIO, seed=1)
        for col in ("Record ID", "Date", "Day_Offset", "Entity ID", "Mineral", "Parking Zone",
                    "Queue Wait (Min)", "Parking Spot X", "Loader Y"):
            self.assertIn(col, df.columns)
        self.assertTrue(df["Record ID"].is_unique)
        self.assertTrue((df[df["Loader"] == "Loader L1"]["Mineral"] == "Silver").all())
        self.assertEqual(df.groupby("Entity ID")["Truck Class"].nunique().max(), 1)   # per_entity stays fixed

    def test_configs_mark_positions_as_helpers(self):
        from dataapps import scenario
        metric_config, story_config, story = scenario.configs(SCENARIO)
        self.assertTrue(metric_config[0]["is_primary"])
        helpers = [m["label"] for m in metric_config if m.get("no_metric")]
        self.assertEqual(sorted(helpers), ["Loader X", "Loader Y", "Parking Spot X", "Parking Spot Y"])
        self.assertEqual(story_config["dimension_values"]["Parking Zone"], ["Central Lot", "South Ridge Lot"])
        self.assertEqual(story_config["signal_plan"]["culprit"]["value"], "South Ridge Lot")

    def test_the_problem_lands_in_the_culprit(self):
        from dataapps import scenario
        import pandas as pd
        df = scenario.generate(SCENARIO, seed=3)
        recent = df["Date"] >= pd.Timestamp.today() - pd.Timedelta(days=45)
        early = df["Date"] < pd.Timestamp.today() - pd.Timedelta(days=150)
        def change(zone):
            z = df["Parking Zone"] == zone
            return df[z & recent]["Queue Wait (Min)"].mean() / df[z & early]["Queue Wait (Min)"].mean() - 1
        self.assertGreater(change("South Ridge Lot"), 0.2)
        self.assertLess(abs(change("Central Lot")), 0.1)
