"""
claude_model.py — which Claude model AIO uses for its own calls (Web UI chat, story
generation, revintel drafting), shared with claude_credentials.py (which resolves the
key/auth, not the model).

Each task has a recommended default model, tuned for that task's cost/quality tradeoff
(fast+cheap for story generation, strongest for Rev Intel drafting). A user can save a
global override in config.json ("anthropic_model") to force every task onto one model
instead — pick() returns the override when present, otherwise the task's default.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"

DEFAULTS = {
    "chat": "claude-sonnet-5-5",            # Ask Claude assistant
    "story": "claude-haiku-4-5-20251001",   # story/metric generation (builder.py), credentials Test button
    "revintel": "claude-opus-5-5",          # Rev Intel drafting + research
}

# Shown in the Setup UI's model dropdown, cheapest first.
CHOICES = [
    {"id": "", "label": "Recommended per task (default)"},
    {"id": "claude-haiku-4-5-20251001", "label": "Haiku 4.5 — fastest, cheapest"},
    {"id": "claude-sonnet-5-5", "label": "Sonnet 5.5 — balanced"},
    {"id": "claude-opus-5-5", "label": "Opus 5.5 — most capable"},
]


def _read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def gateway_id(model):
    """The Bedrock gateway's ID for a direct-API model name, e.g. 'claude-opus-5-5' -> 'us.anthropic.claude-opus-5-5'."""
    return model if model.startswith("us.anthropic.") else f"us.anthropic.{model}"


def pick(task, full_config=None):
    """The direct-API model ID to use for a task: the saved override if the user set one, else the task's default."""
    full = full_config if full_config is not None else _read_json(CONFIG_PATH)
    override = (full.get("anthropic_model") or "").strip()
    return override or DEFAULTS[task]


def current(full_config=None):
    """Secret-free description for the UI: the saved override (if any) and the per-task defaults."""
    full = full_config if full_config is not None else _read_json(CONFIG_PATH)
    return {"override": (full.get("anthropic_model") or "").strip(), "defaults": dict(DEFAULTS), "choices": CHOICES}
