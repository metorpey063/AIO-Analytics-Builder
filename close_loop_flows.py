"""
Salesforce Flow metadata generators for close_loop.py.

Every demo gets ONE follow-up, built from these pieces:
  followup_flow  — autolaunched; creates the story's records (no callouts). Invocable via REST + subflow.
  notify_flow    — record-triggered on the anchor record; posts the "done" card to Slack (or Chatter)
                   on an async-after-commit path (callouts can't share a transaction with the DML).
  Trigger (one of):
    slack_button      → alert_flow (posts the insight card with a "Create follow-ups" link)
                        + screen_flow (the link target: confirm → run followup_flow → done)
    record_triggered  → signal_flow (Task with the signal Subject is created → run followup_flow)

Output is Metadata API (mdapi) XML. Elements are emitted in the order Salesforce
retrieves them (base fields first, then alphabetical) so files diff cleanly against retrieves.
"""

from xml.sax.saxutils import escape as _x

API_VERSION = "62.0"
NS = "http://soap.sforce.com/2006/04/metadata"

TOP_ORDER = ["actionCalls", "apiVersion", "description", "environments", "formulas", "interviewLabel", "label",
             "processMetadataValues", "processType", "recordCreates", "recordLookups", "screens", "start", "status",
             "subflows", "textTemplates", "variables"]


class Ref:
    """An elementReference value (a variable, formula, template, or $Record field)."""
    def __init__(self, name):
        self.name = name


def _t(tag, text):
    return f"<{tag}>{_x(str(text))}</{tag}>"


def _val(v):
    if isinstance(v, Ref):
        return f"<value><elementReference>{_x(v.name)}</elementReference></value>"
    if isinstance(v, bool):
        return f"<value><booleanValue>{'true' if v else 'false'}</booleanValue></value>"
    if isinstance(v, (int, float)):
        return f"<value><numberValue>{v}</numberValue></value>"
    return f"<value><stringValue>{_x(str(v))}</stringValue></value>"


def _head(name, label, y=0):
    return f"{_t('name', name)}{_t('label', label)}<locationX>176</locationX><locationY>{y}</locationY>"


def _conn(target):
    return f"<connector><targetReference>{target}</targetReference></connector>" if target else ""


def _flow(label, description, process_type, start, parts):
    meta = "".join(
        f"<processMetadataValues>{_t('name', k)}<value><stringValue>{v}</stringValue></value></processMetadataValues>"
        for k, v in (("BuilderType", "LightningFlowBuilder"), ("CanvasMode", "AUTO_LAYOUT_CANVAS"),
                     ("OriginBuilderType", "LightningFlowBuilder")))
    parts = {**parts,
             "apiVersion": [API_VERSION], "description": [_x(description[:2000])], "environments": ["Default"],
             "interviewLabel": [_x(label[:200]) + " {!$Flow.CurrentDateTime}"], "label": [_x(label[:255])],
             "processMetadataValues": [meta], "processType": [process_type], "start": [start], "status": ["Active"]}
    body = []
    for tag in TOP_ORDER:
        for chunk in parts.get(tag, []):
            # processMetadataValues is pre-wrapped (several sibling elements)
            body.append(chunk if tag == "processMetadataValues" else f"<{tag}>{chunk}</{tag}>")
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<Flow xmlns="{NS}">' + "".join(body) + "</Flow>\n"


def _start(target):
    return f"<locationX>50</locationX><locationY>0</locationY>{_conn(target)}"


def _record_start(obj, field, value, async_target=None, sync_target=None, operator="EqualTo"):
    """After-save record trigger on create, filtered on one field (EqualTo / StartsWith)."""
    async_path = (f"<scheduledPaths>{_conn(async_target)}<pathType>AsyncAfterCommit</pathType></scheduledPaths>"
                  if async_target else "")
    return (f"<locationX>50</locationX><locationY>0</locationY>{_conn(sync_target)}"
            f"<filterLogic>and</filterLogic>"
            f"<filters>{_t('field', field)}{_t('operator', operator)}{_val(value)}</filters>"
            f"{_t('object', obj)}<recordTriggerType>Create</recordTriggerType>{async_path}"
            f"<triggerType>RecordAfterSave</triggerType>")


def _text_template(name, text):
    return f"{_t('name', name)}<isViewedAsPlainText>true</isViewedAsPlainText>{_t('text', text)}"


def _post_action(name, post, template, chatter_target):
    """post = {"mode": "slack", "action": ..., "inputs": {inputName: value|"__MESSAGE__"}} or {"mode": "chatter"}."""
    if post.get("mode") == "slack":
        params = "".join(
            f"<inputParameters>{_t('name', k)}{_val(Ref(template) if v == '__MESSAGE__' else v)}</inputParameters>"
            for k, v in post["inputs"].items())
        action = post["action"]
        label = "Post to Slack"
    else:
        params = (f"<inputParameters><name>text</name>{_val(Ref(template))}</inputParameters>"
                  f"<inputParameters><name>subjectNameOrId</name>{_val(Ref(chatter_target))}</inputParameters>")
        action = "chatterPost"
        label = "Post to Chatter"
    return (f"{_head(name, label, 200)}{_t('actionName', action)}{_t('actionType', action)}"
            f"{params}<storeOutputAutomatically>true</storeOutputAutomatically>")


# ── Flow builders ─────────────────────────────────────────────────────────────

def _record_lookup(name, label_, y, sobject, field, value, output_var, target):
    """recordLookups element: find one record by a field value, store its Id."""
    return (f"{_head(name, label_, y)}{_conn(target)}"
            f"<filterLogic>and</filterLogic>"
            f"<filters>{_t('field', field)}{_t('operator', 'EqualTo')}{_val(value)}</filters>"
            f"<getFirstRecordOnly>true</getFirstRecordOnly>"
            f"{_t('object', sobject)}"
            f"<storeOutputAutomatically>true</storeOutputAutomatically>")


def followup_flow(label, description, records, golden_record=None):
    """records: [{"sobject": "Task", "fields": {...}, "dates": {"ActivityDate": 2}}]. Outputs firstRecordId.

    golden_record: optional {"id": "001...", "name": "Acme Corp", "type": "Account"}
    When provided, a recordLookups step finds the record by Id at runtime and the
    created records get WhatId (Tasks) or AccountId (Cases) linked to it.
    """
    lookups = []
    lookup_vars = []
    first_step = "Create_1"

    if golden_record:
        gr_id = golden_record["id"]
        gr_type = golden_record.get("type", "Account")
        first_step = "Lookup_Golden_Record"
        lookups.append(_record_lookup(
            "Lookup_Golden_Record", f"Find {golden_record.get('name', gr_type)}",
            50, gr_type, "Id", gr_id, "goldenRecord", "Create_1"))

    creates, formulas, offsets = [], [], {}
    for i, rec in enumerate(records):
        assigns = "".join(f"<inputAssignments>{_t('field', k)}{_val(v)}</inputAssignments>"
                          for k, v in rec["fields"].items())
        for field, days in rec.get("dates", {}).items():
            fname = offsets.setdefault(days, f"today_plus_{days}")
            assigns += f"<inputAssignments>{_t('field', field)}{_val(Ref(fname))}</inputAssignments>"
        if golden_record:
            gr_type = golden_record.get("type", "Account")
            if rec["sobject"] == "Task" and gr_type in ("Account", "Opportunity", "Case"):
                assigns += f"<inputAssignments>{_t('field', 'WhatId')}{_val(Ref('Lookup_Golden_Record.Id'))}</inputAssignments>"
            elif rec["sobject"] == "Case" and gr_type == "Account":
                assigns += f"<inputAssignments>{_t('field', 'AccountId')}{_val(Ref('Lookup_Golden_Record.Id'))}</inputAssignments>"
        nxt = f"Create_{i + 2}" if i + 1 < len(records) else None
        rid = "<assignRecordIdToReference>firstRecordId</assignRecordIdToReference>" if i == 0 else ""
        head = _head(f"Create_{i + 1}", f"Create {rec['sobject']} {i + 1}", 100 * (i + 1) + (100 if golden_record else 0))
        creates.append(f"{head}"
                       f"{rid}{_conn(nxt)}{assigns}{_t('object', rec['sobject'])}")
    for days, fname in offsets.items():
        formulas.append(f"{_t('name', fname)}<dataType>Date</dataType>{_t('expression', f'TODAY() + {days}')}")
    var = ("<name>firstRecordId</name><dataType>String</dataType><isCollection>false</isCollection>"
           "<isInput>false</isInput><isOutput>true</isOutput>")
    return _flow(label, description, "AutoLaunchedFlow", _start(first_step),
                 {"recordCreates": creates, "recordLookups": lookups, "formulas": formulas, "variables": [var]})


def notify_flow(label, description, obj, filter_field, filter_value, message, post, chatter_target="$Record.CreatedById"):
    """Posts `message` (may contain {!$Record.Id}) once the anchor record commits."""
    return _flow(label, description, "AutoLaunchedFlow",
                 _record_start(obj, filter_field, filter_value, async_target="Post_Message"),
                 {"actionCalls": [_post_action("Post_Message", post, "messageText", chatter_target)],
                  "textTemplates": [_text_template("messageText", message)]})


def alert_flow(label, description, message, post):
    """Autolaunched: posts the insight card (with the Create-follow-ups link). Invoked before/at the demo."""
    return _flow(label, description, "AutoLaunchedFlow", _start("Post_Message"),
                 {"actionCalls": [_post_action("Post_Message", post, "messageText", "$User.Id")],
                  "textTemplates": [_text_template("messageText", message)]})


def screen_flow(label, description, followup_api, confirm_html, done_html, button_label):
    """Link target from the alert: confirm screen → run follow-up subflow → done screen (with record link)."""
    def screen(name, label_, html, target, finish_label):
        return (f"{_head(name, label_, 100)}<allowBack>false</allowBack><allowFinish>true</allowFinish>"
                f"<allowPause>false</allowPause>{_conn(target)}"
                f"<fields>{_t('name', name + '_text')}{_t('fieldText', html)}<fieldType>DisplayText</fieldType></fields>"
                f"{_t('nextOrFinishButtonLabel', finish_label)}<showFooter>true</showFooter><showHeader>true</showHeader>")
    sub = (f"{_head('Run_Followup', 'Run Follow-up', 200)}{_conn('Done')}{_t('flowName', followup_api)}"
           f"<storeOutputAutomatically>true</storeOutputAutomatically>")
    return _flow(label, description, "Flow", _start("Confirm"),
                 {"screens": [screen("Confirm", "Confirm", confirm_html, "Run_Followup", button_label),
                              screen("Done", "Done", done_html, None, "Finish")],
                  "subflows": [sub]})


def signal_flow(label, description, signal_prefix, followup_api):
    """When a Task whose Subject starts with the signal prefix is created, run the follow-up automatically."""
    sub = (f"{_head('Run_Followup', 'Run Follow-up', 200)}{_t('flowName', followup_api)}"
           f"<storeOutputAutomatically>true</storeOutputAutomatically>")
    return _flow(label, description, "AutoLaunchedFlow",
                 _record_start("Task", "Subject", signal_prefix, sync_target="Run_Followup", operator="StartsWith"),
                 {"subflows": [sub]})


def record_action_screen_flow(label, description, followup_api, confirm_html, done_html, button_label):
    """Screen Flow launched from a record-page Quick Action. Receives recordId automatically.
    Confirm screen → run follow-up subflow → done screen with link to created record."""
    def screen(name, label_, html, target, finish_label):
        return (f"{_head(name, label_, 100)}<allowBack>false</allowBack><allowFinish>true</allowFinish>"
                f"<allowPause>false</allowPause>{_conn(target)}"
                f"<fields>{_t('name', name + '_text')}{_t('fieldText', html)}<fieldType>DisplayText</fieldType></fields>"
                f"{_t('nextOrFinishButtonLabel', finish_label)}<showFooter>true</showFooter><showHeader>true</showHeader>")
    sub = (f"{_head('Run_Followup', 'Run Follow-up', 200)}{_conn('Done')}{_t('flowName', followup_api)}"
           f"<storeOutputAutomatically>true</storeOutputAutomatically>")
    var = ("<name>recordId</name><dataType>String</dataType><isCollection>false</isCollection>"
           "<isInput>true</isInput><isOutput>false</isOutput>")
    return _flow(label, description, "Flow", _start("Confirm"),
                 {"screens": [screen("Confirm", "Confirm", confirm_html, "Run_Followup", button_label),
                              screen("Done", "Done", done_html, None, "Finish")],
                  "subflows": [sub], "variables": [var]})


def quick_action_xml(sobject_type, action_name, flow_api_name, label):
    """QuickAction metadata XML: a Flow-type action on a record page."""
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<QuickAction xmlns="{NS}">\n'
            f"    <flowDefinition>{_x(flow_api_name)}</flowDefinition>\n"
            f"    <label>{_x(label)}</label>\n"
            f"    <optionsCreateFeedItem>false</optionsCreateFeedItem>\n"
            f"    <type>Flow</type>\n"
            f"</QuickAction>\n")


def record_action_deployment_xml(sobject_type, action_member, label):
    """RecordActionDeployment metadata XML: pins the Quick Action to the record page."""
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<RecordActionDeployment xmlns="{NS}">\n'
            f"    <masterLabel>{_x(label)}</masterLabel>\n"
            f"    <hasGuidedActions>true</hasGuidedActions>\n"
            f"    <shouldLaunchActionOnReject>false</shouldLaunchActionOnReject>\n"
            f"    <deploymentContexts>\n"
            f"        <entityName>{_x(sobject_type)}</entityName>\n"
            f"    </deploymentContexts>\n"
            f"    <channels>\n"
            f"        <channelItems>\n"
            f"            <channel>Default</channel>\n"
            f"            <defaultItems>\n"
            f"                <action>{_x(action_member)}</action>\n"
            f"                <pinned>Top</pinned>\n"
            f"                <position>1</position>\n"
            f"                <type>QuickAction</type>\n"
            f"            </defaultItems>\n"
            f"        </channelItems>\n"
            f"    </channels>\n"
            f"</RecordActionDeployment>\n")


def package_xml(flow_names=(), quick_action_members=(), deployment_names=()):
    """package.xml for a deploy. Supports Flows, QuickActions, and RecordActionDeployments."""
    if not flow_names and not quick_action_members and not deployment_names:
        return f'<?xml version="1.0" encoding="UTF-8"?>\n<Package xmlns="{NS}"><version>{API_VERSION}</version></Package>\n'
    types = []
    if flow_names:
        members = "".join(f"<members>{n}</members>" for n in flow_names)
        types.append(f"<types>{members}<name>Flow</name></types>")
    if quick_action_members:
        members = "".join(f"<members>{n}</members>" for n in quick_action_members)
        types.append(f"<types>{members}<name>QuickAction</name></types>")
    if deployment_names:
        members = "".join(f"<members>{n}</members>" for n in deployment_names)
        types.append(f"<types>{members}<name>RecordActionDeployment</name></types>")
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<Package xmlns="{NS}">'
            f"{''.join(types)}<version>{API_VERSION}</version></Package>\n")
