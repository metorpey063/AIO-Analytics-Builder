"""claude_model: per-task defaults, a global override, and the gateway ID mapping.

No org or network needed: python3 -m unittest tests.test_claude_model -v
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import claude_model  # noqa: E402


class PerTaskDefaults(unittest.TestCase):
    def test_each_task_has_a_default(self):
        for task in ("chat", "story", "revintel"):
            self.assertEqual(claude_model.pick(task, {}), claude_model.DEFAULTS[task])

    def test_defaults_differ_by_task(self):
        # story uses a cheaper model than chat and revintel by design
        self.assertNotEqual(claude_model.DEFAULTS["story"], claude_model.DEFAULTS["chat"])
        self.assertNotEqual(claude_model.DEFAULTS["story"], claude_model.DEFAULTS["revintel"])

    def test_unknown_task_raises(self):
        with self.assertRaises(KeyError):
            claude_model.pick("not_a_task", {})


class Override(unittest.TestCase):
    def test_override_wins_for_every_task(self):
        full = {"anthropic_model": "claude-opus-5-5"}
        for task in ("chat", "story", "revintel"):
            self.assertEqual(claude_model.pick(task, full), "claude-opus-5-5")

    def test_blank_override_falls_back_to_default(self):
        full = {"anthropic_model": "   "}
        self.assertEqual(claude_model.pick("story", full), claude_model.DEFAULTS["story"])

    def test_missing_key_falls_back_to_default(self):
        self.assertEqual(claude_model.pick("story", {}), claude_model.DEFAULTS["story"])


class GatewayId(unittest.TestCase):
    def test_adds_prefix(self):
        self.assertEqual(claude_model.gateway_id("claude-sonnet-5-5"), "us.anthropic.claude-sonnet-5-5")

    def test_already_prefixed_is_unchanged(self):
        self.assertEqual(claude_model.gateway_id("us.anthropic.claude-sonnet-5-5"), "us.anthropic.claude-sonnet-5-5")


class Current(unittest.TestCase):
    def test_reports_no_override_by_default(self):
        out = claude_model.current({})
        self.assertEqual(out["override"], "")
        self.assertEqual(out["defaults"], claude_model.DEFAULTS)

    def test_reports_saved_override(self):
        out = claude_model.current({"anthropic_model": "claude-opus-5-5"})
        self.assertEqual(out["override"], "claude-opus-5-5")

    def test_choices_include_a_blank_recommended_option(self):
        ids = [c["id"] for c in claude_model.current({})["choices"]]
        self.assertIn("", ids)
        for task_default in claude_model.DEFAULTS.values():
            self.assertIn(task_default, ids)


if __name__ == "__main__":
    unittest.main()
