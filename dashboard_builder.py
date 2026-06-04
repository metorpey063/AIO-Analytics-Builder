"""
Tableau Dashboard Builder for AIO Analytics Builder.
Generates a .twbx file (workbook + packaged hyper extract) with:
  - BAN tiles across the top
  - Charts row: horizontal bar, treemap, scatter plot
  - Detail table at the bottom
  - Dashboard layout combining all

Opens in Tableau Desktop for one-click publish to Cloud.
"""

import os
import uuid
import zipfile
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import date


def _pretty_xml(elem):
    rough = ET.tostring(elem, encoding="unicode")
    parsed = minidom.parseString(rough)
    return parsed.toprettyxml(indent="  ", encoding="utf-8")


def _uuid():
    return f"{{{uuid.uuid4()}}}".upper()


DS_NAME = "federated.datasource"


def _build_worksheet(worksheets, sheet_name, ds_caption, columns, instances, mark_class,
                     rows_field, cols_field, hide_gridlines=False, hide_axes=False,
                     text_encoding=None, size_encoding=None, color_encoding=None):
    ws = ET.SubElement(worksheets, "worksheet")
    ws.set("name", sheet_name)

    table = ET.SubElement(ws, "table")

    # <view>
    view = ET.SubElement(table, "view")
    ds_refs = ET.SubElement(view, "datasources")
    ds_ref = ET.SubElement(ds_refs, "datasource")
    ds_ref.set("caption", ds_caption)
    ds_ref.set("name", DS_NAME)

    deps = ET.SubElement(view, "datasource-dependencies")
    deps.set("datasource", DS_NAME)
    for col_def in columns:
        dep_col = ET.SubElement(deps, "column")
        for k, v in col_def.items():
            dep_col.set(k, v)
    for inst_def in instances:
        ci = ET.SubElement(deps, "column-instance")
        for k, v in inst_def.items():
            ci.set(k, v)

    ET.SubElement(view, "aggregation").set("value", "true")

    # <style>
    style = ET.SubElement(table, "style")
    if hide_gridlines:
        sr = ET.SubElement(style, "style-rule")
        sr.set("element", "gridline")
        for scope in ["cols", "rows"]:
            fmt = ET.SubElement(sr, "format")
            fmt.set("attr", "line-visibility")
            fmt.set("scope", scope)
            fmt.set("value", "off")
    if hide_axes:
        sr = ET.SubElement(style, "style-rule")
        sr.set("element", "axis")
        for scope in ["cols", "rows"]:
            fmt = ET.SubElement(sr, "format")
            fmt.set("attr", "display")
            fmt.set("scope", scope)
            fmt.set("value", "false")
        sr2 = ET.SubElement(style, "style-rule")
        sr2.set("element", "worksheet")
        for scope in ["cols", "rows"]:
            fmt = ET.SubElement(sr2, "format")
            fmt.set("attr", "display-field-labels")
            fmt.set("scope", scope)
            fmt.set("value", "false")

    # <panes>
    panes = ET.SubElement(table, "panes")
    pane = ET.SubElement(panes, "pane")
    pane.set("selection-relaxation-option", "selection-relaxation-allow")
    pane_view = ET.SubElement(pane, "view")
    ET.SubElement(pane_view, "breakdown").set("value", "auto")
    mark = ET.SubElement(pane, "mark")
    mark.set("class", mark_class)

    if text_encoding or size_encoding or color_encoding:
        encodings = ET.SubElement(pane, "encodings")
        if text_encoding:
            enc = ET.SubElement(encodings, "text")
            enc.set("column", text_encoding)
        if size_encoding:
            enc = ET.SubElement(encodings, "size")
            enc.set("column", size_encoding)
        if color_encoding:
            enc = ET.SubElement(encodings, "color")
            enc.set("column", color_encoding)

    # <rows> and <cols>
    rows_el = ET.SubElement(table, "rows")
    rows_el.text = rows_field if rows_field else ""
    cols_el = ET.SubElement(table, "cols")
    cols_el.text = cols_field if cols_field else ""

    ET.SubElement(ws, "simple-id").set("uuid", _uuid())
    return ws


def _add_zone(parent, zone_id, name=None, h="100000", w="100000", x="0", y="0",
              zone_type=None, param=None, bg_color=None, border=False, margin=None):
    z = ET.SubElement(parent, "zone")
    z.set("h", h)
    z.set("id", str(zone_id))
    if name:
        z.set("name", name)
    if zone_type:
        z.set("type-v2", zone_type)
    if param:
        z.set("param", param)
    z.set("w", w)
    z.set("x", x)
    z.set("y", y)

    if bg_color or border or margin:
        zs = ET.SubElement(z, "zone-style")
        if bg_color:
            fmt = ET.SubElement(zs, "format")
            fmt.set("attr", "background-color")
            fmt.set("value", bg_color)
        if border:
            fmt = ET.SubElement(zs, "format")
            fmt.set("attr", "border-color")
            fmt.set("value", "#E0E0E0")
            fmt2 = ET.SubElement(zs, "format")
            fmt2.set("attr", "border-style")
            fmt2.set("value", "solid")
            fmt3 = ET.SubElement(zs, "format")
            fmt3.set("attr", "border-width")
            fmt3.set("value", "1")
        if margin:
            fmt = ET.SubElement(zs, "format")
            fmt.set("attr", "margin")
            fmt.set("value", str(margin))
    return z


def build_dashboard_twbx(
    hyper_path: str,
    output_path: str,
    metrics: list[dict],
    primary_metric_field: str,
    secondary_metric_field: str = None,
    date_field: str = "Date",
    dimension_field: str = None,
    detail_dimensions: list[str] = None,
    detail_extra_metrics: list[dict] = None,
    title: str = "Performance Dashboard",
    build_date: str = None,
):
    if build_date is None:
        build_date = date.today().isoformat()
    if secondary_metric_field is None and len(metrics) > 1:
        secondary_metric_field = metrics[1]["field"]
    if detail_dimensions is None:
        detail_dimensions = []
    if detail_extra_metrics is None:
        detail_extra_metrics = []

    hyper_filename = os.path.basename(hyper_path)
    extract_dir = "Data/Extracts"

    # ── Workbook ──────────────────────────────────────────────────────────────
    workbook = ET.Element("workbook")
    workbook.set("xmlns:user", "http://www.tableausoftware.com/xml/user")
    workbook.set("source-build", "2024.1.0")
    workbook.set("source-platform", "mac")
    workbook.set("version", "18.1")
    workbook.set("xml:base", "http://localhost")

    manifest = ET.SubElement(workbook, "document-format-change-manifest")
    for tag in ["SheetIdentifierTracking", "WindowsPersistSimpleIdentifiers"]:
        ET.SubElement(manifest, tag)

    ET.SubElement(workbook, "preferences")

    # ── Datasource ────────────────────────────────────────────────────────────
    datasources = ET.SubElement(workbook, "datasources")
    ds = ET.SubElement(datasources, "datasource")
    ds.set("caption", title)
    ds.set("inline", "true")
    ds.set("name", DS_NAME)
    ds.set("version", "18.1")

    conn = ET.SubElement(ds, "connection")
    conn.set("class", "federated")
    named_conns = ET.SubElement(conn, "named-connections")
    nc = ET.SubElement(named_conns, "named-connection")
    nc.set("caption", "Extract")
    nc.set("name", "hyper.connection")
    inner_conn = ET.SubElement(nc, "connection")
    inner_conn.set("class", "hyper")
    inner_conn.set("dbname", f"{extract_dir}/{hyper_filename}")
    inner_conn.set("default-settings", "yes")
    inner_conn.set("schema", "Extract")
    inner_conn.set("tablename", "Extract")
    relation = ET.SubElement(conn, "relation")
    relation.set("connection", "hyper.connection")
    relation.set("name", "Extract")
    relation.set("table", "[Extract].[Extract]")
    relation.set("type", "table")

    # Column definitions
    col = ET.SubElement(ds, "column")
    col.set("datatype", "date")
    col.set("name", f"[{date_field}]")
    col.set("role", "dimension")
    col.set("type", "ordinal")

    calc = ET.SubElement(ds, "column")
    calc.set("caption", "Display Date")
    calc.set("datatype", "date")
    calc.set("name", "[Calculation_DisplayDate]")
    calc.set("role", "dimension")
    calc.set("type", "ordinal")
    calc_formula = ET.SubElement(calc, "calculation")
    calc_formula.set("class", "tableau")
    calc_formula.set("formula", f"DATEADD('day', DATEDIFF('day', #{build_date}#, [{date_field}]), TODAY())")

    if dimension_field:
        col = ET.SubElement(ds, "column")
        col.set("datatype", "string")
        col.set("name", f"[{dimension_field}]")
        col.set("role", "dimension")
        col.set("type", "nominal")

    for dim in detail_dimensions:
        if dim != dimension_field:
            col = ET.SubElement(ds, "column")
            col.set("datatype", "string")
            col.set("name", f"[{dim}]")
            col.set("role", "dimension")
            col.set("type", "nominal")

    for mc in metrics + detail_extra_metrics:
        col = ET.SubElement(ds, "column")
        col.set("datatype", "real")
        col.set("name", f"[{mc['field']}]")
        col.set("role", "measure")
        col.set("type", "quantitative")
        if "rate" in mc["field"].lower() or "%" in mc.get("label", ""):
            col.set("default-format", "p0%")

    # ── Worksheets ────────────────────────────────────────────────────────────
    worksheets = ET.SubElement(workbook, "worksheets")
    all_sheet_names = []

    # --- BANs ---
    ban_sheet_names = []
    for mc in metrics:
        sheet_name = mc["label"]
        ban_sheet_names.append(sheet_name)
        all_sheet_names.append(sheet_name)

        agg = "Avg" if mc.get("agg", "Average").lower() == "average" else "Sum"
        inst = f"{agg.lower()}:{mc['field']}:qk"

        _build_worksheet(
            worksheets, sheet_name, title,
            columns=[{"datatype": "real", "name": f"[{mc['field']}]", "role": "measure", "type": "quantitative"}],
            instances=[{"column": f"[{mc['field']}]", "derivation": agg, "name": f"[{inst}]", "pivot": "key", "type": "quantitative"}],
            mark_class="Text",
            rows_field="",
            cols_field="",
            hide_axes=True,
            hide_gridlines=True,
            text_encoding=f"[{DS_NAME}].[{inst}]",
        )

    # --- Horizontal Bar Chart ---
    bar_sheet_name = f"{primary_metric_field} by {dimension_field}" if dimension_field else None
    if bar_sheet_name:
        all_sheet_names.append(bar_sheet_name)
        dim_inst = f"none:{dimension_field}:nk"
        metric_inst = f"avg:{primary_metric_field}:qk"

        _build_worksheet(
            worksheets, bar_sheet_name, title,
            columns=[
                {"datatype": "string", "name": f"[{dimension_field}]", "role": "dimension", "type": "nominal"},
                {"datatype": "real", "name": f"[{primary_metric_field}]", "role": "measure", "type": "quantitative"},
            ],
            instances=[
                {"column": f"[{dimension_field}]", "derivation": "None", "name": f"[{dim_inst}]", "pivot": "key", "type": "nominal"},
                {"column": f"[{primary_metric_field}]", "derivation": "Avg", "name": f"[{metric_inst}]", "pivot": "key", "type": "quantitative"},
            ],
            mark_class="Bar",
            rows_field=f"[{DS_NAME}].[{dim_inst}]",
            cols_field=f"[{DS_NAME}].[{metric_inst}]",
        )

    # --- Treemap (dimension sized by primary metric) ---
    treemap_sheet_name = f"{primary_metric_field} Treemap" if dimension_field else None
    if treemap_sheet_name:
        all_sheet_names.append(treemap_sheet_name)
        dim_inst_t = f"none:{dimension_field}:nk"
        metric_inst_t = f"avg:{primary_metric_field}:qk"

        _build_worksheet(
            worksheets, treemap_sheet_name, title,
            columns=[
                {"datatype": "string", "name": f"[{dimension_field}]", "role": "dimension", "type": "nominal"},
                {"datatype": "real", "name": f"[{primary_metric_field}]", "role": "measure", "type": "quantitative"},
            ],
            instances=[
                {"column": f"[{dimension_field}]", "derivation": "None", "name": f"[{dim_inst_t}]", "pivot": "key", "type": "nominal"},
                {"column": f"[{primary_metric_field}]", "derivation": "Avg", "name": f"[{metric_inst_t}]", "pivot": "key", "type": "quantitative"},
            ],
            mark_class="Square",
            rows_field=f"[{DS_NAME}].[{dim_inst_t}]",
            cols_field="",
            size_encoding=f"[{DS_NAME}].[{metric_inst_t}]",
            color_encoding=f"[{DS_NAME}].[{metric_inst_t}]",
        )

    # --- Scatter Plot (primary vs secondary metric by dimension) ---
    scatter_sheet_name = None
    if secondary_metric_field and dimension_field:
        scatter_sheet_name = f"{primary_metric_field} vs {secondary_metric_field}"
        all_sheet_names.append(scatter_sheet_name)
        dim_inst_s = f"none:{dimension_field}:nk"
        m1_inst = f"avg:{primary_metric_field}:qk"
        m2_inst = f"avg:{secondary_metric_field}:qk"

        _build_worksheet(
            worksheets, scatter_sheet_name, title,
            columns=[
                {"datatype": "string", "name": f"[{dimension_field}]", "role": "dimension", "type": "nominal"},
                {"datatype": "real", "name": f"[{primary_metric_field}]", "role": "measure", "type": "quantitative"},
                {"datatype": "real", "name": f"[{secondary_metric_field}]", "role": "measure", "type": "quantitative"},
            ],
            instances=[
                {"column": f"[{dimension_field}]", "derivation": "None", "name": f"[{dim_inst_s}]", "pivot": "key", "type": "nominal"},
                {"column": f"[{primary_metric_field}]", "derivation": "Avg", "name": f"[{m1_inst}]", "pivot": "key", "type": "quantitative"},
                {"column": f"[{secondary_metric_field}]", "derivation": "Avg", "name": f"[{m2_inst}]", "pivot": "key", "type": "quantitative"},
            ],
            mark_class="Circle",
            rows_field=f"[{DS_NAME}].[{m1_inst}]",
            cols_field=f"[{DS_NAME}].[{m2_inst}]",
            text_encoding=f"[{DS_NAME}].[{dim_inst_s}]",
        )

    # --- Detail Table ---
    table_sheet_name = "Detail"
    all_sheet_names.append(table_sheet_name)

    # Build rows as multiple dimensions separated by /
    table_dims = [dimension_field] if dimension_field else []
    table_dims.extend([d for d in detail_dimensions if d != dimension_field])
    if not table_dims:
        table_dims = [dimension_field] if dimension_field else [date_field]

    table_columns = []
    table_instances = []
    rows_parts = []

    for dim in table_dims:
        dtype = "date" if dim == date_field else "string"
        ttype = "ordinal" if dim == date_field else "nominal"
        inst_name = f"none:{dim}:nk" if dtype == "string" else f"none:{dim}:ok"
        table_columns.append({"datatype": dtype, "name": f"[{dim}]", "role": "dimension", "type": ttype})
        table_instances.append({"column": f"[{dim}]", "derivation": "None", "name": f"[{inst_name}]", "pivot": "key", "type": ttype})
        rows_parts.append(f"[{DS_NAME}].[{inst_name}]")

    # Add ALL metrics (main + extra) as text columns
    all_detail_metrics = metrics + detail_extra_metrics
    for mc in all_detail_metrics:
        agg = "Avg" if mc.get("agg", "Average").lower() == "average" else "Sum"
        inst_name = f"{agg.lower()}:{mc['field']}:qk"
        table_columns.append({"datatype": "real", "name": f"[{mc['field']}]", "role": "measure", "type": "quantitative"})
        table_instances.append({"column": f"[{mc['field']}]", "derivation": agg, "name": f"[{inst_name}]", "pivot": "key", "type": "quantitative"})

    rows_field_table = " / ".join(rows_parts) if len(rows_parts) > 1 else rows_parts[0]

    _build_worksheet(
        worksheets, table_sheet_name, title,
        columns=table_columns,
        instances=table_instances,
        mark_class="Text",
        rows_field=rows_field_table,
        cols_field=f"[{DS_NAME}].[:Measure Names]",
        hide_gridlines=True,
    )

    # ── Dashboard ─────────────────────────────────────────────────────────────
    dashboards = ET.SubElement(workbook, "dashboards")
    dash = ET.SubElement(dashboards, "dashboard")
    dash.set("name", title)

    # Style (before size per XSD)
    dash_style = ET.SubElement(dash, "style")
    sr = ET.SubElement(dash_style, "style-rule")
    sr.set("element", "dashboard")
    fmt = ET.SubElement(sr, "format")
    fmt.set("attr", "background-color")
    fmt.set("value", "#F5F5F5")

    size = ET.SubElement(dash, "size")
    size.set("maxheight", "900")
    size.set("maxwidth", "1400")
    size.set("minheight", "900")
    size.set("minwidth", "1400")

    zones = ET.SubElement(dash, "zones")

    # Layout: outer > vert flow > [BAN row, Charts row, Table row]
    outer = _add_zone(zones, 1, zone_type="layout-basic")
    vert = _add_zone(outer, 2, zone_type="layout-flow", param="vert")

    # BAN row
    ban_row = _add_zone(vert, 10, h="12000", zone_type="layout-flow", param="horz")
    ban_w = 100000 // len(ban_sheet_names)
    for i, sn in enumerate(ban_sheet_names):
        _add_zone(ban_row, 20 + i, name=sn, h="12000", w=str(ban_w),
                  x=str(ban_w * i), bg_color="#FFFFFF", border=True, margin=4)

    # Charts row (3 charts side by side)
    chart_names = [n for n in [bar_sheet_name, treemap_sheet_name, scatter_sheet_name] if n]
    charts_row = _add_zone(vert, 40, h="48000", y="12000", zone_type="layout-flow", param="horz")
    chart_w = 100000 // max(len(chart_names), 1)
    for i, cn in enumerate(chart_names):
        _add_zone(charts_row, 50 + i, name=cn, h="48000", w=str(chart_w),
                  x=str(chart_w * i), bg_color="#FFFFFF", border=True, margin=4)

    # Detail table row
    _add_zone(vert, 70, name=table_sheet_name, h="40000", y="60000",
              bg_color="#FFFFFF", border=True, margin=4)

    ET.SubElement(dash, "simple-id").set("uuid", _uuid())

    # ── Windows ───────────────────────────────────────────────────────────────
    windows = ET.SubElement(workbook, "windows")
    windows.set("source-height", "30")

    for sn in all_sheet_names:
        win = ET.SubElement(windows, "window")
        win.set("class", "worksheet")
        win.set("name", sn)
        cards = ET.SubElement(win, "cards")
        edge_left = ET.SubElement(cards, "edge")
        edge_left.set("name", "left")
        strip_l = ET.SubElement(edge_left, "strip")
        strip_l.set("size", "160")
        for ctype in ["pages", "filters", "marks"]:
            ET.SubElement(strip_l, "card").set("type", ctype)
        edge_top = ET.SubElement(cards, "edge")
        edge_top.set("name", "top")
        for sz, ctype in [("2048", "columns"), ("2048", "rows"), ("31", "title")]:
            strip_t = ET.SubElement(edge_top, "strip")
            strip_t.set("size", sz)
            ET.SubElement(strip_t, "card").set("type", ctype)
        ET.SubElement(win, "simple-id").set("uuid", _uuid())

    dash_win = ET.SubElement(windows, "window")
    dash_win.set("class", "dashboard")
    dash_win.set("name", title)
    viewpoints = ET.SubElement(dash_win, "viewpoints")
    for sn in all_sheet_names:
        ET.SubElement(viewpoints, "viewpoint").set("name", sn)
    ET.SubElement(dash_win, "active").set("id", "-1")
    ET.SubElement(dash_win, "simple-id").set("uuid", _uuid())

    # ── Write .twbx ───────────────────────────────────────────────────────────
    twb_xml = _pretty_xml(workbook)
    twb_filename = os.path.splitext(os.path.basename(output_path))[0] + ".twb"

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(twb_filename, twb_xml)
        zf.write(hyper_path, f"{extract_dir}/{hyper_filename}")

    return output_path


# ── Convenience wrapper ───────────────────────────────────────────────────────

def build_from_demo_config(
    hyper_path: str,
    output_dir: str,
    slug: str,
    company: str,
    metrics: list[dict],
    primary_metric_field: str,
    dimension_field: str,
    secondary_metric_field: str = None,
    detail_dimensions: list[str] = None,
    detail_extra_metrics: list[dict] = None,
    date_field: str = "Date",
    build_date: str = None,
):
    output_path = os.path.join(output_dir, f"{slug}_dashboard.twbx")
    title = f"{company} — Performance Dashboard"

    build_dashboard_twbx(
        hyper_path=hyper_path,
        output_path=output_path,
        metrics=metrics,
        primary_metric_field=primary_metric_field,
        secondary_metric_field=secondary_metric_field,
        date_field=date_field,
        dimension_field=dimension_field,
        detail_dimensions=detail_dimensions,
        detail_extra_metrics=detail_extra_metrics,
        title=title,
        build_date=build_date,
    )

    return output_path


if __name__ == "__main__":
    demo_dir = os.path.join(os.path.dirname(__file__), "demos", "hchsp_student_attendance")
    hyper = os.path.join(demo_dir, "hchsp_student_attendance.hyper")

    if not os.path.exists(hyper):
        print(f"Hyper file not found: {hyper}")
        exit(1)

    metrics = [
        {"label": "Attendance", "field": "Attendance Rate", "agg": "Average"},
        {"label": "Dental", "field": "Dental Completion Rate", "agg": "Average"},
        {"label": "Screening", "field": "Screening Compliance Rate", "agg": "Average"},
        {"label": "Family Referral", "field": "Family Referral Rate", "agg": "Average"},
    ]

    extra_detail_metrics = [
        {"label": "Funded Enrollment", "field": "Funded Enrollment", "agg": "Sum"},
        {"label": "Actual Enrollment", "field": "Actual Enrollment", "agg": "Sum"},
    ]

    out = build_from_demo_config(
        hyper_path=hyper,
        output_dir=demo_dir,
        slug="hchsp_student_attendance",
        company="HCHSP",
        metrics=metrics,
        primary_metric_field="Attendance Rate",
        secondary_metric_field="Dental Completion Rate",
        dimension_field="ISD",
        detail_dimensions=["ISD", "Setting", "Program Type", "Campus Name"],
        detail_extra_metrics=extra_detail_metrics,
        build_date="2026-05-29",
    )
    print(f"\nDashboard built: {out}")
    print(f"  Size: {os.path.getsize(out) / 1024:.1f} KB")
    print(f"\n  Layout:")
    print(f"    Row 1: BANs — {', '.join(m['label'] for m in metrics)}")
    print(f"    Row 2: Bar chart + Treemap + Scatter plot")
    print(f"    Row 3: Detail table")
    print(f"\n  Open in Tableau Desktop → Server → Publish Workbook")
