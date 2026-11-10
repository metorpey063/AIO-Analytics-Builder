"""
"Ask Claude" assistant for the Web UI: Claude with read-only tools over AIO's docs and the user's
demo files, so it can troubleshoot builds instead of guessing.

Read-only by design. Tools can search and read the docs (CLAUDE.md Known Pitfalls, guides, skill
files), read files under demos/ (checkpoints, logs, configs), see recent job logs held by the server
and the list of connections. They can't write anything, run commands, call an org, or read
config.json or any credential. JSON values under secret-looking keys are redacted.

Credentials come from claude_credentials.py (same as the rest of the Web UI). Two transports:
  - the internal Bedrock gateway (/model/{id}/invoke + x-api-key), which the SDK can't call
  - the Anthropic SDK for API keys and OAuth tokens
"""

import json
import re
from pathlib import Path

MODEL = "claude-sonnet-5-5"
GATEWAY_MODEL = "us.anthropic.claude-sonnet-5-5"   # Bedrock gateway ID for the same model
EFFORT = "medium"        # multi-step troubleshooting; plain questions finish quickly anyway
MAX_TOKENS = 16000
MAX_TOOL_ROUNDS = 8
MAX_RESULT_CHARS = 24000

ROOT = Path(__file__).resolve().parent.parent
DEMOS = ROOT / "demos"
ROOT_DOCS = ["CLAUDE.md", "ENGINEERING_GUIDELINES.md", "README.md", "OVERVIEW.md", "ROADMAP.md", "CHANGELOG.md",
             "MCP_BUILD_GUIDE.md", "CRMA_BUILD_PLAYBOOK.md", "discovered_fixes.md", "QUICK_START.txt"]
DOC_GLOBS = [".claude/commands/*.md", "salesinsights/DESIGN.md", "sidekicks/studio/docs/*.md"]
TEXT_EXT = {".json", ".log", ".md", ".txt", ".csv", ".py", ".yaml", ".yml", ".xml", ".html"}
SECRET_NAME = re.compile(r"(secret|token|password|passwd|api[_-]?key|credential|private[_-]?key|\.env$|\.pem$|\.key$)", re.I)
SECRET_VALUE = re.compile(r'("[^"]*(?:secret|token|password|api_key|apikey|refresh|verifier|private_key)[^"]*"\s*:\s*)"[^"]*"', re.I)

PAGE_HINTS = {
    "/": "the Home page (overview, quick stats, getting started)",
    "/build": "the Build Demo wizard (company, story, metrics, output, build)",
    "/setup": "Setup (connecting Tableau Cloud and Salesforce, AI configuration)",
    "/demos": "My Demos (existing builds, walkthroughs, assets)",
    "/connections": "Connections (Salesforce and Tableau Cloud connections, testing auth, the active connection)",
    "/update-rev-intel": "Update Rev Intel Data (tailoring a demo org's Revenue Intelligence data to a customer)",
    "/deploy-sales-insights": "Deploy Sales Insights (deploying the six Sales Insights dashboards to an org with Data Cloud)",
}

TOOLS = [
    {"name": "search_docs",
     "description": "Search AIO's documentation for a word or phrase (case-insensitive). Covers CLAUDE.md (including the "
                    "Known Pitfalls list of API errors and their fixes), ENGINEERING_GUIDELINES.md, the build guides, the "
                    "CHANGELOG, and every skill's instructions (.claude/commands/*.md). Returns matching lines as file:line "
                    "with a little context. Search for the distinctive part of an error message first.",
     "input_schema": {"type": "object", "properties": {
         "query": {"type": "string", "description": "Text to find, e.g. 'Cyclic relationship' or 'minorVersion'"},
         "max_results": {"type": "integer", "description": "Default 20, at most 50"}},
         "required": ["query"], "additionalProperties": False}},
    {"name": "read_doc",
     "description": "Read part of one AIO documentation file found by search_docs or listed by name, e.g. CLAUDE.md or "
                    ".claude/commands/build-demo.md. Use start_line from a search hit to read around it.",
     "input_schema": {"type": "object", "properties": {
         "path": {"type": "string"}, "start_line": {"type": "integer", "description": "1-based, default 1"},
         "line_count": {"type": "integer", "description": "Default 200, at most 400"}},
         "required": ["path"], "additionalProperties": False}},
    {"name": "list_demos",
     "description": "List the user's demo folders under demos/ with their files, newest first, and any checkpoint's "
                    "completed phases. Start here when the user asks about a specific build.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "read_demo_file",
     "description": "Read a text file under demos/, e.g. 'acme_churn/acme_churn_checkpoint.json' or "
                    "'sales_insights/aio_dev/deploy.log'. Use tail_lines for long logs (the end has the error).",
     "input_schema": {"type": "object", "properties": {
         "path": {"type": "string", "description": "Path relative to demos/"},
         "tail_lines": {"type": "integer", "description": "Return only the last N lines"}},
         "required": ["path"], "additionalProperties": False}},
    {"name": "recent_job_logs",
     "description": "Recent build and deploy jobs run from this Web UI session (Build Demo, Update Rev Intel, Deploy "
                    "Sales Insights) with their latest log lines. Call with no job_id to list them, then with a job_id "
                    "for its full recent log.",
     "input_schema": {"type": "object", "properties": {"job_id": {"type": "string"}}, "additionalProperties": False}},
    {"name": "list_connections",
     "description": "The user's saved Salesforce and Tableau Cloud connections: name, org URL or site, which is active, "
                    "and whether each is set up. No credentials.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
]

STATUS = {
    "search_docs": lambda a: f'Searching the docs for "{a.get("query", "")}"…',
    "read_doc": lambda a: f'Reading {a.get("path", "")}…',
    "list_demos": lambda a: "Listing your demos…",
    "read_demo_file": lambda a: f'Reading demos/{a.get("path", "")}…',
    "recent_job_logs": lambda a: "Checking recent job logs…",
    "list_connections": lambda a: "Checking your connections…",
}


# ---- tools --------------------------------------------------------------------------------------

def _doc_files():
    files = [ROOT / p for p in ROOT_DOCS if (ROOT / p).is_file()]
    for g in DOC_GLOBS:
        files += sorted(ROOT.glob(g))
    return [f for f in files if f.is_file()]


def _rel(p):
    return str(p.relative_to(ROOT))


def _clip(text):
    return text if len(text) <= MAX_RESULT_CHARS else text[:MAX_RESULT_CHARS] + "\n…(truncated)"


def search_docs(query, max_results=20):
    q = (query or "").strip().lower()
    if len(q) < 2:
        return "Give a longer search phrase."
    max_results = max(1, min(int(max_results or 20), 50))
    hits = []
    for f in _doc_files():
        lines = f.read_text(errors="replace").splitlines()
        for i, line in enumerate(lines):
            if q in line.lower():
                ctx = lines[max(0, i - 1): i + 2]
                hits.append(f"{_rel(f)}:{i + 1}: " + " ⏎ ".join(l.strip() for l in ctx)[:700])
                if len(hits) >= max_results:
                    return _clip("\n".join(hits) + f"\n(first {max_results} hits; narrow the query for more)")
    return _clip("\n".join(hits)) if hits else f'No matches for "{query}". Try a shorter or different phrase.'


def read_doc(path, start_line=1, line_count=200):
    target = (ROOT / (path or "")).resolve()
    allowed = {f.resolve() for f in _doc_files()}
    if target not in allowed:
        names = ", ".join(_rel(f) for f in _doc_files())
        return f"Not a readable doc: {path}. Readable docs: {names}"
    lines = target.read_text(errors="replace").splitlines()
    start = max(1, int(start_line or 1))
    count = max(1, min(int(line_count or 200), 400))
    chunk = lines[start - 1: start - 1 + count]
    body = "\n".join(f"{start + i}: {l}" for i, l in enumerate(chunk))
    return _clip(f"{_rel(target)} lines {start}-{start + len(chunk) - 1} of {len(lines)}\n{body}")


def list_demos():
    if not DEMOS.is_dir():
        return "No demos folder yet."
    out = []
    dirs = sorted((d for d in DEMOS.iterdir() if d.is_dir() and not d.name.startswith(".")),
                  key=lambda d: d.stat().st_mtime, reverse=True)
    for d in dirs[:40]:
        files = sorted((f for f in d.rglob("*") if f.is_file() and not SECRET_NAME.search(f.name)),
                       key=lambda f: f.stat().st_mtime, reverse=True)
        done = ""
        for cp in [f for f in files if f.name.endswith("checkpoint.json")][:2]:
            try:
                data = json.loads(cp.read_text())
                keys = data.get("done") or [k for k, v in data.items() if v is True]
                done += f" | {cp.relative_to(DEMOS)} done: {keys}"
            except Exception:
                pass
        shown = ", ".join(str(f.relative_to(d)) for f in files[:12])
        out.append(f"{d.name}/ ({len(files)} files){done}\n   {shown}")
    return _clip("\n".join(out)) if out else "No demos yet."


def read_demo_file(path, tail_lines=None):
    target = (DEMOS / (path or "")).resolve()
    if DEMOS.resolve() not in target.parents:
        return "Only files under demos/ can be read."
    if not target.is_file():
        return f"No such file: demos/{path}. Use list_demos to see what exists."
    if SECRET_NAME.search(target.name):
        return "That file looks like it holds credentials, so it can't be read."
    if target.suffix.lower() not in TEXT_EXT:
        return f"Not a text file ({target.suffix}); readable types: {', '.join(sorted(TEXT_EXT))}"
    text = SECRET_VALUE.sub(r'\1"***"', target.read_text(errors="replace"))
    lines = text.splitlines()
    if tail_lines:
        lines = lines[-max(1, min(int(tail_lines), 1000)):]
    elif target.suffix.lower() == ".csv":
        lines = lines[:40] + ([f"…({len(text.splitlines()) - 40} more rows)"] if len(text.splitlines()) > 40 else [])
    return _clip(f"demos/{path} ({len(text.splitlines())} lines)\n" + "\n".join(lines))


def run_tool(name, args, providers):
    try:
        if name == "search_docs":
            return search_docs(args.get("query"), args.get("max_results"))
        if name == "read_doc":
            return read_doc(args.get("path"), args.get("start_line"), args.get("line_count"))
        if name == "list_demos":
            return list_demos()
        if name == "read_demo_file":
            return read_demo_file(args.get("path"), args.get("tail_lines"))
        if name == "recent_job_logs":
            return _clip(providers["jobs"](args.get("job_id")))
        if name == "list_connections":
            return _clip(providers["connections"]())
        return f"Unknown tool {name}"
    except Exception as e:   # a tool failure goes back to Claude as an error result, not a crashed chat
        return f"Tool error: {e}"


# ---- prompt -------------------------------------------------------------------------------------

def _skills():
    out = []
    for f in sorted((ROOT / ".claude" / "commands").glob("*.md")):
        first = next((l for l in f.read_text(errors="replace").splitlines() if l.startswith("# ")), "")
        out.append(first[2:].strip() or f"/{f.stem}")
    return out


def system_prompt(page_context, connections_summary):
    page = (page_context or {}).get("url", "")
    hint = PAGE_HINTS.get(page)
    if not hint and page.startswith("/close-loop/"):
        hint = f"the Close the Loop page for demo '{page.split('/')[-1]}' (golden record, action, trigger, Flow deploy)"
    hint = hint or f"{(page_context or {}).get('page', '')} ({page})"
    skills = "\n".join(f"- {s}" for s in _skills())
    return f"""You are the assistant inside AIO Analytics Builder's Web UI. AIO helps Tableau and Salesforce Solutions Engineers build demos: Tableau Pulse, Tableau Next (Data Cloud, semantic models, vizzes, dashboards), CRM Analytics, close-the-loop Flows, Revenue Intelligence data and the Sales Insights deploy.

You have read-only tools over AIO's docs and the user's demo files. Use them instead of guessing:
- For any error or failed build, search the docs for the distinctive part of the error first. CLAUDE.md's Known Pitfalls documents most API errors with their exact fix. Then read the demo's checkpoint and log, or the recent job logs.
- Cite where an answer comes from (file:line or the log line) so the user can check it.
- You can't change anything: no writes, no commands, no org calls. When a fix needs an action, say exactly what the user should click, or the command to run in Claude Code or a terminal. Many fixes mean re-running a step: builds and deploys are checkpointed and resume.
- Never ask for, guess at or repeat credentials. They aren't readable by your tools.

The user is on {hint}.
{connections_summary}

AIO's skills (run in Claude Code; several also have a Web UI page):
{skills}

Answer the question that was asked, lead with the answer, keep it short, and use plain Markdown."""


# ---- transports -----------------------------------------------------------------------------------

def _call_gateway(cfg, body):
    import requests
    payload = {"anthropic_version": "bedrock-2023-05-31", **body}
    r = requests.post(f"{cfg['base_url']}/model/{GATEWAY_MODEL}/invoke",
                      headers={"x-api-key": cfg["token"], "Content-Type": "application/json"},
                      json=payload, verify=cfg["ca_bundle"], timeout=180)
    if r.status_code != 200:
        raise RuntimeError(f"Claude gateway error {r.status_code}: {r.text[:300]}")
    return r.json()


def _call_sdk(cfg, body):
    import anthropic
    key = cfg.get("api_key", "")
    client = anthropic.Anthropic(auth_token=key) if key.startswith("sk-ant-oat") else anthropic.Anthropic(api_key=key)
    try:
        # server-side refusal fallback: a declined request is retried on a fallback model inside the same call
        msg = client.beta.messages.create(model=MODEL, betas=["server-side-fallback-2026-07-01"],
                                          fallbacks="default", **body)
    except anthropic.AuthenticationError:
        raise RuntimeError("Claude rejected the credentials. Check AI Configuration in Setup.")
    except anthropic.RateLimitError:
        raise RuntimeError("Claude rate limit reached. Wait a minute and ask again.")
    except anthropic.APIStatusError as e:
        raise RuntimeError(f"Claude API error {e.status_code}: {e.message}")
    except anthropic.APIConnectionError:
        raise RuntimeError("Couldn't reach the Claude API. Check the network.")
    return msg.to_dict()


def chat(cfg, history, page_context, providers):
    """Run the tool loop; yields UI events: {'type': 'status'|'text'|'error'|'done', 'text': ...}."""
    call = _call_gateway if cfg["mode"] == "bedrock_gateway" else _call_sdk
    messages = [{"role": m["role"], "content": m["content"]} for m in history
                if m.get("role") in ("user", "assistant") and m.get("content")]
    system = system_prompt(page_context, providers["summary"]())
    for _ in range(MAX_TOOL_ROUNDS + 1):
        body = {"max_tokens": MAX_TOKENS, "system": system, "messages": messages, "tools": TOOLS,
                "output_config": {"effort": EFFORT}}
        try:
            resp = call(cfg, body)
        except RuntimeError as e:
            yield {"type": "error", "text": str(e)}
            return
        content = resp.get("content", [])
        stop = resp.get("stop_reason")
        if stop == "refusal":
            yield {"type": "error", "text": "Claude declined to answer that. Try rephrasing the question."}
            return
        if stop == "max_tokens":
            yield {"type": "error", "text": "The answer ran too long and was cut off. Ask a narrower question."}
            return
        uses = [b for b in content if b.get("type") == "tool_use"]
        if stop != "tool_use" or not uses:
            text = "".join(b.get("text", "") for b in content if b.get("type") == "text").strip()
            yield {"type": "text", "text": text or "(no answer)"}
            yield {"type": "done"}
            return
        messages.append({"role": "assistant", "content": content})   # unchanged, including thinking blocks
        results = []
        for u in uses:
            args = u.get("input") if isinstance(u.get("input"), dict) else {}
            yield {"type": "status", "text": STATUS.get(u["name"], lambda a: "Working…")(args)}
            results.append({"type": "tool_result", "tool_use_id": u["id"], "content": run_tool(u["name"], args, providers)})
        messages.append({"role": "user", "content": results})   # all results in one message
    yield {"type": "error", "text": "That took more lookups than allowed. Ask a narrower question."}
