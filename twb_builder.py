"""
TWB Builder — Generates Tableau .twb workbooks with live datasource connections
and publishes them to Tableau Cloud.

Creates workbooks with:
- Live connection to an already-published datasource (sqlproxy)
- Multiple worksheet types (bar, horizontal_bar, line, dual_axis, multi-line)
- Dashboard with Pulse metric tiles, filters, and viz zones
- Brand-colored layout with filter bar, title, KPI row, and content grid
- Auto-adapting layout: 1=full, 2=side-by-side, 3=2+1, 4=2x2, 5+=3+N

Usage:
    from twb_builder import build_twb, publish_twb, get_datasource_content_url

    content_url = get_datasource_content_url(ds_name, project_id, server)

    config = {
        "workbook_name": "Company - Use Case",
        "datasource_name": "Company - Use Case",
        "datasource_content_url": content_url,
        "server_pod": "us-east-1.online.tableau.com",
        "site_name": "sitename",
        "output_dir": "demos/company_slug/",
        "columns": [
            {"name": "Date", "role": "dimension", "datatype": "datetime"},
            {"name": "Region", "role": "dimension", "datatype": "string"},
            {"name": "Revenue", "role": "measure", "datatype": "real", "format": "currency"},
        ],
        "worksheets": [
            {"name": "Revenue by Region", "type": "horizontal_bar",
             "title": "Revenue by Region", "rows_field": "Region",
             "cols_field": "Revenue", "aggregation": "Avg", "sort": "desc"},
            {"name": "Revenue Trend", "type": "line",
             "title": "Revenue — Monthly Trend", "rows_field": "Revenue",
             "cols_field": "Date", "aggregation": "Avg",
             "date_derivation": "Month-Trunc"},
        ],
        "pulse_tiles": [
            {"field": "Revenue", "def_id": "xxx", "metric_id": "yyy"},
        ],
        "filters": ["Region"],
        "dashboard_name": "Company — Overview",
        "brand": {"primary": "#1B3A6B", "secondary": "#4E9FD1", "border": "#bfb18c"},
    }

    twb_path = build_twb(config)
    wb_luid = publish_twb(twb_path, project_id, "Company - Use Case", server)

Worksheet types:
    "horizontal_bar" — dim on rows, measure on cols (sorted bar chart)
    "bar"            — measure on rows, dim on cols (vertical bar)
    "line"           — measure on rows, date on cols (time series)
    "line" + color_field — multi-line, one line per color dimension value
    "dual_axis"      — two measures on rows (bar+line combo, independent Y-axes)
                       requires: rows_field_2, aggregation_2, mark_1, mark_2, color_1, color_2

Column config:
    datatype: "string" | "real" | "integer" | "datetime"
    role: "dimension" | "measure"
    format (measures only): "currency" | "percentage" | "decimal" | "integer"
"""

import hashlib
import os
import uuid
from xml.sax.saxutils import escape, quoteattr

import tableauserverclient as TSC


# ── Format strings ────────────────────────────────────────────────────────────

FORMAT_MAP = {
    "currency": 'c"$"#,##0.00;-"$"#,##0.00',
    "percentage": "p0.00%",
    "integer": "#,##0",
    "decimal": "0.00",
}

# Remote-type codes for metadata-records
REMOTE_TYPES = {
    "real": "5",
    "integer": "20",
    "string": "129",
    "datetime": "135",
}

LOCAL_TYPES = {
    "real": "real",
    "integer": "integer",
    "string": "string",
    "datetime": "datetime",
}


# ── Public API ────────────────────────────────────────────────────────────────


def build_twb(config: dict) -> str:
    """
    Generate a .twb XML file from a config dict.

    Returns path to the generated .twb file.
    """
    ds_hash = _generate_ds_hash(config["datasource_name"])
    ds_name = f"sqlproxy.{ds_hash}"

    # Build all sections
    datasource_xml = _build_datasource_xml(config, ds_name)
    worksheets_xml = []
    for ws in config["worksheets"]:
        worksheets_xml.append(_build_worksheet_xml(ws, ds_name, config["columns"], config))

    ws_names = [ws["name"] for ws in config["worksheets"]]
    dashboard_name = config.get("dashboard_name", "Dashboard")
    dashboard_xml = _build_dashboard_xml(config, ws_names, ds_name)
    windows_xml = _build_windows_xml(ws_names, dashboard_name)

    # Build referenced-extensions manifest if Pulse tiles are used
    ref_ext_xml = ""
    if config.get("pulse_tiles"):
        num_tiles = len(config["pulse_tiles"])
        ref_ext_xml = f"""
  <referenced-extensions>
    <referenced-extension>
      <manifest manifest-version='0.1'>
        <dashboard-extension extension-version='0.100.0' id='com.tableau.pulse-metric'>
          <default-locale>en_US</default-locale>
          <name resource-id='name' />
          <description>Display Tableau Pulse metric</description>
          <author email='customerservice@tableau.com' name='Tableau' organization='Tableau' website='https://www.tableau.com' />
          <min-api-version>1.10</min-api-version>
          <source-location>
            <url>tableau:/pulse/extension-assets/dashboard-metric/index.html</url>
          </source-location>
          <icon />
          <context-menu>
            <configure-context-menu-item />
          </context-menu>
        </dashboard-extension>
        <resources>
          <resource id='name'>
            <text locale='en_US'>Pulse Metric</text>
          </resource>
        </resources>
      </manifest>
      <referenced-views>
        <referenced-view instances='{num_tiles}' viewId={quoteattr(dashboard_name)} />
      </referenced-views>
    </referenced-extension>
  </referenced-extensions>"""

    # Assemble full workbook
    twb = f"""<?xml version='1.0' encoding='utf-8' ?>
<workbook name={quoteattr(config['workbook_name'])} version='18.1' xmlns:user='http://www.tableausoftware.com/xml/user'>
  <preferences />
  <datasources>
{datasource_xml}
  </datasources>
  <worksheets>
{"".join(worksheets_xml)}
  </worksheets>
  <dashboards>
{dashboard_xml}
  </dashboards>
  <windows>
{windows_xml}
  </windows>{ref_ext_xml}
</workbook>
"""

    # Write to file
    slug = config["workbook_name"].replace(" ", "_").replace("-", "_").lower()
    output_dir = config.get("output_dir", os.path.dirname(os.path.abspath(__file__)))
    output_path = os.path.join(output_dir, f"{slug}.twb")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(twb)

    return output_path


def get_datasource_content_url(datasource_name: str, project_id: str, server) -> str:
    """Look up a published datasource's content_url by name and project."""
    all_ds, _ = server.datasources.get()
    for ds in all_ds:
        if ds.name == datasource_name and ds.project_id == project_id:
            return ds.content_url
    raise ValueError(f"Datasource '{datasource_name}' not found in project {project_id}")


def publish_twb(twb_path: str, project_id: str, workbook_name: str, server) -> str:
    """
    Publish a .twb to Tableau Cloud using TSC.

    Returns the published workbook LUID.
    """
    wb_item = TSC.WorkbookItem(project_id=project_id, name=workbook_name)
    published = server.workbooks.publish(
        wb_item, twb_path, mode=TSC.Server.PublishMode.Overwrite
    )
    print(f"  Published workbook: {published.name} (LUID: {published.id})")
    return published.id


# ── Internal: Datasource ──────────────────────────────────────────────────────


def _generate_ds_hash(name: str) -> str:
    """Deterministic 20-char hex hash for the datasource internal name."""
    return hashlib.sha256(name.encode()).hexdigest()[:20]


def _build_datasource_xml(config: dict, ds_name: str) -> str:
    """Build the full <datasource> block with connection, metadata, and columns."""
    caption = escape(config["datasource_name"])
    content_url = escape(config["datasource_content_url"])
    server_pod = escape(config["server_pod"])
    columns = config["columns"]

    # Metadata records
    metadata_records = []
    for i, col in enumerate(columns):
        metadata_records.append(_metadata_record(col, i))

    # Column definitions
    column_defs = []
    for col in columns:
        column_defs.append(_column_definition(col))

    return f"""    <datasource caption='{caption}' inline='true' name='{ds_name}' version='18.1'>
      <connection channel='https' class='sqlproxy' dbname='{content_url}' directory='/dataserver' server='{server_pod}' port='443' direct-connection='yes'>
        <relation name='sqlproxy' table='[sqlproxy]' type='table' />
        <metadata-records>
{"".join(metadata_records)}
        </metadata-records>
      </connection>
      <aliases enabled='yes' />
{_indent("".join(column_defs), 6)}
      <layout dim-ordering='alphabetic' measure-ordering='alphabetic' show-structure='true' />
    </datasource>"""


def _metadata_record(col: dict, ordinal: int) -> str:
    """Build a single <metadata-record> element."""
    name = col["name"]
    datatype = col["datatype"]
    role = col["role"]

    remote_type = REMOTE_TYPES[datatype]
    local_type = LOCAL_TYPES[datatype]

    if role == "measure":
        cls = "measure"
        aggregation = "Sum"
    elif datatype == "datetime":
        cls = "column"
        aggregation = "Year"
    else:
        cls = "column"
        aggregation = "Count"

    collation = ""
    if datatype == "string":
        collation = "\n            <collation flag='0' name='LEN_RUS' />"

    # Attributes block
    if datatype == "datetime":
        attrs = "\n            <attributes>\n              <attribute datatype='string' name='field-type'>1</attribute>\n              <attribute datatype='string' name='role'>0</attribute>\n            </attributes>"
    elif role == "dimension":
        attrs = "\n            <attributes>\n              <attribute datatype='string' name='field-type'>2</attribute>\n              <attribute datatype='string' name='role'>0</attribute>\n            </attributes>"
    else:
        attrs = "\n            <attributes>\n              <attribute datatype='string' name='field-type'>0</attribute>\n            </attributes>"

    return f"""
          <metadata-record class='{cls}'>
            <remote-name>{escape(name)}</remote-name>
            <remote-type>{remote_type}</remote-type>
            <local-name>[{escape(name)}]</local-name>
            <parent-name>[sqlproxy]</parent-name>
            <remote-alias>{escape(name)}</remote-alias>
            <ordinal>{ordinal}</ordinal>
            <local-type>{local_type}</local-type>
            <aggregation>{aggregation}</aggregation>
            <contains-null>true</contains-null>{collation}{attrs}
          </metadata-record>
"""


def _column_definition(col: dict) -> str:
    """Build a <column> element for the datasource."""
    name = col["name"]
    datatype = col["datatype"]
    role = col["role"]
    fmt = col.get("format")

    if role == "measure":
        aggregation = "Sum"
        role_attr = "measure"
        type_attr = "quantitative"
        default_type = "quantitative"
    elif datatype == "datetime":
        aggregation = "Year"
        role_attr = "dimension"
        type_attr = "ordinal"
        default_type = "ordinal"
    else:
        aggregation = "Count"
        role_attr = "dimension"
        type_attr = "nominal"
        default_type = "nominal"

    fmt_attr = ""
    if fmt and fmt in FORMAT_MAP:
        fmt_attr = f" default-format='{FORMAT_MAP[fmt]}'"

    return f"<column aggregation='{aggregation}' datatype='{datatype}' default-type='{default_type}'{fmt_attr} name='[{escape(name)}]' pivot='key' role='{role_attr}' type='{type_attr}' />\n"


# ── Internal: Worksheets ──────────────────────────────────────────────────────


def _build_worksheet_xml(ws_config: dict, ds_name: str, columns: list, full_config: dict) -> str:
    """Build a single <worksheet> element."""
    ws_name = ws_config["name"]
    ws_type = ws_config["type"]
    title = ws_config.get("title", ws_name)
    rows_field = ws_config.get("rows_field", "")
    cols_field = ws_config.get("cols_field", "")
    aggregation = ws_config.get("aggregation", "Sum")
    date_derivation = ws_config.get("date_derivation", "Month-Trunc")
    date_filter_months = ws_config.get("date_filter_months")
    sort_dir = ws_config.get("sort", "")

    # Dual-axis: second measure on rows
    rows_field_2 = ws_config.get("rows_field_2", "")
    aggregation_2 = ws_config.get("aggregation_2", "Avg")

    # Determine mark type
    mark_class = _mark_class(ws_type)

    # Build column instances and shelf references
    col_lookup = {c["name"]: c for c in columns}
    rows_col = col_lookup.get(rows_field, {})
    cols_col = col_lookup.get(cols_field, {})
    rows_col_2 = col_lookup.get(rows_field_2, {}) if rows_field_2 else {}

    # Generate instance names
    rows_instance = _instance_name(rows_field, rows_col, aggregation, date_derivation)
    cols_instance = _instance_name(cols_field, cols_col, aggregation, date_derivation)
    rows_instance_2 = _instance_name(rows_field_2, rows_col_2, aggregation_2, date_derivation) if rows_field_2 else ""

    # Determine which fields are used by this worksheet
    used_fields = set()
    if rows_field:
        used_fields.add(rows_field)
    if cols_field:
        used_fields.add(cols_field)
    if rows_field_2:
        used_fields.add(rows_field_2)

    # Color field for multi-line or explicit color
    color_field = ws_config.get("color_field")
    color_instance = ""
    if color_field and color_field in col_lookup:
        used_fields.add(color_field)
        color_col = col_lookup[color_field]
        color_instance = _instance_name(color_field, color_col, "None", "")

    # Add filter fields
    filters = full_config.get("filters", [])
    for f in filters:
        if f in col_lookup:
            used_fields.add(f)

    # Build datasource-dependencies
    dep_columns = []
    dep_instances = []
    for field_name in sorted(used_fields):
        col = col_lookup[field_name]
        dep_columns.append(_dep_column(field_name, col))

    # Add column-instances for rows/cols
    if rows_field and rows_col:
        dep_instances.append(_dep_column_instance(rows_field, rows_col, aggregation, date_derivation))
    if cols_field and cols_col:
        dep_instances.append(_dep_column_instance(cols_field, cols_col, aggregation, date_derivation))
    if rows_field_2 and rows_col_2:
        dep_instances.append(_dep_column_instance(rows_field_2, rows_col_2, aggregation_2, date_derivation))
    if color_field and color_field in col_lookup:
        dep_instances.append(_dep_column_instance(color_field, col_lookup[color_field], "None", ""))

    # Filter instances (dimensions only)
    for f in filters:
        if f in col_lookup and col_lookup[f]["role"] == "dimension" and f not in (rows_field, cols_field, color_field, rows_field_2):
            dep_instances.append(_dep_column_instance(f, col_lookup[f], "None", ""))

    # Build filter XML elements
    filter_xml = ""
    for f in filters:
        if f in col_lookup and col_lookup[f]["role"] == "dimension":
            f_instance = _instance_name(f, col_lookup[f], "None", "")
            filter_xml += f"""
        <filter class='categorical' column='[{ds_name}].{f_instance}' context='true'>
          <groupfilter function='level-members' level='{f_instance}' user:ui-enumeration='all' user:ui-marker='enumerate' />
        </filter>"""

    # Date filter (relative)
    date_filter_xml = ""
    if date_filter_months and rows_col.get("datatype") == "datetime":
        date_filter_xml = _date_range_filter(ds_name, rows_field, date_filter_months)
    elif date_filter_months and cols_col.get("datatype") == "datetime":
        date_filter_xml = _date_range_filter(ds_name, cols_field, date_filter_months)

    # Sort XML
    sort_xml = ""
    if sort_dir and rows_col.get("role") == "dimension" and cols_col.get("role") == "measure":
        sort_xml = _sort_xml(ds_name, rows_field, rows_col, cols_field, cols_col, aggregation, sort_dir, date_derivation)
    elif sort_dir and cols_col.get("role") == "dimension" and rows_col.get("role") == "measure":
        sort_xml = _sort_xml(ds_name, cols_field, cols_col, rows_field, rows_col, aggregation, sort_dir, date_derivation)

    # Shelf references (fully qualified)
    rows_ref = f"[{ds_name}].{rows_instance}" if rows_field else ""
    cols_ref = f"[{ds_name}].{cols_instance}" if cols_field else ""

    # Dual-axis: combine two measures on rows with +
    if ws_type == "dual_axis" and rows_field_2:
        rows_ref_2 = f"[{ds_name}].{rows_instance_2}"
        rows_ref = f"({rows_ref} + {rows_ref_2})"

    # Encodings for color
    encodings_xml = ""
    if color_field and ws_type != "dual_axis":
        encodings_xml = f"""
            <encodings>
              <color column='[{ds_name}].{color_instance}' />
            </encodings>"""

    ws_uuid = _ws_uuid(ws_name)

    # Dual-axis needs multiple panes with different mark types
    if ws_type == "dual_axis" and rows_field_2:
        mark_1 = ws_config.get("mark_1", "Bar")
        mark_2 = ws_config.get("mark_2", "Line")
        color_1 = ws_config.get("color_1", "#4E9FD1")
        color_2 = ws_config.get("color_2", "#1B3A6B")
        panes_xml = f"""
        <panes>
          <pane selection-relaxation-option='selection-relaxation-allow'>
            <view><breakdown value='auto' /></view>
            <mark class='Automatic' />
            <style>
              <style-rule element='mark'>
                <format attr='mark-labels-show' value='false' />
              </style-rule>
            </style>
          </pane>
          <pane id='1' selection-relaxation-option='selection-relaxation-allow' y-axis-name='[{ds_name}].{rows_instance}'>
            <view><breakdown value='auto' /></view>
            <mark class='{mark_1}' />
            <mark-sizing mark-sizing-setting='marks-scaling-off' />
            <style>
              <style-rule element='mark'>
                <format attr='mark-labels-show' value='false' />
                <format attr='mark-color' value='{color_1}' />
              </style-rule>
            </style>
          </pane>
          <pane id='2' selection-relaxation-option='selection-relaxation-allow' y-axis-name='[{ds_name}].{rows_instance_2}'>
            <view><breakdown value='auto' /></view>
            <mark class='{mark_2}' />
            <mark-sizing mark-sizing-setting='marks-scaling-off' />
            <style>
              <style-rule element='mark'>
                <format attr='mark-labels-show' value='false' />
                <format attr='mark-color' value='{color_2}' />
                <format attr='line-width' value='2.5' />
              </style-rule>
            </style>
          </pane>
        </panes>"""
    else:
        panes_xml = f"""
        <panes>
          <pane selection-relaxation-option='selection-relaxation-allow'>
            <view>
              <breakdown value='auto' />
            </view>
            <mark class='{mark_class}' />{encodings_xml}
          </pane>
        </panes>"""

    return f"""
    <worksheet name={quoteattr(ws_name)}>
      <layout-options>
        <title>
          <formatted-text><run fontstyle='normal'>{escape(title)}</run></formatted-text>
        </title>
      </layout-options>
      <table>
        <view>
          <datasources>
            <datasource caption={quoteattr(full_config['datasource_name'])} name='{ds_name}' />
          </datasources>
          <datasource-dependencies datasource='{ds_name}'>
{"".join(dep_columns)}
{"".join(dep_instances)}
          </datasource-dependencies>{filter_xml}{date_filter_xml}{sort_xml}
          <aggregation value='true' />
        </view>{panes_xml}
        <rows>{rows_ref}</rows>
        <cols>{cols_ref}</cols>
      </table>
      <simple-id uuid='{ws_uuid}' />
    </worksheet>
"""


def _mark_class(ws_type: str) -> str:
    """Map worksheet type to Tableau mark class."""
    return {
        "bar": "Bar",
        "horizontal_bar": "Bar",
        "line": "Line",
        "dual_axis": "Line",
        "area": "Area",
        "scatter": "Circle",
        "square": "Square",
        "text": "Text",
    }.get(ws_type, "Automatic")


def _instance_name(field_name: str, col: dict, aggregation: str, date_derivation: str) -> str:
    """Generate the column-instance bracket name like [sum:Revenue:qk].
    Output is XML-attribute-safe (ampersands, quotes, angle brackets escaped)."""
    if not field_name or not col:
        return ""

    datatype = col.get("datatype", "string")
    role = col.get("role", "dimension")
    safe_name = escape(field_name)

    if datatype == "datetime":
        if date_derivation == "Month-Trunc":
            return f"[tmn:{safe_name}:qk]"
        else:
            return f"[none:{safe_name}:qk]"
    elif role == "measure":
        agg_prefix = aggregation.lower()[:3]  # sum, avg, cnt, etc.
        return f"[{agg_prefix}:{safe_name}:qk]"
    else:
        return f"[none:{safe_name}:nk]"


def _dep_column(field_name: str, col: dict) -> str:
    """Build <column> inside datasource-dependencies."""
    datatype = col["datatype"]
    role = col["role"]

    if role == "measure":
        aggregation = "Sum"
        role_attr = "measure"
        type_attr = "quantitative"
    elif datatype == "datetime":
        aggregation = "Year"
        role_attr = "dimension"
        type_attr = "ordinal"
    else:
        aggregation = "Count"
        role_attr = "dimension"
        type_attr = "nominal"

    return f"            <column datatype='{datatype}' name='[{escape(field_name)}]' role='{role_attr}' type='{type_attr}' />\n"


def _dep_column_instance(field_name: str, col: dict, aggregation: str, date_derivation: str) -> str:
    """Build <column-instance> inside datasource-dependencies."""
    datatype = col.get("datatype", "string")
    role = col.get("role", "dimension")
    instance = _instance_name(field_name, col, aggregation, date_derivation)

    if datatype == "datetime":
        if date_derivation == "Month-Trunc":
            derivation = "Month-Trunc"
            type_attr = "quantitative"
        else:
            derivation = "None"
            type_attr = "quantitative"
    elif role == "measure":
        derivation = aggregation
        type_attr = "quantitative"
    else:
        derivation = "None"
        type_attr = "nominal"

    return f"            <column-instance column='[{escape(field_name)}]' derivation='{derivation}' name='{instance}' pivot='key' type='{type_attr}' />\n"


def _date_range_filter(ds_name: str, date_field: str, months: int) -> str:
    """Build a relative date filter for last N months."""
    return f"""
        <filter class='relative-date' column='[{ds_name}].[none:{date_field}:qk]' first-period='-{months}' include-future='true' include-null='false' last-period='0' period-type='month' />"""


def _sort_xml(ds_name: str, dim_field: str, dim_col: dict, measure_field: str, measure_col: dict, aggregation: str, direction: str, date_derivation: str) -> str:
    """Build a shelf-sort-v2 element for ordering a dimension by a measure."""
    dim_instance = f"[{ds_name}].{_instance_name(dim_field, dim_col, 'None', '')}"
    measure_instance = f"[{ds_name}].{_instance_name(measure_field, measure_col, aggregation, date_derivation)}"
    dir_attr = "DESC" if direction == "desc" else "ASC"

    return f"""
          <shelf-sorts>
            <shelf-sort-v2 dimension-to-sort='{dim_instance}' direction='{dir_attr}' is-on-innermost-dimension='true' measure-to-sort-by='{measure_instance}' shelf='rows' />
          </shelf-sorts>"""


def _ws_uuid(ws_name: str) -> str:
    """Deterministic UUID for a worksheet based on name."""
    h = hashlib.md5(ws_name.encode()).hexdigest()
    return f"{{{h[:8]}-{h[8:12]}-4{h[13:16]}-8{h[17:20]}-{h[20:32]}}}"


# ── Internal: Dashboard ───────────────────────────────────────────────────────


def _build_dashboard_xml(config: dict, ws_names: list, ds_name: str) -> str:
    """Build the <dashboard> element with zone tree."""
    dashboard_name = config.get("dashboard_name", "Dashboard")
    brand = config.get("brand", {})
    primary = brand.get("primary", "#1B3A6B")
    secondary = brand.get("secondary", "#4E9FD1")
    border_color = brand.get("border", "#CCCCCC")
    bg_color = brand.get("background", "#F3F3F3")
    filters = config.get("filters", [])
    pulse_tiles = config.get("pulse_tiles", [])
    site_name = config.get("site_name", "")
    server_pod = config.get("server_pod", "")
    datasource_caption = config.get("datasource_name", "")

    # Zone ID counter
    zid = [1]

    def next_id():
        val = zid[0]
        zid[0] += 1
        return val

    # Build zone tree top-to-bottom
    # Root container (vertical)
    root_id = next_id()

    # 1. Filter row (horizontal)
    filter_row_id = next_id()
    filter_zones = []
    # Filters need an anchor worksheet — use the first one
    anchor_ws = ws_names[0] if ws_names else "Sheet1"
    for f in filters:
        fid = next_id()
        f_instance = f"[{ds_name}].[none:{escape(f)}:nk]"
        filter_zones.append(f"""              <zone h='3500' id='{fid}' mode='checkdropdown' name={quoteattr(anchor_ws)} param='{f_instance}' type-v2='filter' w='20000'>
                <zone-style>
                  <format attr='border-color' value='{primary}' />
                  <format attr='border-style' value='solid' />
                  <format attr='border-width' value='1' />
                  <format attr='background-color' value='{bg_color}' />
                </zone-style>
              </zone>""")

    filter_row_xml = ""
    if filter_zones:
        filter_row_xml = f"""
            <zone fixed-size='35' h='3500' id='{filter_row_id}' is-fixed='true' param='horz' type-v2='layout-flow' w='100000'>
{chr(10).join(filter_zones)}
              <zone-style>
                <format attr='border-color' value='#000000' />
                <format attr='border-style' value='none' />
                <format attr='border-width' value='0' />
                <format attr='margin' value='4' />
              </zone-style>
            </zone>"""

    # 2. Title zone (text widget in a fixed-height container)
    title_id = next_id()
    title_text_id = next_id()
    title_text = config.get("dashboard_title", config.get("dashboard_name", "Dashboard"))
    title_zone = f"""
            <zone fixed-size='70' h='7000' id='{title_id}' is-fixed='true' param='horz' type-v2='layout-flow' w='100000'>
              <zone forceUpdate='true' h='7000' id='{title_text_id}' type-v2='text' w='100000'>
                <formatted-text>
                  <run bold='true' fontalignment='1' fontcolor='{primary}' fontsize='16'>{escape(title_text)}</run>
                </formatted-text>
                <zone-style>
                  <format attr='border-color' value='#000000' />
                  <format attr='border-style' value='none' />
                  <format attr='border-width' value='0' />
                  <format attr='margin' value='0' />
                </zone-style>
              </zone>
              <zone-style>
                <format attr='border-color' value='#000000' />
                <format attr='border-style' value='none' />
                <format attr='border-width' value='0' />
              </zone-style>
            </zone>"""

    # 3. Pulse tiles row (horizontal)
    pulse_row_xml = ""
    if pulse_tiles:
        pulse_row_id = next_id()
        tile_zones = []
        for tile in pulse_tiles:
            tid = next_id()
            instance_id = str(uuid.uuid4())
            pulse_root = f"https://{server_pod}/pulse/site/{site_name}/"
            instance_hex = instance_id.replace("-", "").upper()
            tile_zones.append(f"""              <zone forceUpdate='true' h='18000' id='{tid}' param='[com.tableau.pulse-metric].[0.100.0].[tableau:/pulse/extension-assets/dashboard-metric/index.html]' type-v2='dashboard-object' w='25000'>
                <add-in add-in-id='com.tableau.pulse-metric' extension-url='tableau:/pulse/extension-assets/dashboard-metric/index.html' extension-version='0.100.0' instance-id='{instance_hex}'>
                  <instance-settings>
                    <setting key='DATASOURCE_NAME' value={quoteattr(datasource_caption)} />
                    <setting key='ENABLE_LINK' value='true' />
                    <setting key='MEASURE_FIELD' value={quoteattr(tile['field'])} />
                    <setting key='METRIC_DEFINITION_ID' value='{tile["def_id"]}' />
                    <setting key='METRIC_ID' value='{tile["metric_id"]}' />
                    <setting key='PULSE_ROOT' value='{escape(pulse_root)}' />
                    <setting key='SQUARE_CORNERS' value='true' />
                    <setting key='SYSTEM_TOOLTIP_TEXT' value='Month to Date' />
                    <setting key='TIME_DIMENSION_FIELD' value='Date' />
                    <setting key='USE_FULL_CARD' value='true' />
                    <setting key='has_been_configured' value='true' />
                    <setting key='has_been_initialized' value='true' />
                  </instance-settings>
                  <type-settings><dashboard /></type-settings>
                </add-in>
                <zone-style>
                  <format attr='border-color' value='#000000' />
                  <format attr='border-style' value='none' />
                  <format attr='border-width' value='0' />
                  <format attr='margin' value='4' />
                </zone-style>
              </zone>""")

        pulse_row_xml = f"""
            <zone fixed-size='180' h='18000' id='{pulse_row_id}' is-fixed='true' param='horz' type-v2='layout-flow' w='100000'>
{chr(10).join(tile_zones)}
              <zone-style>
                <format attr='border-color' value='#000000' />
                <format attr='border-style' value='none' />
                <format attr='border-width' value='0' />
                <format attr='margin' value='4' />
              </zone-style>
            </zone>"""

    # 4. Content area — worksheets
    def _viz_zone(zid, ws_n, w='50000', h='50000'):
        return f"""                <zone h='{h}' id='{zid}' name={quoteattr(ws_n)} w='{w}'>
                  <zone-style>
                    <format attr='border-color' value='{border_color}' />
                    <format attr='border-style' value='solid' />
                    <format attr='border-width' value='1' />
                    <format attr='margin' value='4' />
                  </zone-style>
                </zone>"""

    content_id = next_id()

    if len(ws_names) == 1:
        vid = next_id()
        content_zone = f"""
            <zone h='70000' id='{content_id}' param='horz' type-v2='layout-flow' w='100000'>
{_viz_zone(vid, ws_names[0], w='100000', h='70000')}
              <zone-style>
                <format attr='border-color' value='#000000' />
                <format attr='border-style' value='none' />
                <format attr='border-width' value='0' />
              </zone-style>
            </zone>"""

    elif len(ws_names) == 2:
        lid = next_id()
        rid = next_id()
        content_zone = f"""
            <zone h='70000' id='{content_id}' param='horz' type-v2='layout-flow' w='100000'>
{_viz_zone(lid, ws_names[0], w='50000', h='70000')}
{_viz_zone(rid, ws_names[1], w='50000', h='70000')}
              <zone-style>
                <format attr='border-color' value='#000000' />
                <format attr='border-style' value='none' />
                <format attr='border-width' value='0' />
              </zone-style>
            </zone>"""

    elif len(ws_names) == 3:
        # Top row: first 2 side by side. Bottom: third full width.
        top_id = next_id()
        t1 = next_id()
        t2 = next_id()
        bot_id = next_id()
        b1 = next_id()
        content_zone = f"""
            <zone h='70000' id='{content_id}' param='vert' type-v2='layout-flow' w='100000'>
              <zone h='35000' id='{top_id}' param='horz' type-v2='layout-flow' w='100000'>
{_viz_zone(t1, ws_names[0], w='50000', h='35000')}
{_viz_zone(t2, ws_names[1], w='50000', h='35000')}
                <zone-style>
                  <format attr='border-color' value='#000000' />
                  <format attr='border-style' value='none' />
                  <format attr='border-width' value='0' />
                </zone-style>
              </zone>
              <zone h='35000' id='{bot_id}' param='horz' type-v2='layout-flow' w='100000'>
{_viz_zone(b1, ws_names[2], w='100000', h='35000')}
                <zone-style>
                  <format attr='border-color' value='#000000' />
                  <format attr='border-style' value='none' />
                  <format attr='border-width' value='0' />
                </zone-style>
              </zone>
              <zone-style>
                <format attr='border-color' value='#000000' />
                <format attr='border-style' value='none' />
                <format attr='border-width' value='0' />
              </zone-style>
            </zone>"""

    elif len(ws_names) == 4:
        # 2x2 grid
        top_id = next_id()
        t1 = next_id()
        t2 = next_id()
        bot_id = next_id()
        b1 = next_id()
        b2 = next_id()
        content_zone = f"""
            <zone h='70000' id='{content_id}' param='vert' type-v2='layout-flow' w='100000'>
              <zone h='35000' id='{top_id}' param='horz' type-v2='layout-flow' w='100000'>
{_viz_zone(t1, ws_names[0], w='50000', h='35000')}
{_viz_zone(t2, ws_names[1], w='50000', h='35000')}
                <zone-style>
                  <format attr='border-color' value='#000000' />
                  <format attr='border-style' value='none' />
                  <format attr='border-width' value='0' />
                </zone-style>
              </zone>
              <zone h='35000' id='{bot_id}' param='horz' type-v2='layout-flow' w='100000'>
{_viz_zone(b1, ws_names[2], w='50000', h='35000')}
{_viz_zone(b2, ws_names[3], w='50000', h='35000')}
                <zone-style>
                  <format attr='border-color' value='#000000' />
                  <format attr='border-style' value='none' />
                  <format attr='border-width' value='0' />
                </zone-style>
              </zone>
              <zone-style>
                <format attr='border-color' value='#000000' />
                <format attr='border-style' value='none' />
                <format attr='border-width' value='0' />
              </zone-style>
            </zone>"""

    else:
        # 5+: top row first 3, bottom row remaining
        top_id = next_id()
        top_zones = []
        for ws_n in ws_names[:3]:
            top_zones.append(_viz_zone(next_id(), ws_n, w='33333', h='35000'))
        bot_id = next_id()
        bot_zones = []
        bot_w = str(100000 // max(1, len(ws_names) - 3))
        for ws_n in ws_names[3:]:
            bot_zones.append(_viz_zone(next_id(), ws_n, w=bot_w, h='35000'))
        content_zone = f"""
            <zone h='70000' id='{content_id}' param='vert' type-v2='layout-flow' w='100000'>
              <zone h='35000' id='{top_id}' param='horz' type-v2='layout-flow' w='100000'>
{chr(10).join(top_zones)}
                <zone-style>
                  <format attr='border-color' value='#000000' />
                  <format attr='border-style' value='none' />
                  <format attr='border-width' value='0' />
                </zone-style>
              </zone>
              <zone h='35000' id='{bot_id}' param='horz' type-v2='layout-flow' w='100000'>
{chr(10).join(bot_zones)}
                <zone-style>
                  <format attr='border-color' value='#000000' />
                  <format attr='border-style' value='none' />
                  <format attr='border-width' value='0' />
                </zone-style>
              </zone>
              <zone-style>
                <format attr='border-color' value='#000000' />
                <format attr='border-style' value='none' />
                <format attr='border-width' value='0' />
              </zone-style>
            </zone>"""

    # Assemble root zone (TD-017: children before zone-style)
    dash_uuid = _dash_uuid(dashboard_name)

    return f"""    <dashboard name={quoteattr(dashboard_name)}>
      <style />
      <size maxheight='900' maxwidth='1600' minheight='900' minwidth='1600' sizing-mode='fixed' />
      <zones>
        <zone h='100000' id='{root_id}' param='vert' type-v2='layout-flow' w='100000'>{filter_row_xml}{title_zone}{pulse_row_xml}{content_zone}
          <zone-style>
            <format attr='border-color' value='#000000' />
            <format attr='border-style' value='none' />
            <format attr='border-width' value='0' />
            <format attr='margin' value='8' />
            <format attr='background-color' value='{bg_color}' />
          </zone-style>
        </zone>
      </zones>
      <simple-id uuid='{dash_uuid}' />
    </dashboard>"""


def _dash_uuid(name: str) -> str:
    h = hashlib.md5(f"dashboard_{name}".encode()).hexdigest()
    return f"{{{h[:8]}-{h[8:12]}-4{h[13:16]}-8{h[17:20]}-{h[20:32]}}}"


# ── Internal: Windows ─────────────────────────────────────────────────────────


def _build_windows_xml(ws_names: list, dashboard_name: str) -> str:
    """Build the <windows> section — one per worksheet + one for the dashboard."""
    lines = []

    for ws_name in ws_names:
        win_uuid = _win_uuid(ws_name)
        lines.append(f"""    <window class='worksheet' name={quoteattr(ws_name)}>
      <cards />
      <viewpoint />
      <simple-id uuid='{win_uuid}' />
    </window>""")

    # Dashboard window (maximized, references all worksheets)
    viewpoints = "\n".join(
        f"        <viewpoint name={quoteattr(n)} />" for n in ws_names
    )
    dash_win_uuid = _win_uuid(f"dashboard_{dashboard_name}")
    lines.append(f"""    <window class='dashboard' maximized='true' name={quoteattr(dashboard_name)}>
      <viewpoints>
{viewpoints}
      </viewpoints>
      <simple-id uuid='{dash_win_uuid}' />
    </window>""")

    return "\n".join(lines)


def _win_uuid(name: str) -> str:
    h = hashlib.md5(f"window_{name}".encode()).hexdigest()
    return f"{{{h[:8]}-{h[8:12]}-4{h[13:16]}-8{h[17:20]}-{h[20:32]}}}"


# ── Utilities ─────────────────────────────────────────────────────────────────


def _indent(text: str, spaces: int) -> str:
    """Indent each line of text by the given number of spaces."""
    prefix = " " * spaces
    return "\n".join(prefix + line if line.strip() else line for line in text.splitlines())
