"""
Prep Flow Builder — Generates self-contained Tableau Prep flows for auto-refreshing dates.

Creates a .tflx file that:
1. Reads an embedded CSV with a Day_Offset column (days relative to max date = 0)
2. Calculates Date = DATEADD('day', [Day_Offset], TODAY()) at runtime
3. Publishes the result as a datasource on Tableau Cloud

When scheduled daily, dates are always current — no manual /refresh-dates needed.
"""

import json
import uuid
import zipfile
import pandas as pd
from datetime import date


def build_prep_flow(
    df: pd.DataFrame,
    date_column: str,
    datasource_name: str,
    project_name: str,
    project_luid: str,
    server_url: str = "https://us-east-1.online.tableau.com",
    site_name: str = "torpeyshouseodata",
    output_path: str = None,
) -> str:
    """
    Build a self-contained .tflx Prep flow from a DataFrame.

    Args:
        df: DataFrame with the demo data (must include date_column)
        date_column: Name of the date column to make self-healing
        datasource_name: Name of the published datasource to create/overwrite
        project_name: Tableau Cloud project name
        project_luid: Tableau Cloud project LUID
        server_url: Tableau Cloud server URL
        site_name: Tableau Cloud site name
        output_path: Where to save the .tflx file (defaults to datasource_name.tflx)

    Returns:
        Path to the generated .tflx file
    """
    if output_path is None:
        safe_name = datasource_name.replace(" ", "_").replace("-", "_").lower()
        output_path = f"{safe_name}_auto_refresh.tflx"

    # Convert date column to Day_Offset
    df = df.copy()
    df[date_column] = pd.to_datetime(df[date_column])
    max_date = df[date_column].max().date()
    df["Day_Offset"] = (df[date_column].dt.date - max_date).apply(lambda x: x.days)
    df_export = df.drop(columns=[date_column])

    csv_bytes = df_export.to_csv(index=False).encode("utf-8")

    # Build field schema
    fields = []
    for col in df_export.columns:
        dtype = str(df_export[col].dtype)
        if "float" in dtype:
            ftype = "real"
        elif "int" in dtype:
            ftype = "integer"
        else:
            ftype = "string"
        fields.append({
            "name": col,
            "type": ftype,
            "collation": "LEN_RUS" if ftype == "string" else None,
            "caption": None,
            "ordinal": None,
            "isGenerated": False,
        })

    # Generate node IDs
    input_id = str(uuid.uuid4())
    container_id = str(uuid.uuid4())
    add_date_id = str(uuid.uuid4())
    output_id = str(uuid.uuid4())
    conn_id = str(uuid.uuid4())

    csv_filename = "demo_data.csv"

    flow = {
        "parameters": {"parameters": {}},
        "initialNodes": [input_id],
        "nodes": {
            input_id: {
                "nodeType": ".v1.LoadCsv",
                "name": "Demo Data",
                "id": input_id,
                "baseType": "input",
                "nextNodes": [{"namespace": "Default", "nextNodeId": container_id, "nextNamespace": "Default"}],
                "serialize": False,
                "description": None,
                "connectionId": conn_id,
                "connectionAttributes": {},
                "fields": fields,
                "actions": [],
                "debugModeRowLimit": 393216,
                "originalDataTypes": {},
                "randomSampling": None,
                "updateTimestamp": None,
                "restrictedFields": {},
                "userRenamedFields": {},
                "selectedFields": None,
                "samplingType": None,
                "groupByFields": None,
                "filters": [],
                "separator": ",",
                "locale": "en_US",
                "charSet": "UTF-8",
                "containsHeaders": True,
                "textQualifier": "A",
            },
            container_id: {
                "nodeType": ".v1.Container",
                "name": "Shift Dates",
                "id": container_id,
                "baseType": "container",
                "nextNodes": [{"namespace": "Default", "nextNodeId": output_id, "nextNamespace": "Default"}],
                "serialize": False,
                "loomContainer": {
                    "parameters": {"parameters": {}},
                    "initialNodes": [add_date_id],
                    "nodes": {
                        add_date_id: {
                            "nodeType": ".v1.AddColumn",
                            "columnName": date_column,
                            "expression": f"DATEADD('day', [Day_Offset], TODAY())",
                            "name": f"Calculate {date_column}",
                            "id": add_date_id,
                            "baseType": "transform",
                            "nextNodes": [],
                            "serialize": False,
                        },
                    },
                    "connections": {},
                    "dataConnections": {},
                    "connectionIds": [],
                    "dataConnectionIds": [],
                    "nodeProperties": {},
                    "extensibility": None,
                },
                "namespacesToInput": {"Default": {"nodeId": add_date_id, "namespace": "Default"}},
                "namespacesToOutput": {"Default": {"nodeId": add_date_id, "namespace": "Default"}},
                "providedParameters": None,
            },
            output_id: {
                "nodeType": ".v1.PublishExtract",
                "name": "Output",
                "id": output_id,
                "baseType": "output",
                "nextNodes": [],
                "serialize": False,
                "description": None,
                "projectName": project_name,
                "projectLuid": project_luid,
                "datasourceName": datasource_name,
                "datasourceDescription": "",
                "serverUrl": f"{server_url}/#/site/{site_name}",
            },
        },
        "connections": {
            conn_id: {
                "connectionType": ".v1.SqlConnection",
                "id": conn_id,
                "name": csv_filename,
                "isPackaged": True,
                "connectionAttributes": {"filename": csv_filename, "class": "textscan"},
            },
        },
        "dataConnections": {},
        "connectionIds": [conn_id],
        "dataConnectionIds": [],
        "nodeProperties": {},
        "extensibility": None,
        "selection": [],
        "majorVersion": 1,
        "minorVersion": 0,
        "documentId": str(uuid.uuid4()),
        "obfuscatorId": str(uuid.uuid4()),
    }

    metadata = {
        "majorVersion": 1,
        "minorVersion": 0,
        "flowEntryName": "flow",
        "displaySettingsEntryName": "displaySettings",
        "isPackagedMaestroDocument": True,
        "documentFeaturesUsedInDocument": [],
    }

    display_settings = {
        "majorVersion": 1,
        "minorVersion": 0,
        "fieldOrder": {"fieldOrdinals": {}, "minOrdinal": 0, "maxOrdinal": 0},
        "flowDisplaySettings": {
            "flowGroupNodeDisplay": {},
            "flowSelection": {"type": "nothing", "selectedNodePath": None, "selectedType": None},
            "flowNodeDisplaySettings": {
                input_id: {"color": {"hexCss": "#4E79A7", "rgba": ["78", "121", "167", "1"]}, "position": {"x": 0, "y": 0}, "size": {"width": 1, "height": 1}},
                container_id: {"color": {"hexCss": "#F28E2B", "rgba": ["242", "142", "43", "1"]}, "position": {"x": 1, "y": 0}, "size": {"width": 1, "height": 1}},
                output_id: {"color": {"hexCss": "#59A14F", "rgba": ["89", "161", "79", "1"]}, "position": {"x": 2, "y": 0}, "size": {"width": 1, "height": 1}},
            },
        },
        "hiddenColumns": [],
    }

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("flow", json.dumps(flow))
        zf.writestr("maestroMetadata", json.dumps(metadata))
        zf.writestr("displaySettings", json.dumps(display_settings))
        zf.writestr(f"Data/{conn_id}/{csv_filename}", csv_bytes)

    return output_path


def publish_and_run_flow(
    flow_path: str,
    flow_name: str,
    project_id: str,
    server,
    auth_token: str,
    site_id: str,
) -> dict:
    """
    Publish a .tflx flow to Tableau Cloud and run it immediately.

    Args:
        flow_path: Path to the .tflx file
        flow_name: Display name for the flow on Tableau Cloud
        project_id: Project LUID to publish into
        server: TSC Server object (already authenticated)
        auth_token: Auth token for REST API calls
        site_id: Site LUID

    Returns:
        dict with 'flow_id', 'job_id', 'success', 'error'
    """
    import requests
    import time
    import tableauserverclient as TSC
    import xml.etree.ElementTree as ET

    result = {"flow_id": None, "job_id": None, "success": False, "error": None}

    try:
        flow_item = TSC.FlowItem(project_id=project_id, name=flow_name)
        published = server.flows.publish(flow_item, flow_path, mode="Overwrite")
        result["flow_id"] = published.id
    except Exception as e:
        if "already exists" in str(e).lower() or "409" in str(e):
            all_flows, _ = server.flows.get()
            for f in all_flows:
                if f.name == flow_name and f.project_id == project_id:
                    result["flow_id"] = f.id
                    break
            if not result["flow_id"]:
                result["error"] = f"Flow exists but couldn't find it: {e}"
                return result
            # Overwrite
            flow_item = TSC.FlowItem(project_id=project_id, name=flow_name)
            flow_item._id = result["flow_id"]
            published = server.flows.publish(flow_item, flow_path, mode="Overwrite")
            result["flow_id"] = published.id
        else:
            result["error"] = str(e)
            return result

    # Run the flow
    headers = {"X-Tableau-Auth": auth_token, "Content-Type": "application/xml"}
    base = f"{server.server_address}/api/{server.version}/sites/{site_id}"
    r = requests.post(f"{base}/flows/{result['flow_id']}/run", headers=headers, data="<tsRequest></tsRequest>")

    if r.status_code != 200:
        result["error"] = f"Run failed: {r.status_code} {r.text[:200]}"
        return result

    root = ET.fromstring(r.text)
    ns = {"t": "http://tableau.com/api"}
    job = root.find(".//t:job", ns)
    result["job_id"] = job.get("id") if job is not None else None

    # Poll for completion
    headers_json = {"X-Tableau-Auth": auth_token, "Accept": "application/json"}
    for _ in range(30):
        time.sleep(10)
        r = requests.get(f"{base}/jobs/{result['job_id']}", headers=headers_json)
        if r.status_code == 200:
            j = r.json().get("job", {})
            if j.get("completedAt"):
                if j.get("finishCode") == "0":
                    result["success"] = True
                else:
                    result["error"] = j.get("runFlowJobType", {}).get("notes", "Unknown error")
                break

    return result
