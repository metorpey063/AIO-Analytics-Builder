# CRM Analytics (CRMA / Wave) Demo Build Playbook

> **Source:** contributed by an SE from the ATI Restoration demo build (2026-11). Patterns were derived against one live org. Treat the crash list (§4) as defensive rules: some items may be specific to that org's CRMA runtime. AIO's current CRMA output (one dataset + one dashboard from `crma_golden_template.json`) uses only a small part of this; the rest is the reference for a future polished CRMA mode (see ROADMAP.md). Short versions of the API rules are in CLAUDE.md → Known Pitfalls → CRM Analytics.

Hard-won patterns from building the ATI Restoration demo (4 branded dashboards, 5 reusable
LWCs, recipe + 5 datasets, record page, quick actions, flows, a branded Lightning app).
Follow this to build a **polished** CRMA demo first-time-right and minimize review cycles.

**Everything here is REST Metadata/Analytics API via `connections.py` + `close_loop.deploy_metadata`.**
All dashboard/lens/widget shapes below were derived by iterating against the live API — trust them.

---

## 0. Golden rules (read first)
1. **Build with deterministic Python scripts, not ad-hoc JSON.** One script per phase; re-runnable; each edit reproduces the asset. The user WILL iterate ~10×; a script that rebuilds in seconds is the whole game.
2. **Update dashboards IN PLACE (PATCH), never re-create.** Re-POST auto-suffixes the dev name (`X1`) and breaks nav links. See §3.
3. **This org white-screens on certain widgets.** Know the crash list (§4) before adding filters.
4. **Custom LWCs render reliably here; several "native" things don't.** When native CRMA can't do it (chevrons, record links, inline edit, conditional row color, rich cards), reach for an `analytics__Dashboard` LWC (§8) — it's the single highest-leverage tool.
5. **The user is the render oracle.** The POST succeeding ≠ it renders. After each build, give the dashboard URL and ask them to confirm render + the specific behavior. Many issues (centerText overlap, squished text, faceting) are only visible at runtime.
6. **Bake every approved tweak back into the builder** so the next rebuild doesn't regress it. Read the user's hand-edited asset via GET and sync the code to it.

---

## 1. Build workflow & scripts
Phase order (each a script in `demos/<slug>/`):
1. `metadata_objects.py` — custom objects + fields + standard-object fields (Metadata API zip).
2. `grant_access.py` — FLS via a permission set (assign to BOTH the Integration User *and* the demo/admin user — see §9).
3. `generate_and_load.py` — synthetic data (InsightsExternalData upload / CRM upsert).
4. `build_recipe.py` — R3 recipe over the live objects → datasets (§2).
5. `build_branded.py` — the dashboards (§3, §5, §10). One `BUILDERS`/`TARGETS` registry; `main()` builds one target by arg.
6. `build_lens.py` — saved lenses (§7).
7. `deploy_lwc.py` — zips ALL `lwc/*` bundles and deploys (§8).
8. `deploy_actions.py` / `deploy_flows.py` / `deploy_layout.py` / `deploy_app.py` — record-level (§9).

`deploy_metadata(inst, h, {path: content}, check_only, timeout)` zips+deploys any metadata type and polls; raises with the component failures (read them — they're precise).

---

## 2. Recipe & datasets (R3 via `/wave/recipes`)
- Read live objects via `SFDC_LOCAL` connected datasets; compute derived fields IN-recipe.
- **Each R3 Formula node defines exactly ONE field** — chain single-field formula nodes (the UI errors "node defines N fields" otherwise).
- **SAQL `sum(case when...)` is NOT allowed** — add numeric 0/1 flag fields in the recipe (`Won_Num` etc.) and `sum` those.
- Filter on a **field that only exists on demo records** (e.g. a custom `Region__c` null on pre-existing org rows) to scope cleanly.
- Pre-aggregate 1:1 (e.g. financials to one row per job) to **avoid join fan-out**.
- **Carry the real 18-char record Id** in every dataset (`Job_Id`, `Opportunity_Id`, …) for the action framework + LWC record links.
- Recipe runs as the **Integration User** — grant it FLS on the custom fields or the digest can't read them.
- Derived fields that pay off later: a **colored-dot status** text field (`'🟢 On Track'`…), a **numeric severity rank** (`Overdue=0,At Risk=1,On Track=2`) for worst-first sorts, and cumulative SLA-hour measures.
- **Rerunning the recipe changes dataset VERSION ids.** Dashboards referencing datasets by NAME survive; anything referencing `datasetId/versionId` (lenses) must be rebuilt — fetch `currentVersionId` at build time, don't hardcode.

---

## 3. Dashboards via REST (`/wave/dashboards`)
- State = `{steps, widgets, gridLayouts:[{pages:[{widgets:[layout entries]}], style}], layouts:[], filters, dataSourceLinksInfo, widgetStyle}`.
- **Per-widget style** lives on each page-layout entry: `widgetStyle:{backgroundColor,borderColor,borderRadius,borderWidth,borderEdges:[]}` → white rounded cards, navy nav panel, tinted KPI rows.
- Grid: `numColumns:48` for fine control; `style.backgroundColor`/`gutterColor` = light grid (`#E6ECF2`).
- **UPDATE IN PLACE:** nav `link` widgets resolve by dashboard **developer name**. A fresh POST with an existing label auto-suffixes the name (`ATI_Sales_Performance1`) and nav lands on the stale asset; the canonical originals often can't be DELETEd (409, referenced by other dashboards' links). So: find the dashboard whose `name` == the canonical dev name and **`PATCH /wave/dashboards/{id}`** `{name,label,state,folder}`. It's PATCH (PUT → 405). Delete only stray same-label copies whose name isn't canonical.
- Cross-dashboard nav: `link` widget `{destinationType:"dashboard", destinationLink:{name:"<DevName>", namespace:""}}`. To a lens: `destinationType:"lens"`, `destinationLink.name` = lens **asset Id** (`0FK…`).
- A step's compact query: `{"query":{"query": json.dumps({measures,groups,filters}), "version":-1.0}, "type":"aggregateflex", "useGlobal":true, "broadcastFacet":true, "receiveFacetSource":{"mode":"all","steps":[]}, "selectMode":...}`. Aliased measures: `["avg","Field","Alias"]`. Values table: `{"values":[cols], "filters":[], "orders":[{"field","ascending"}], "limit":N}` (orders+limit accepted).
- GET returns query strings **HTML-encoded** (`&quot;`) — `html.unescape()` before `json.loads`. Binding strings (`{{…}}`) aren't valid JSON — don't parse those.

---

## 4. THE CRASH LIST (white-screens / silent fallbacks in this CRMA runtime)
- **`listselector` filter dropdowns white-screen a full dashboard.** 2 header filters are OK; a 3rd on a heavy page crashes it (bisected). Fix: use a **`pillbox`** widget or a custom **LWC segmented filter** instead — different components that render where the dropdown crashes.
- **`visualizationType:"time"`** (time chart) white-screens with filters+charts → use `bar`/`line` grouped by `<date>_Year`/`_Month`.
- **`visualizationType:"donut"` silently FALLS BACK TO A BAR.** For a donut use `"pie"` + `parameters.inner` = 0.6 (hole) + `parameters.centerText`. On a plain pie, centerText overlaps the slices (looks blurry/doubled) — always pair centerText with an inner hole.
- **A `container` widget inside another container's grid area → fuzzy/doubled text.** Keep sub-cards as siblings (adjacent grid areas), never nested.
- **Table cell conditional formatting is UI-ONLY** — `conditionalFormatting` in `columnProperties` is 400-rejected by POST. Use a colored-dot recipe field for scannable status; background fills are a manual one-time UI toggle.
- **Widget/param hygiene:** a number widget needs exactly `{compact,exploreLink,measureField,numberColor,numberSize,showActionMenu,step,textAlignment,title,titleColor,titleSize}` — a stray key (e.g. `textColor`, `numberBold`) white-screens it. `theme` on a table is rejected; tables need `minColumnWidth`/`maxColumnWidth`.
- When something white-screens: bisect with throwaway `ZZ_`-prefixed dashboards (single-widget / full-minus-X / add-one-suspect), user reports render each round, clean up after.

---

## 5. Widget cookbook (polished KPIs/charts/tables)
- **KPI card (icon + value + trend + sparkline):** container + a text/number value, a label, a trend line, and a `line` sparkline (`sparkline=True` → axes/legend off). Compute %Δ with a **compare-table step** (`columns` filtered to last-30 vs prior-30 date windows) + formula columns for pct/color/arrow (`case when pct>0 then green…`, arrow `▲▼▬`). Use **percentage-POINT** deltas (`share_30 - share_60`, suffix " pp") for rate/GP metrics, **relative %** for counts/amounts.
- **Show "%" on a value:** number widgets can't suffix. Render a TEXT widget whose run is the cell binding + a literal: `text([(bind(step,"OnTrackPct")+"%", color,"28px",True)])`, `bind = {{cell(step.result,0,"Col").asString()}}`. Round the measure to 0 decimals.
- **Donut with center count:** `pie` + `inner:0.6` + `centerText: bind(kpis,"ActiveJobs")+" Jobs"`; legend on for category breakdown, or off if side-KPIs carry it.
- **Colored pie members:** `colors:[...]` (alphabetical member order) + `applyConditionalFormatting:true` + `showMeasureTitle:false`.
- **Bar with one color:** `highColor`. Hide a chart's axis titles while keeping axes: set `measureAxis1/2.showTitle:false` + `dimensionAxis.showTitle:false` (axes `showAxis:true`).
- **Table:** `values` step + `table` widget; reduce to priority columns (horizontal scroll if too many); sort worst-first via `orders:[{Health_Rank,asc},{Days,desc}]`; show health as a colored-dot recipe field.
- **Dynamic text that tracks a selection:** a count step filtered by the same selection binding + a number widget, or (better) render the summary **inside the filter LWC** so the label can be color-coded by the selected segment.

---

## 6. Faceting & interactivity
- `state.dataSourceLinksInfo.enableAutomaticLinking:true` → a selection on a step grouped by a dimension auto-facets other same-dataset steps by that dimension.
- **Scope a filter to ONE widget** (so it doesn't degrade KPIs): give the filter step `broadcastFacet:false` and have the target step read the selection via an explicit binding in its `filters`: `["Field", '{{column(<step>.selection, ["Field"]).asObject()}}', "in"]`. Empty selection → CRMA drops the `in` filter → all rows (good default). Step-level default selection can't be set on POST (`selection`/`start` rejected) — rely on the empty default.
- **Cross-filter from an LWC:** bind the LWC to a step GROUPED by the dimension and call `setSelection([row])` (auto-link facets the rest); `setSelection([])` clears. A groupless step can't facet by a dimension — group it, and if you need an overall display value, count-weight the grouped rows back in the LWC.

---

## 7. Lenses (`/wave/lenses`)
Derived by probing; the only shape that works:
- Top-level: `{datasets:[{id}], folder:{id}, label, name, visualizationType, state}`. NO `type`/`queryType`/`versionId`.
- `state` uses the **dashboard-state schema**: only `{steps, widgets, layouts}`.
- Step **key must be the step type** (`"saql"`), and a saql step is minimal `{query, type, selectMode, label}` — extra keys rejected.
- Widget **key must be `<stepId>_chart`**, widget `type:"chart"`.
- A record-list lens uses `visualizationType:"table"` (NOT `valuestable`/`pivottable` → 500). Validate SAQL via `/wave/query` first. Fetch `currentVersionId` at runtime so recipe reruns don't break `load "<dsId>/<versionId>"`.

---

## 8. Custom LWCs in CRMA dashboards (highest-leverage)
**Target `analytics__Dashboard`** (NOT `lightning__AnalyticsDashboard`), with `<targetConfig><hasStep>true</hasStep><property .../></targetConfig>`. Runtime sets `@api results` (array of query rows), `@api metadata`, `@api selection`, `@api selectMode`, `@api setSelection`. Implement `results` as a setter to re-render; it's re-set on every facet (that's how faceting is free).

**Dashboard component-widget JSON** (undocumented — derived):
```json
{"type":"component","parameters":{
  "step":"<stepName>",
  "source":{"name":"<bareDevName>","type":"lightningComponent"},   // runtime prepends c:; type MUST be lightningComponent
  "attributes":{ ...each @api property... }                         // sibling of source, NOT inside it
}}
```
Gotchas: `name`/`namespace`/`componentName` under parameters are all rejected — only `source{name,type}`. Feed measures deterministically with aliased measures + a `measureFields` attribute (don't rely on column order).

**LWC authoring/deploy constraints:**
- A property name can't start with `on` (reserved) — use `siteField` not `onsiteField`.
- Once a component is on a saved dashboard you CANNOT delete/rename a `<property>` — only ADD. Generalize reusable components by **keeping the original property names** and repurposing them.
- `deploy_lwc.py` zips ALL bundles; a compile/delete error in any one fails the whole deploy.
- Internal helper LWCs deploy with `isExposed=false` and no targets.

**What LWCs solved here (reuse these patterns):**
- `atiLifecyclePath` — chevron SLA path (CSS `clip-path`), count-weights grouped rows to overall avg, click a chevron → `setSelection` to cross-filter.
- `atiTop5` — nav "attention" cards; each is an **anchor** `href="{absoluteOrgUrl}/{recordId}" target="_blank"` (NavigationMixin is INERT in the Studio iframe; relative/`_top` links are sandbox-blocked — absolute + new tab works in Studio AND embedded). Inject the org base URL via an attribute.
- `atiHealthFilter` — segmented All/segment filter with live counts + a dynamic, color-coded summary line (renders where listselector dropdowns crash).
- `atiTimeline` — per-record horizontal SLA timeline with Met/Missed chips.
- `atiOppEditTable` — inline-editable `lightning-datatable` (double-click), saves to live records via `updateRecord` from `lightning/uiRecordApi` (**no Apex**); bound step → re-filters with the dashboard. Picklist inline edit needs a **custom datatable type**: a component extending `lightning/datatable` with `static customTypes={picklist:{template,editTemplate,standardCellLayout:true,typeAttributes:[...]}}` (no own .html — inherits the base) + a combobox child that dispatches a `valueselect` composed/bubbling event; the wrapper merges native `cellchange` drafts + picklist drafts into one draft set.
- Caveat: `updateRecord` / `NavigationMixin` may be sandboxed in the bare Analytics Studio preview — they work when the dashboard is embedded in a Lightning page/app.

---

## 9. Record page, actions, flows, app
- **Quick Actions (Update type)** = the reliable, action-framework-referenceable actions. File `quickActions/<Object>.<Name>.quickAction`. `layoutSectionStyle` must be `TwoColumnsLeftToRight` (not OneColumn) and needs **exactly two** `<quickActionLayoutColumns>` — split the fields.
- **Screen Flows** (create related records / branch): DON'T hand-roll — reuse `close_loop_flows.py` primitives (`_flow`, `_head`, `_conn`, `_t`, `_val`, `Ref`, `_record_lookup`). It emits children in the required order + base fields. Hand-rolled XML fails with a misleading "Required field is missing: label" (top-level order is strict, same-type elements must be contiguous, every `<screens>` needs a `<label>`). A record-launched flow needs an input var `recordId`.
- **Flow-type Quick Action:** `{flowDefinition, label, optionsCreateFeedItem, type:Flow}` — only deploys when the referenced flow is in the SAME package; CANNOT be added to a layout's QuickActionList ("You can't add QuickActionType Flow") — put it on the Lightning page via App Builder.
- **Page layout** (`<Object>-<ObjectLabel> Layout`): escape `&` in section labels; the Name field must be `<behavior>Required</behavior>`; related-list name is `<ChildObject>.<LookupField>` (not the `__r` name); related-list `<fields>` are bare field names and must NOT include `Name`; quickActionList names must be object-qualified (`ATI_Job__c.Edit_Job`).
- **"Record shows only 3 fields":** first check **FLS** — custom fields on the layout but not readable by the viewing user show nothing. Assign the demo permission set to the human user too (not just the Integration User). Then it's Lightning layout **cache** — hard refresh. (The server-side layout can be verified by reading `tooling/sobjects/Layout/<id>.Metadata`.)
- **Branded Lightning app:** `CustomApplication` (uiType Lightning, navType Standard) with `<brand><headerColor>#001733</headerColor><shouldOverrideOrgTheme>true</shouldOverrideOrgTheme></brand>` + `<tabs>`. Custom objects need a `CustomTab` (fullName = object api name, `<customObject>true</customObject>` + a `<motif>`). Grant app + tab visibility by deploying a partial Profile (`Admin`) with `applicationVisibilities` + `tabVisibilities` (DefaultOn).

---

## 10. Branding & polish patterns (the formatting that got approved)
Brand constants: navy `#001733` (default font), med-blue `#012C74`, red `#A42123`, white, grid/gutter `#E6ECF2`; green `#2E844A` / amber `#F2B01E` / red `#A42123` for On Track / At Risk / Overdue. Cards: white, `borderRadius:16`, thin grid border. KPI tints: `#EAF2FD` (blue), `#EAF6EE` (green), `#FDF4DC` (amber), `#FBEAEA` (red).
Anatomy that reads as "one system":
- **Left nav panel** (tall med-blue container): logo image at top (uploaded CRMA image, `image:{name,namespace}`), icon + text link per dashboard (icon and text as separate widgets), current one highlighted. A dashboard-specific "attention list" LWC + a "View All →" button can live below the links.
- **Header band:** icon + bold navy title + muted subtitle + an always-current "Last Refreshed" badge (`date_to_string(now(),"MMM dd, yyyy")`) + 2 filters (pillbox/LWC, not a 3rd listselector).
- **KPI row:** icon + big number (with `%`/`$`), label, trend arrow + Δ + "vs prior 30 days", sparkline.
- **Charts** in white rounded cards, ATI colors, axis titles/legend trimmed.
- **Table section:** segmented filter (All + segments w/ counts) + dynamic colored summary + severity-sorted table with colored dots.

---

## 11. Do-by-default (lessons from this build's feedback — bake these in to cut cycles)
These were all explicit corrections; doing them upfront removes rounds:
1. Use the **uploaded logo image**, never a text wordmark.
2. **Consistent dark-navy `#001733` font** everywhere unless conditionally colored.
3. Sparklines: **axes AND title off**. %Δ: **conditional color** (green up / red down) and show it **as a %/pp**.
4. KPI numbers **bold, branded blue**; cards aligned flush to both edges; don't let text squish/cut off (give rows enough height/width).
5. Nav links: **icon separated from the text**, consistent across all dashboards.
6. Reconcile populations: if KPIs are "active jobs", the donut must use the **same filter** (don't mix 195 vs 250).
7. Lifecycle/variance: show **actual vs target + variance**, and don't flag a phase off-target without a **confirmed** SLA.
8. Table: **priority columns only** (no horizontal scroll), **Risk Reason not truncated**, **severity sort**, **colored status dots**, drop raw Id columns (wire record-open as a row action / card link).
9. **Top-N attention list in the nav** (repeater-style → use an LWC), cards **clickable to the record in a new tab**.
10. **Segmented filter with an "All" option + live counts** and a **dynamic summary** whose filter name is color-coded.
11. Keep all four dashboards **cohesive** and **cross-nav working** (PATCH in place, §3).
12. After any rebuild, **re-apply the UI-only bits** the user set (table cell fills) — tell them which, since the API can't.

---

## 12. Pre-ship checklist
- [ ] All dashboards PATCHed in place under canonical names; nav links land on branded versions.
- [ ] No listselector beyond the 2 header filters; filters are pillbox/LWC. Render-verified (no white screen).
- [ ] Donuts are `pie`+`inner`; no nested containers; number widgets have the exact param set.
- [ ] KPIs reconcile with their charts (same population); %/pp + arrows correct.
- [ ] Record Ids carried in datasets; table/card record-open works; actions deployed + referenceable.
- [ ] FLS granted to the demo user (not just Integration User); layout verified server-side; hard-refresh advised.
- [ ] Lenses/LWCs rebuilt after any recipe rerun (version ids change).
- [ ] Branded Lightning app with tabs + visibility; logo + header color.
- [ ] Hand the user URLs and the exact things to render-verify.
