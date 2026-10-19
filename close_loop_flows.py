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
             "processMetadataValues", "processType", "recordCreates", "screens", "start", "status", "subflows",
             "textTemplates", "variables"]


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

def followup_flow(label, description, records):
    """records: [{"sobject": "Task", "fields": {...}, "dates": {"ActivityDate": 2}}]. Outputs firstRecordId."""
    creates, formulas, offsets = [], [], {}
    for i, rec in enumerate(records):
        assigns = "".join(f"<inputAssignments>{_t('field', k)}{_val(v)}</inputAssignments>"
                          for k, v in rec["fields"].items())
        for field, days in rec.get("dates", {}).items():
            fname = offsets.setdefault(days, f"today_plus_{days}")
            assigns += f"<inputAssignments>{_t('field', field)}{_val(Ref(fname))}</inputAssignments>"
        nxt = f"Create_{i + 2}" if i + 1 < len(records) else None
        rid = "<assignRecordIdToReference>firstRecordId</assignRecordIdToReference>" if i == 0 else ""
        head = _head(f"Create_{i + 1}", f"Create {rec['sobject']} {i + 1}", 100 * (i + 1))
        creates.append(f"{head}"
                       f"{rid}{_conn(nxt)}{assigns}{_t('object', rec['sobject'])}")
    for days, fname in offsets.items():
        formulas.append(f"{_t('name', fname)}<dataType>Date</dataType>{_t('expression', f'TODAY() + {days}')}")
    var = ("<name>firstRecordId</name><dataType>String</dataType><isCollection>false</isCollection>"
           "<isInput>false</isInput><isOutput>true</isOutput>")
    return _flow(label, description, "AutoLaunchedFlow", _start("Create_1"),
                 {"recordCreates": creates, "formulas": formulas, "variables": [var]})


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


def package_xml(flow_names=()):
    """package.xml for a deploy; package_xml() (no members) is the companion for destructiveChanges."""
    if not flow_names:
        return f'<?xml version="1.0" encoding="UTF-8"?>\n<Package xmlns="{NS}"><version>{API_VERSION}</version></Package>\n'
    members = "".join(f"<members>{n}</members>" for n in flow_names)
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<Package xmlns="{NS}">'
            f"<types>{members}<name>Flow</name></types><version>{API_VERSION}</version></Package>\n")
