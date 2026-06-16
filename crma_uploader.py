"""CRM Analytics (Wave) dataset uploader.

Handles the three-phase upload process: create job with metadata,
upload base64-encoded CSV parts, trigger processing, and poll.
"""

import base64
import json
import time
from typing import Any, Dict, List, Optional, Tuple

import requests


CHUNK_SIZE = 9 * 1024 * 1024  # 9 MB per part (before base64 encoding)


def build_metadata(
    dataset_name: str,
    dataset_label: str,
    fields: List[Dict[str, Any]],
) -> dict:
    """Build the metadata JSON for a CRMA dataset upload.

    Args:
        dataset_name: API name (no spaces, underscores OK)
        dataset_label: Display label
        fields: List of field dicts with keys: name, label, type, and
                optionally precision/scale (Numeric) or format (Date)
    """
    return {
        "fileFormat": {
            "charsetName": "UTF-8",
            "fieldsDelimitedBy": ",",
            "linesTerminatedBy": "\n",
        },
        "objects": [
            {
                "connector": "CSV",
                "fullyQualifiedName": dataset_name,
                "label": dataset_label,
                "name": dataset_name,
                "fields": fields,
            }
        ],
    }


def build_field(name: str, label: str, field_type: str, **kwargs) -> dict:
    """Build a single field definition for CRMA metadata.

    Args:
        name: Column name in CSV (maps to SAQL field name)
        label: Display label in UI
        field_type: "Text", "Numeric", or "Date"
        **kwargs: Additional properties (precision, scale, format, defaultValue)
    """
    field = {
        "fullyQualifiedName": f"{name}",
        "label": label,
        "name": name,
        "type": field_type,
        "isSystemField": False,
    }
    if field_type == "Numeric":
        field["precision"] = kwargs.get("precision", 18)
        field["scale"] = kwargs.get("scale", 4)
        field["defaultValue"] = str(kwargs.get("defaultValue", "0"))
    elif field_type == "Date":
        field["format"] = kwargs.get("format", "yyyy-MM-dd")
    return field


def fields_from_metric_config(
    metric_configs: List[Dict[str, Any]],
    dimension_names: List[str],
) -> List[Dict[str, Any]]:
    """Generate CRMA field definitions from METRIC_CONFIG and dimension list.

    Produces: record_id (Text), date (Date), each dimension (Text),
    each metric field (Numeric).
    """
    fields = [
        build_field("record_id", "Record ID", "Text"),
        build_field("date", "Date", "Date", format="yyyy-MM-dd"),
    ]
    for dim in dimension_names:
        fields.append(build_field(dim, dim.replace("_", " ").title(), "Text"))
    for mc in metric_configs:
        fname = mc["field"]
        flabel = mc["label"]
        scale = 4 if mc.get("agg") == "Average" else 2
        fields.append(build_field(fname, flabel, "Numeric", precision=18, scale=scale))
    return fields


def upload_dataset(
    sf_instance: str,
    sf_token: str,
    dataset_name: str,
    dataset_label: str,
    metadata: dict,
    csv_bytes: bytes,
    operation: str = "Overwrite",
    app_name: Optional[str] = None,
) -> Tuple[str, str]:
    """Upload a CSV dataset to CRM Analytics.

    Args:
        sf_instance: Salesforce instance URL
        sf_token: Bearer token
        dataset_name: API name for the dataset
        dataset_label: Display label
        metadata: Metadata dict (from build_metadata)
        csv_bytes: Raw CSV content as bytes
        operation: "Overwrite", "Append", "Upsert", or "Delete"
        app_name: Optional CRMA app/folder name to place the dataset in

    Returns:
        Tuple of (job_id, dataset_id)
    """
    headers = {"Authorization": f"Bearer {sf_token}", "Content-Type": "application/json"}
    api_base = f"{sf_instance}/services/data/v61.0"

    metadata_b64 = base64.b64encode(json.dumps(metadata).encode("utf-8")).decode("utf-8")

    # Phase 1: Create job
    job_payload = {
        "EdgemartAlias": dataset_name,
        "EdgemartLabel": dataset_label,
        "Format": "Csv",
        "Operation": operation,
        "Action": "None",
        "MetadataJson": metadata_b64,
    }
    if app_name:
        job_payload["EdgemartContainer"] = app_name

    r = requests.post(f"{api_base}/sobjects/InsightsExternalData", headers=headers, json=job_payload)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"Job creation failed ({r.status_code}): {r.text[:300]}")
    job_id = r.json()["id"]
    print(f"  CRMA job created: {job_id}")

    # Phase 2: Upload parts
    num_chunks = (len(csv_bytes) + CHUNK_SIZE - 1) // CHUNK_SIZE
    for i in range(num_chunks):
        chunk = csv_bytes[i * CHUNK_SIZE : (i + 1) * CHUNK_SIZE]
        chunk_b64 = base64.b64encode(chunk).decode("utf-8")
        part_payload = {
            "InsightsExternalDataId": job_id,
            "PartNumber": i + 1,
            "DataFile": chunk_b64,
        }
        r = requests.post(f"{api_base}/sobjects/InsightsExternalDataPart", headers=headers, json=part_payload)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"Part upload failed ({r.status_code}): {r.text[:300]}")
    print(f"  Uploaded {num_chunks} part(s) ({len(csv_bytes):,} bytes)")

    # Phase 3: Trigger processing
    r = requests.patch(f"{api_base}/sobjects/InsightsExternalData/{job_id}",
                       headers=headers, json={"Action": "Process"})
    if r.status_code not in (200, 204):
        raise RuntimeError(f"Process trigger failed ({r.status_code}): {r.text[:300]}")
    print("  Processing triggered...")

    # Poll for completion
    dataset_id = None
    for attempt in range(60):
        time.sleep(10)
        r = requests.get(f"{api_base}/sobjects/InsightsExternalData/{job_id}", headers=headers)
        if r.status_code != 200:
            continue
        status = r.json().get("Status")
        print(f"    [{attempt+1}] Status: {status}")
        if status in ("Completed", "CompletedWithWarnings"):
            dataset_id = r.json().get("EdgemartId", "")
            break
        elif status == "Failed":
            msg = r.json().get("StatusMessage", "Unknown error")
            raise RuntimeError(f"CRMA upload failed: {msg}")

    if not dataset_id:
        # Try to find dataset by name
        r = requests.get(f"{api_base}/wave/datasets", headers=headers, params={"q": dataset_name})
        if r.status_code == 200:
            datasets = r.json().get("datasets", [])
            for ds in datasets:
                if ds.get("name") == dataset_name:
                    dataset_id = ds["id"]
                    break

    print(f"  Dataset ready: {dataset_id}")
    return job_id, dataset_id or ""


def set_security_predicate(
    sf_instance: str,
    sf_token: str,
    dataset_id: str,
    predicate: str,
) -> bool:
    """Set a security predicate on the current version of a dataset.

    Args:
        predicate: e.g. "'owner_id' == \"$User.Id\""
    """
    headers = {"Authorization": f"Bearer {sf_token}", "Content-Type": "application/json"}
    api_base = f"{sf_instance}/services/data/v61.0"

    r = requests.get(f"{api_base}/wave/datasets/{dataset_id}", headers=headers)
    if r.status_code != 200:
        return False
    version_id = r.json().get("currentVersionId")
    if not version_id:
        return False

    r = requests.patch(
        f"{api_base}/wave/datasets/{dataset_id}/versions/{version_id}",
        headers=headers,
        json={"predicate": predicate},
    )
    return r.status_code in (200, 204)
