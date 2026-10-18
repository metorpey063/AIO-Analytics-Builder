"""
CRM record upserter for AIO Analytics Builder.

Creates or upserts Salesforce sObject records (Accounts, Contacts, Cases, etc.)
alongside analytics demo data, so that Tableau Next drill-downs can link to real
CRM records and trigger Flows/Actions.

Usage in a demo script:
    from crm_upserter import ensure_external_id_field, upsert_crm_records

    # 1. Make sure the External ID field exists on the target object
    ensure_external_id_field(sf_token, sf_instance, "Account", "Demo_External_ID__c")

    # 2. Build CRM records with matching external IDs
    accounts = [
        {"Name": "Acme Corp", "Industry": "Technology", "Demo_External_ID__c": "DDI-0001"},
        ...
    ]

    # 3. Upsert them (idempotent — safe to re-run)
    id_map = upsert_crm_records(sf_token, sf_instance, "Account",
                                 "Demo_External_ID__c", accounts)
    # id_map = {"DDI-0001": "001xx000003GH1pAAG", ...}
"""

import time
import requests

API_VERSION = "v62.0"
COMPOSITE_BATCH_SIZE = 200


def sf_headers(sf_token):
    return {"Authorization": f"Bearer {sf_token}", "Content-Type": "application/json"}


def ensure_external_id_field(sf_token, sf_instance, sobject_type, field_name,
                              field_label=None):
    """Create a custom External ID text field on the given sObject if it doesn't exist.

    Uses the Tooling API to create a CustomField metadata record. The field is
    marked as externalId=true and unique=true so the REST upsert endpoint works.

    Args:
        sf_token: Salesforce access token
        sf_instance: Salesforce instance URL (e.g. https://my-org.my.salesforce.com)
        sobject_type: API name of the sObject (e.g. "Account", "Contact")
        field_name: API name of the field with __c suffix (e.g. "Demo_External_ID__c")
        field_label: Human-readable label. Defaults to field_name without __c.

    Returns:
        True if the field was created, False if it already existed.
    """
    h = sf_headers(sf_token)

    if not field_label:
        field_label = field_name.replace("__c", "").replace("_", " ")

    describe_url = f"{sf_instance}/services/data/{API_VERSION}/sobjects/{sobject_type}/describe"
    r = requests.get(describe_url, headers=h)
    r.raise_for_status()
    existing_fields = {f["name"] for f in r.json()["fields"]}

    if field_name in existing_fields:
        print(f"  External ID field {sobject_type}.{field_name} already exists")
        return False

    # A new custom field gets no FLS for the running user, so describe and the
    # upsert endpoint treat it as nonexistent (404). Check Tooling before creating.
    tq = requests.get(f"{sf_instance}/services/data/{API_VERSION}/tooling/query", headers=h,
                      params={"q": f"SELECT Id FROM CustomField WHERE TableEnumOrId='{sobject_type}' "
                                   f"AND DeveloperName='{field_name.replace('__c', '')}'"})
    if tq.ok and tq.json().get("records"):
        print(f"  External ID field {sobject_type}.{field_name} exists but is hidden — granting access")
        grant_field_access(sf_token, sf_instance, sobject_type, field_name)
        return False

    full_name = f"{sobject_type}.{field_name}"
    payload = {
        "FullName": full_name,
        "Metadata": {
            "label": field_label,
            "type": "Text",
            "length": 80,
            "externalId": True,
            "unique": True,
            "caseSensitive": False,
            "required": False,
            "description": "Auto-created by AIO Analytics Builder for demo record linkage",
        },
    }

    tooling_url = f"{sf_instance}/services/data/{API_VERSION}/tooling/sobjects/CustomField"
    r = requests.post(tooling_url, headers=h, json=payload)

    if r.status_code == 201:
        print(f"  Created External ID field {sobject_type}.{field_name}")
        grant_field_access(sf_token, sf_instance, sobject_type, field_name)
        print(f"  Waiting 30s for field metadata propagation...")
        time.sleep(30)
        return True

    if r.status_code == 400 and "duplicate" in r.text.lower():
        print(f"  External ID field {sobject_type}.{field_name} already exists (race)")
        return False

    r.raise_for_status()
    return True


FIELD_ACCESS_PERMSET = "AIO_Demo_Field_Access"


def grant_field_access(sf_token, sf_instance, sobject_type, field_name):
    """Give the running user read/edit on a field via the AIO_Demo_Field_Access permission set.

    Creates the permission set and assignment if missing. Idempotent.
    """
    h = sf_headers(sf_token)
    base = f"{sf_instance}/services/data/{API_VERSION}"
    q = lambda soql: requests.get(f"{base}/query", headers=h, params={"q": soql}).json().get("records", [])

    ps = q(f"SELECT Id FROM PermissionSet WHERE Name='{FIELD_ACCESS_PERMSET}'")
    if ps:
        ps_id = ps[0]["Id"]
    else:
        r = requests.post(f"{base}/sobjects/PermissionSet", headers=h, json={
            "Name": FIELD_ACCESS_PERMSET, "Label": "AIO Demo Field Access",
            "Description": "Read/edit on AIO Analytics Builder demo External ID fields"})
        r.raise_for_status()
        ps_id = r.json()["id"]

    full = f"{sobject_type}.{field_name}"
    if not q(f"SELECT Id FROM FieldPermissions WHERE ParentId='{ps_id}' AND Field='{full}'"):
        r = requests.post(f"{base}/sobjects/FieldPermissions", headers=h, json={
            "ParentId": ps_id, "SobjectType": sobject_type, "Field": full,
            "PermissionsRead": True, "PermissionsEdit": True})
        r.raise_for_status()

    user_id = requests.get(f"{sf_instance}/services/oauth2/userinfo", headers=h).json()["user_id"]
    if not q(f"SELECT Id FROM PermissionSetAssignment WHERE PermissionSetId='{ps_id}' AND AssigneeId='{user_id}'"):
        r = requests.post(f"{base}/sobjects/PermissionSetAssignment", headers=h,
                          json={"PermissionSetId": ps_id, "AssigneeId": user_id})
        r.raise_for_status()
    print(f"  Granted field access to {full} ({FIELD_ACCESS_PERMSET})")


def upsert_crm_records(sf_token, sf_instance, sobject_type, external_id_field,
                        records, quiet=False):
    """Upsert a list of sObject records using the Composite sObjects Collections API.

    Uses PATCH /composite/sobjects/{SObjectType}/{ExternalIdField} which processes
    up to 200 records per call and is fully idempotent — re-running with the same
    external IDs updates existing records rather than creating duplicates.

    Args:
        sf_token: Salesforce access token
        sf_instance: Salesforce instance URL
        sobject_type: API name of the sObject (e.g. "Account")
        external_id_field: API name of the External ID field (e.g. "Demo_External_ID__c")
        records: List of dicts, each with the external_id_field plus standard fields.
                 Do NOT include "attributes" or "Id" — the API adds them.
        quiet: If True, suppress per-batch progress prints.

    Returns:
        dict mapping external_id_value → Salesforce record ID for all successful upserts.
        Raises RuntimeError if any record fails with a non-duplicate error.
    """
    h = sf_headers(sf_token)
    url = (f"{sf_instance}/services/data/{API_VERSION}/composite/sobjects/"
           f"{sobject_type}/{external_id_field}")

    id_map = {}
    total = len(records)
    created = 0
    updated = 0
    errors = []

    for batch_start in range(0, total, COMPOSITE_BATCH_SIZE):
        batch = records[batch_start:batch_start + COMPOSITE_BATCH_SIZE]

        payload = {
            "allOrNone": False,
            "records": [
                {**rec, "attributes": {"type": sobject_type}}
                for rec in batch
            ],
        }

        r = None
        for retry in range(5):
            r = requests.patch(url, headers=h, json=payload)
            if r.status_code == 404:
                wait = 15 * (retry + 1)
                print(f"    404 — field not yet available, retrying in {wait}s "
                      f"(attempt {retry+1}/5)...")
                time.sleep(wait)
                continue
            break

        r.raise_for_status()
        results = r.json()

        for i, result in enumerate(results):
            ext_id = batch[i].get(external_id_field, f"record_{batch_start + i}")

            if result.get("success"):
                id_map[ext_id] = result["id"]
                if result.get("created"):
                    created += 1
                else:
                    updated += 1
            else:
                err_msgs = [e.get("message", "Unknown error") for e in result.get("errors", [])]
                errors.append({"external_id": ext_id, "errors": err_msgs})

        if not quiet:
            done = min(batch_start + COMPOSITE_BATCH_SIZE, total)
            print(f"  {sobject_type}: {done}/{total} "
                  f"(created: {created}, updated: {updated})")

    if errors:
        print(f"\n  WARNING: {len(errors)} record(s) failed:")
        for e in errors[:5]:
            print(f"    {e['external_id']}: {'; '.join(e['errors'])}")
        if len(errors) > 5:
            print(f"    ... and {len(errors) - 5} more")

    print(f"  {sobject_type} upsert complete: "
          f"{created} created, {updated} updated, {len(errors)} failed")

    return id_map


def delete_demo_records(sf_token, sf_instance, sobject_type, external_id_field,
                         external_ids):
    """Delete specific demo records by their External ID values.

    Useful for cleanup on retry. Looks up records by External ID, then deletes them.

    Args:
        sf_token: Salesforce access token
        sf_instance: Salesforce instance URL
        sobject_type: API name of the sObject
        external_id_field: API name of the External ID field
        external_ids: List of external ID values to delete

    Returns:
        int — number of records successfully deleted
    """
    h = sf_headers(sf_token)
    deleted = 0

    for ext_id in external_ids:
        url = (f"{sf_instance}/services/data/{API_VERSION}/sobjects/"
               f"{sobject_type}/{external_id_field}/{ext_id}")
        r = requests.delete(url, headers=h)

        if r.status_code == 204:
            deleted += 1
        elif r.status_code == 404:
            pass  # already gone
        else:
            print(f"  Warning: failed to delete {sobject_type} {ext_id}: {r.status_code}")

    print(f"  Deleted {deleted}/{len(external_ids)} {sobject_type} records")
    return deleted


def query_records(sf_token, sf_instance, soql):
    """Run a SOQL query and return all records (handles pagination).

    Args:
        sf_token: Salesforce access token
        sf_instance: Salesforce instance URL
        soql: SOQL query string

    Returns:
        list of record dicts
    """
    h = sf_headers(sf_token)
    url = f"{sf_instance}/services/data/{API_VERSION}/query"
    r = requests.get(url, headers=h, params={"q": soql})
    r.raise_for_status()
    body = r.json()
    records = body.get("records", [])

    while not body.get("done", True) and body.get("nextRecordsUrl"):
        r = requests.get(f"{sf_instance}{body['nextRecordsUrl']}", headers=h)
        r.raise_for_status()
        body = r.json()
        records.extend(body.get("records", []))

    return records


def get_record_type_id(sf_token, sf_instance, sobject_type, record_type_name):
    """Look up a RecordType ID by name. Returns None if not found."""
    records = query_records(
        sf_token, sf_instance,
        f"SELECT Id FROM RecordType WHERE SObjectType = '{sobject_type}' "
        f"AND Name = '{record_type_name}' AND IsActive = true LIMIT 1"
    )
    return records[0]["Id"] if records else None
