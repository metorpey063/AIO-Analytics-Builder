"""
TDSX Builder — Creates self-healing Pulse datasources with calculated Date fields.

The pattern:
1. Publish a .hyper with a stored Date column (Pulse indexes it immediately)
2. Create metrics against the stored Date field
3. Overwrite with a .tdsx containing a calc Date = DATEADD('day', [Day_Offset], TODAY())
4. Metrics survive (LUID preserved), calc Date resolves, self-heals forever

No Prep flow needed. No scheduling. No maintenance.
"""

import os
import zipfile
import pandas as pd
import numpy as np
from datetime import date
from tableauhyperapi import (
    HyperProcess, Telemetry, Connection, CreateMode,
    TableName, TableDefinition, SqlType, Inserter,
)
import tableauhyperapi as ha


def build_hyper_with_date(df: pd.DataFrame, date_column: str, output_path: str) -> str:
    """
    Build a .hyper file WITH a stored Date column (for initial publish + indexing).
    Also adds Day_Offset column for the subsequent .tdsx conversion.

    Args:
        df: DataFrame with the demo data (must include date_column)
        date_column: Name of the date column
        output_path: Where to save the .hyper

    Returns:
        Path to the .hyper file
    """
    df = df.copy()
    df[date_column] = pd.to_datetime(df[date_column])
    max_date = df[date_column].max().date()
    df["Day_Offset"] = (df[date_column].dt.date - date.today()).apply(lambda x: x.days)

    # Build column definitions
    columns = []
    col_order = []
    for col in df.columns:
        dtype = str(df[col].dtype)
        if col == date_column:
            columns.append(TableDefinition.Column(col, SqlType.date()))
        elif col == "Day_Offset":
            columns.append(TableDefinition.Column(col, SqlType.big_int()))
        elif "float" in dtype:
            columns.append(TableDefinition.Column(col, SqlType.double()))
        elif "int" in dtype:
            columns.append(TableDefinition.Column(col, SqlType.big_int()))
        else:
            columns.append(TableDefinition.Column(col, SqlType.text()))
        col_order.append(col)

    with HyperProcess(telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hyper:
        with Connection(hyper.endpoint, output_path, CreateMode.CREATE_AND_REPLACE) as conn:
            conn.catalog.create_schema_if_not_exists("Extract")
            td = TableDefinition(table_name=TableName("Extract", "Extract"), columns=columns)
            conn.catalog.create_table_if_not_exists(td)
            with Inserter(conn, td) as ins:
                for _, row in df.iterrows():
                    values = []
                    for col in col_order:
                        val = row[col]
                        if col == date_column:
                            d = pd.Timestamp(val).date()
                            values.append(ha.Date(d.year, d.month, d.day))
                        elif col == "Day_Offset":
                            values.append(int(val))
                        elif isinstance(val, (np.floating, float)):
                            values.append(float(val))
                        elif isinstance(val, (np.integer, int)):
                            values.append(int(val))
                        else:
                            values.append(str(val))
                    ins.add_row(values)
                ins.execute()

    return output_path


def build_tdsx(df: pd.DataFrame, date_column: str, datasource_name: str, output_path: str) -> str:
    """
    Build a .tdsx with a calculated Date field (self-healing).
    The .hyper inside has Day_Offset but NO stored Date.
    The .tds defines Date = DATEADD('day', [Day_Offset], TODAY()).

    Args:
        df: DataFrame with the demo data (must include date_column)
        date_column: Name of the date column (used for Day_Offset calculation)
        datasource_name: Display name for the datasource
        output_path: Where to save the .tdsx

    Returns:
        Path to the .tdsx file
    """
    df = df.copy()
    df[date_column] = pd.to_datetime(df[date_column])
    df["Day_Offset"] = (df[date_column].dt.date - date.today()).apply(lambda x: x.days)

    # Drop the stored Date column — it becomes calculated
    df_no_date = df.drop(columns=[date_column])

    # Build .hyper (without Date, with Day_Offset)
    hyper_path = output_path.replace(".tdsx", "_inner.hyper")
    columns = []
    col_order = []
    for col in df_no_date.columns:
        dtype = str(df_no_date[col].dtype)
        if col == "Day_Offset":
            columns.append(TableDefinition.Column("Day_Offset", SqlType.big_int()))
        elif "float" in dtype:
            columns.append(TableDefinition.Column(col, SqlType.double()))
        elif "int" in dtype:
            columns.append(TableDefinition.Column(col, SqlType.big_int()))
        else:
            columns.append(TableDefinition.Column(col, SqlType.text()))
        col_order.append(col)

    with HyperProcess(telemetry=Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hyper:
        with Connection(hyper.endpoint, hyper_path, CreateMode.CREATE_AND_REPLACE) as conn:
            conn.catalog.create_schema_if_not_exists("Extract")
            td = TableDefinition(table_name=TableName("Extract", "Extract"), columns=columns)
            conn.catalog.create_table_if_not_exists(td)
            with Inserter(conn, td) as ins:
                for _, row in df_no_date.iterrows():
                    values = []
                    for col in col_order:
                        val = row[col]
                        if col == "Day_Offset":
                            values.append(int(val))
                        elif isinstance(val, (np.floating, float)):
                            values.append(float(val))
                        elif isinstance(val, (np.integer, int)):
                            values.append(int(val))
                        else:
                            values.append(str(val))
                    ins.add_row(values)
                ins.execute()

    # Build .tds with calculated Date
    metadata_records = []
    for i, col in enumerate(col_order):
        dtype = str(df_no_date[col].dtype)
        if col == "Day_Offset":
            remote_type = "20"
            local_type = "integer"
            aggregation = "Sum"
            collation = ""
        elif "float" in dtype:
            remote_type = "5"
            local_type = "real"
            aggregation = "Sum"
            collation = ""
        elif "int" in dtype:
            remote_type = "20"
            local_type = "integer"
            aggregation = "Sum"
            collation = ""
        else:
            remote_type = "129"
            local_type = "string"
            aggregation = "Count"
            collation = '\n        <collation flag="0" name="LEN_RUS" />'

        metadata_records.append(f"""      <metadata-record class='column'>
        <remote-name>{col}</remote-name>
        <remote-type>{remote_type}</remote-type>
        <local-name>[{col}]</local-name>
        <parent-name>[Extract]</parent-name>
        <remote-alias>{col}</remote-alias>
        <ordinal>{i}</ordinal>
        <local-type>{local_type}</local-type>
        <aggregation>{aggregation}</aggregation>
        <contains-null>true</contains-null>{collation}
      </metadata-record>""")

    metadata_xml = "\n".join(metadata_records)

    tds_content = f"""<?xml version='1.0' encoding='utf-8' ?>
<datasource formatted-name='Extract' inline='true' source-platform='linux' version='18.1'>
  <connection class='federated'>
    <named-connections>
      <named-connection name='hyper_0'>
        <connection authentication='auth-none' author-locale='en_US' class='hyper' dbname='Data/Extracts/hyper_0.hyper' default-settings='yes' schema='Extract' tablename='Extract' />
      </named-connection>
    </named-connections>
    <relation connection='hyper_0' name='Extract' table='[Extract].[Extract]' type='table'>
      <columns prep-output-type='outputOperationTypeCreate' />
    </relation>
    <metadata-records>
{metadata_xml}
    </metadata-records>
  </connection>
  <column caption='Date' datatype='datetime' name='[Date]' role='dimension' type='ordinal'>
    <calculation class='tableau' formula="DATEADD(&apos;day&apos;, [Day_Offset], TODAY())" />
  </column>
  <column datatype='integer' hidden='true' name='[Day_Offset]' role='dimension' type='ordinal' />
  <aliases enabled='yes' />
  <layout dim-ordering='alphabetic' dim-percentage='0.5' measure-ordering='alphabetic' measure-percentage='0.4' show-structure='true' />
</datasource>
"""

    # Package into .tdsx
    tds_path = output_path.replace(".tdsx", ".tds")
    with open(tds_path, "w") as f:
        f.write(tds_content)

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(tds_path, "Extract.tds")
        z.write(hyper_path, "Data/Extracts/hyper_0.hyper")

    # Cleanup temp files
    os.remove(hyper_path)
    os.remove(tds_path)

    return output_path


def publish_hyper_for_indexing(
    df: pd.DataFrame,
    date_column: str,
    datasource_name: str,
    project_id: str,
    server,
    output_dir: str,
) -> str:
    """
    Step 1 of self-healing: Publish .hyper with stored Date (Pulse indexes it).

    IMPORTANT: Create your Pulse metrics AFTER this returns and BEFORE calling
    convert_to_self_healing(). The metrics need the stored Date field to exist
    during creation.

    Args:
        df: DataFrame with demo data
        date_column: Name of the date column
        datasource_name: Name for the published datasource
        project_id: Tableau Cloud project LUID
        server: Authenticated TSC Server object
        output_dir: Directory to save temp files

    Returns:
        Datasource LUID (use for metric creation, then pass to convert_to_self_healing)
    """
    import tableauserverclient as TSC
    import time

    slug = datasource_name.replace(" ", "_").replace("-", "_").lower()

    hyper_path = os.path.join(output_dir, f"{slug}_initial.hyper")
    build_hyper_with_date(df, date_column, hyper_path)

    ds_item = TSC.DatasourceItem(project_id=project_id, name=datasource_name)
    published = server.datasources.publish(ds_item, hyper_path, mode=TSC.Server.PublishMode.Overwrite)
    ds_luid = published.id
    print(f"  Published .hyper (for indexing): {ds_luid}")

    # Wait for Pulse to index
    time.sleep(20)

    # Cleanup temp .hyper
    os.remove(hyper_path)

    return ds_luid


def convert_to_self_healing(
    df: pd.DataFrame,
    date_column: str,
    datasource_name: str,
    project_id: str,
    server,
    output_dir: str,
) -> str:
    """
    Step 2 of self-healing: Overwrite with .tdsx containing calc Date.
    Call this AFTER creating all Pulse metrics.

    The LUID is preserved — existing metrics continue to resolve the 'Date'
    field, which is now a calculated DATEADD('day', [Day_Offset], TODAY()).
    Self-heals forever with no refresh, no flow, no scheduling.

    Args:
        df: DataFrame with demo data (same as step 1)
        date_column: Name of the date column
        datasource_name: Same name as step 1 (triggers Overwrite)
        project_id: Same project as step 1
        server: Authenticated TSC Server object
        output_dir: Directory to save .tdsx

    Returns:
        Path to the .tdsx file (kept for reference)
    """
    import tableauserverclient as TSC
    import time

    slug = datasource_name.replace(" ", "_").replace("-", "_").lower()
    tdsx_path = os.path.join(output_dir, f"{slug}_selfheal.tdsx")
    build_tdsx(df, date_column, datasource_name, tdsx_path)

    ds_item = TSC.DatasourceItem(project_id=project_id, name=datasource_name)
    published = server.datasources.publish(ds_item, tdsx_path, mode=TSC.Server.PublishMode.Overwrite)
    print(f"  Overwritten with .tdsx (self-healing): {published.id}")

    time.sleep(15)

    return tdsx_path
