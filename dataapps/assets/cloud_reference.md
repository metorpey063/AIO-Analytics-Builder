# Writing a Tableau Cloud data app (AIO reference)

A Tableau Cloud data app is a web page packaged as a viz extension inside a workbook. It queries one
published datasource live through the Extensions API (the VizQL Data Service). You write two things:

1. `queries`: a JSON object of named VizQL Data Service queries. AIO runs each one against the
   datasource before it publishes; one that errors or returns no rows fails the build.
2. `app_js`: the page, a short script that calls `AIO.start({...})`. AIO's runtime (`aio.js`) does the
   Extensions API, the filter bar and the charts, so the page only says what to show.

## 1. Queries (VizQL Data Service)

```json
{
  "kpi_fcr":   {"fields": [{"fieldCaption": "First-Contact Resolution", "function": "AVG", "fieldAlias": "fcr"}]},
  "trend_fcr": {"fields": [{"fieldCaption": "Date", "function": "TRUNC_MONTH", "fieldAlias": "month"},
                           {"fieldCaption": "First-Contact Resolution", "function": "AVG", "fieldAlias": "fcr"}]},
  "fcr_by_region": {"fields": [{"fieldCaption": "Sailing Region", "fieldAlias": "region"},
                               {"fieldCaption": "First-Contact Resolution", "function": "AVG", "fieldAlias": "fcr"}]},
  "recent_by_region": {"fields": [{"fieldCaption": "Sailing Region", "fieldAlias": "region"},
                                  {"fieldCaption": "First-Contact Resolution", "function": "AVG", "fieldAlias": "fcr"}],
                       "filters": [{"field": {"fieldCaption": "Date"}, "filterType": "DATE", "periodType": "MONTHS",
                                    "dateRangeType": "LASTN", "rangeN": 3}]}
}
```

- `fieldCaption` is the field name exactly as the datasource lists it.
- Measure functions: `SUM`, `AVG`, `MIN`, `MAX`, `COUNT`, `COUNTD`, `MEDIAN`. Rates and averages use `AVG`; totals `SUM`.
- Date functions: `TRUNC_MONTH`, `TRUNC_QUARTER`, `TRUNC_YEAR`, `TRUNC_WEEK`, `MONTH`, `YEAR`.
- A dimension field has no `function`. Give every field a `fieldAlias` (letters, digits, `_`): rows are keyed by it.
- Calculated field: `{"fieldCaption": "Recent FCR", "calculation": "AVG(IF [Date] >= DATEADD('month', -3, TODAY()) THEN [First-Contact Resolution] END)", "fieldAlias": "recent"}`
  (Tableau calc syntax, fields in brackets by caption). Use it for before/after pairs.
- A calculation's `fieldCaption` must be a NEW name: reusing an existing field's caption (e.g. "Queue Wait (Min)")
  fails with "Field Caption for a Calculation references existing field".
- A monthly trend of a `SUM` measure dips in the current, partial month: trend it as `AVG` per event instead,
  or filter the trend to complete months (`{"field": {"fieldCaption": "Date"}, "filterType": "DATE",
  "periodType": "MONTHS", "dateRangeType": "LASTN", "rangeN": 13}` still includes this month, so prefer AVG).
- Filters: `{"field": {"fieldCaption": "X"}, "filterType": "SET", "values": ["A"]}` or the relative `DATE`
  filter above (`dateRangeType`: `LASTN`, `CURRENT`, `LAST`). The filter bar adds SET filters itself; don't
  add them for the bar's fields.
- The page's filter bar narrows every query, so a query must still make sense with any one value picked.

## 2. The page (`app_js`)

```js
AIO.start({
  title: 'Guest Experience',
  subtitle: 'First-contact resolution, response time and spend by sailing region',
  brand: '#cc0033',                       // optional: the company's primary colour
  filters: ['Sailing Region', 'Service Area', 'Ship'],   // dimension captions for the filter bar
  render: function (app) {
    app.kpis([
      {label: 'First-Contact Resolution', query: 'kpi_fcr', field: 'fcr', format: 'percent',
       trend: {query: 'trend_fcr', x: 'month', y: 'fcr'}},
      {label: 'Avg Response Time', query: 'kpi_resp', field: 'resp', format: 'min', goodDirection: 'down',
       trend: {query: 'trend_resp', x: 'month', y: 'resp'}}
    ]);
    var hero = app.section('First-contact resolution fell to 68.6% in November', 'One region carries most of the drop.');
    app.line(hero, 'fcr_region_trend', {x: 'month', y: 'fcr', series: 'region', format: 'percent', highlight: 'Mediterranean'});
    app.row(function () {
      app.dumbbell(app.section('Mediterranean dropped 25 points', 'Earlier months vs the last 3 months.'),
                   'fcr_shift', {x: 'region', from: 'before', to: 'recent', format: 'percent', fromLabel: 'Earlier', toLabel: 'Last 3 months'});
      app.bar(app.section('Response time is up in the Mediterranean'), 'resp_by_region', {x: 'region', y: 'resp', format: 'min', highlight: 'Mediterranean'});
    });
    app.table(app.section('Service areas, last 3 months'), 'area_detail',
              {columns: [{field: 'area', label: 'Service Area'}, {field: 'fcr', label: 'FCR', format: 'percent'}], sort: 'fcr', dir: 'asc'});
  }
});
```

API (nothing else exists):

- `AIO.start({title, subtitle?, brand?, filters?: [captions], render(app)})`. `render` runs again when a filter changes.
- `app.kpis([{label, query, field, format?, goodDirection?: 'up'|'down', trend?: {query, x, y}}])`: 2–5 tiles.
- `app.section(headline, text?)` returns a body element; pass it to one chart call.
- `app.row(fn)`: sections created inside `fn` sit side by side (use for 2 related charts).
- `app.line(body, queryId, {x, y, series?, format?, highlight?, height?})`: x is a date alias, sorted for you.
- `app.bar(body, queryId, {x, y, format?, sort?: 'desc'|'asc', highlight?})`: horizontal ranked bars.
- `app.dumbbell(body, queryId, {x, from, to, format?, fromLabel?, toLabel?})`: before/after per category.
- `app.map(body, queryId, {label, x, y, size?, color?, zone?, format?, goodDirection?, highlight?, colorLabel?,
  markers?, routes?, trucks?})`: a site map on a 0-100 grid, when the datasource has position fields
  (`<Thing> X` / `<Thing> Y`). Use it as the hero when the ask is about where things are. Layers, each its own query:
  - the main query: one row per place (e.g. Parking Spot) with `AVG` of its X and Y, the measure to shade by
    (e.g. AVG Queue Wait) and, for `zone`, the zone field (e.g. Parking Zone) to draw lot outlines; `highlight`
    a zone value outlines it in red.
  - `markers: {query, label, x, y}`: fixed equipment (e.g. Loader with AVG Loader X / Loader Y), squares.
  - `routes: {query, label?, fromX, fromY, toX, toY, weight?, color?, weightLabel?, colorLabel?}`: traffic between two
    places, drawn along a generated haul-road network (curved roads between lot gates and equipment; each route
    takes the shortest way, each road as thick as its traffic), e.g. grouped by
    Parking Spot and Loader with AVG of both positions, COUNT of cycles as `weight` and AVG Queue Wait as `color`.
    Add a recent-window filter (last 3 months) so the lines show the current problem.
  - `trucks: {query, id, x, y, date, noun?}`: one dot per moving thing at its latest position: group by its id
    field (e.g. Entity ID), the place, AVG of the place's X / Y and `MAX` of Date; AIO keeps each id's latest row.
- `app.table(body, queryId, {columns: [{field, label?, format?}], sort?, dir?, limit?})`.
- `format`: `'percent'` (0.62 → 62.0%), `'number'`, `'currency'`, or a unit word (`'min'`, `'days'`).
- Every `query` / `queryId` is a key of your queries object; every `field`, `x`, `y`, `series`, `from`, `to`
  is a `fieldAlias` in that query.

## 3. Page design rules

- Lead with the answer: KPIs → the hero section (the lead finding) → supporting sections → detail last.
  3 to 6 sections, one per finding. Nothing added to fill space.
- Headlines state the finding with its real numbers from the probe results; never "Overview" or "Key insights".
- Use the story's culprit, drill-down, leading indicator and counter-trend when a story is given; `highlight`
  the culprit segment.
- Plain ES5 JavaScript (no imports, no modules, no `fetch`, no `innerHTML`); only the `AIO` API above.
