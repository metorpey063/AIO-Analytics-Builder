# Writing a Tableau Next data app (AIO reference)

You write two files of a Tableau Next data app: `src/app.spec.json` (the data layer) and the page
`src/pages/{PAGE}.tsx` (React). Everything else (`app.tsx`, `index.html`, styles) comes from the platform
starter and is left alone. AIO runs every query in your spec against the semantic model before it
publishes, and the server builds and checks the page. Distilled from the platform's data app skills
(`app-shape`, `data-app-data-system`, `data-app-visual-system`) and a verified build.

## 1. `src/app.spec.json`

```json
{
  "specVersion": 1,
  "name": "{APP_NAME}",
  "label": "{APP_LABEL}",
  "data": {
    "queries": [ {"id": "kpi_fcr", "query": {"kind": "semantic", "query": { ... AppSemanticQuery ... }}} ],
    "filters": [ {"filter": {...AppFilter...}, "options": {"options": {"queryId": "opt_region"}}} ],
    "parameters": [],
    "fieldLinks": []
  }
}
```

### AppSemanticQuery

```
{ "sourceName": "<SDM apiName>",          // ALWAYS the semantic model apiName, never the data object
  "fields": [AppField, ...],
  "filters": [AppQueryFilter, ...],         // optional, ANDed
  "sort": [{"alias": "<alias>", "direction": "asc"|"desc"}],   // by alias
  "limit": 10 }                             // only for a top N or an options list
```

AppField: set exactly ONE of `field` / `calculatedFieldApiName` / `calculation`, plus `alias` (undotted).

- Raw column: `{"field": "<DataObject>.<field apiName>", "alias": "region"}` (a dimension), or with
  `"aggregation": "sum"|"avg"|"min"|"max"|"count"` (a measure). Those five are the only aggregations.
- Governed calc (preferred for measures; the model lists them): `{"calculatedFieldApiName": "x_clc", "role": "measure", "alias": "x"}`.
  A governed calc dimension: `"role": "dimension"`. `role` is required.
- Calculation: `{"calculation": "<expression>", "alias": "month"}`. Bracketed refs `[DataObject].[field apiName]`.
  A model-level calc dimension (e.g. `Display_Date`) is referenced bare: `[Display_Date]`.
  - Monthly trend axis: `DATETRUNC('month', [Display_Date])` (use the model's display date when it has one).
  - Before/after a recent window as two measures:
    `AVG(IF [Display_Date] >= DATEADD('month', -3, TODAY()) THEN [Obj].[field] END)` (and `<` for before).
  - A formula that calls SUM/AVG/COUNT/COUNTD/MIN/MAX is a measure without `aggregation`.
  - Multiply a 0-1 rate by 100 in a calculation only when it feeds a chart that has no percent format
    (calculation results come back as plain numbers; governed calcs keep their percent format).

A monthly trend of a `sum` measure dips in the current, partial month: trend it with `avg` instead.

A query with only measures returns one row (a KPI). Measures plus dimensions return one row per group.

### AppQueryFilter (inline on a query) / AppFilter (registered in `data.filters`)

| filterType | operands |
|---|---|
| `in` / `notIn` | `values: [...]` |
| `match` | `value` |
| `comparison` | `operator: "<" "<=" ">" ">="`, `value` |
| `range` | `min?`, `max?` |
| `relativeDate` | `unit: "day"|"week"|"month"|"quarter"|"year"`, `amount` |

A registered filter adds `id` and `sourceName` and attaches to every query on that source by itself:
`{"filter": {"id": "f_region", "sourceName": "<SDM>", "field": "<Obj>.<dim>", "filterType": "in", "values": []},
  "options": {"options": {"queryId": "opt_region"}}}` with an options query
`{"id": "opt_region", "query": {"kind": "semantic", "query": {"sourceName": "<SDM>", "fields": [{"field": "<Obj>.<dim>", "alias": "value"}],
  "sort": [{"alias": "value", "direction": "asc"}], "limit": 1000}}}`. Any other filter key is rejected.

### Governed metric query (headline KPI only)

`{"kind": "metric", "query": {"sourceName": "<SDM>", "metric": "<metric apiName>", "timeGrain": "month"}}`.
No `sort`, no parameters. The value column is named after the metric's calc field, not the metric.
Prefer `semantic` with the governed calc for everything; it is simpler to bind.

## 2. The page `src/pages/{PAGE}.tsx`

Default-export one component named `{PAGE}`. Import ONLY these (named exports, exact paths):

```tsx
import { PageShell } from '@analytics/data-app-ui-kit/components/react/PageShell';
import { AppHeader } from '@analytics/data-app-ui-kit/components/react/connected/AppHeader';
import { FilterPanel } from '@analytics/data-app-ui-kit/components/react/connected/FilterPanel';
import { KpiStrip } from '@analytics/data-app-ui-kit/components/react/KpiStrip';
import { KpiTile } from '@analytics/data-app-ui-kit/components/react/connected/KpiTile';
import { FindingSection } from '@analytics/data-app-ui-kit/components/react/connected/FindingSection';
import { ChartRow } from '@analytics/data-app-ui-kit/components/react/ChartRow';
import { Chart } from '@analytics/data-app-ui-kit/components/react/connected/Chart';
import { DumbbellChart } from '@analytics/data-app-ui-kit/components/react/connected/DumbbellChart';
import { DataTable } from '@analytics/data-app-ui-kit/components/react/connected/DataTable';
import { CaveatBox } from '@analytics/data-app-ui-kit/components/react/CaveatBox';
import { SiteMap } from '../components/SiteMap';   // AIO's site map, only when the model has positions
```

Components (props are exact; nothing else type-checks, so a wrong prop is a runtime error):

- `PageShell` `header`, `filters`, `children`, `theme?`. `theme={{ name: 'dark', focusStyle: 'glow' }}` is the dark
  presentation look (other names: `light`, `org`, `press`, `grid`; options `density`, `controlCorner`); add
  `accent: '<brand hex>'` for the company color. `AppHeader` `title`.
- `FilterPanel` `filters={[{kind: 'dimension' as const, filterId, label, optionsId, multiple: true}]}`;
  each `filterId` / `optionsId` must exist in the spec.
- `KpiStrip` holds 2–5 `KpiTile`s, the primary KPI first. `KpiTile` `queryId` (a one-row query), `label`,
  `trendQueryId` (a monthly query of the same measure, ascending), `trendPoints` (how many months the spark and its
  delta pill cover; 4 = this month vs 3 months back, default 12), `sparkGoodDirection="down"` for lower-is-better,
  `accent` (a 4px stripe on the tile; use it on the primary KPI), `insight` (a sentence shown on hover: what moved and
  where), `entryIndex`. The value formats itself from the result (percent calcs show as %). The delta pill compares
  the first and last trend points, so leave the partial current month out of a Sum measure's trend query.
- `FindingSection` `finding` (slug), `region` (`"hero"` | `"row"` | `"detail"`), `arrangement`
  (`"stacked"` | `"pair"` inside a ChartRow | `"right"` | `"band"`), `form` (a word: `"multi-line"`,
  `"dumbbell"`, `"bar"`, `"heatmap"`, `"table"`), `lead` (exactly one, the first section), `headline`
  (the claim with its numbers), `text` (one line), `aside` (e.g. a `CaveatBox`), children = the chart.
  Charts inside a FindingSection take no `title`.
- `ChartRow ratio={[1, 1]}` holds two `FindingSection arrangement="pair"`.
- `Chart` `queryId`, `archetype`, `dimension`, `measure`, `height?`, plus by archetype:
  `bar` (1 dim, 1 measure; ranked), `line` / `area` (date dim, 1 measure), `multiLine` (`series`: a 2nd dim,
  or `secondMeasure`), `stackedBar` (`series`), `heatmap` (`dimension` = rows, `series` = columns),
  `dualAxis` (`secondMeasure` as a line), `donut` (≤5 categories), `scatter` (`secondMeasure`, `sizeMeasure?`),
  `diverging` (signed values), `waterfall`. Props `target` / `targetLabel` draw a reference line.
- **Site map** (when the model has `<Thing> X` / `<Thing> Y` position measures): AIO's own component, which
  ships with every app. `import { SiteMap } from '../components/SiteMap';` then
  `<SiteMap queryId="spot_map" label="spot" x="spot_x" y="spot_y" color="wait" size="cycles" zone="zone"
     highlight="South Ridge Lot" colorLabel="Avg queue wait (min)"
     markers={{queryId: 'loaders', label: 'loader', x: 'loader_x', y: 'loader_y'}}
     routes={{queryId: 'routes', fromX: 'spot_x', fromY: 'spot_y', toX: 'loader_x', toY: 'loader_y', weight: 'cycles', color: 'wait'}}
     trucks={{queryId: 'trucks', id: 'truck', x: 'spot_x', y: 'spot_y', date: 'last_date', noun: 'haul truck'}} />`
  - main query: grouped by the place (and its zone), `avg` of its X and Y, the problem measure, a count/sum for size.
  - `markers`: grouped by the equipment, `avg` of its X / Y. `routes`: grouped by place AND equipment with `avg` of
    both positions, a `count`/`sum` weight and the problem measure (filter to the last 3 months with an inline
    `IF [date] >= DATEADD('month', -3, TODAY())` calc, or a `relativeDate` filter). Roads are drawn for you and every
    route follows them. `trucks`: grouped by `entity_id_field` and the place, `avg` X / Y and `max` of the date.
  - Tooltips on hover/focus: `tooltip={[{field, label, format}]}` on the component (places), on `markers` and on
    `routes` (format: `min`, `L`, `percent`, `number`), plus `routes.fromLabel` / `toLabel` (the route query's place
    and equipment aliases) to name each route. A road's tooltip shows its traffic and the busiest routes on it with
    their fields: give the audience transit/travel time, wait, cycle time, fuel and cycles. `format` sets the color
    measure's format.
  - `lowerIsBetter={false}` when a higher value is good. Props are aliases of those queries. Put it in a
    `FindingSection` as the hero when the ask is about where things are; it brings its own card.
- `DumbbellChart` `queryId`, `dimension`, `from`, `to` (two measures per category: before and after).
- `DataTable` `queryId`, `entity` (the label column alias), `measures` (aliases), `title?`.
- `CaveatBox` children = one sentence.

Column props (`dimension`, `measure`, `series`, `from`, `to`, `entity`, `measures`) are query ALIASES.

## 3. Page design rules

- Lead with the answer. Order: KpiStrip → one hero FindingSection (the lead finding) → supporting sections
  (pairs in ChartRows) → detail last. 3 to 6 sections, one per finding, nothing added to fill space.
- Headlines state the finding with its real numbers from the probe results ("Mediterranean dropped 25 points
  to 57.9%"), never "Overview" / "Key insights". A weak finding gets a plain descriptive title.
- Use the story's culprit, drill-down, leading indicator and counter-trend when a story is given.
- 2–4 filters on the dimensions the story drills into.
- Text is plain business language. Comments are short captions a business user can read (they show in Code view).
- No fetch, no hard-coded data, no field or object names in the page: everything comes from spec query ids.
