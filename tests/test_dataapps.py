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
