"""Unit tests for kontor_cli.rules_engine."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

import yaml

from kontor_cli.himalaya import Email
from kontor_cli.rules import nl_rules, python_rules, yaml_dsl
from kontor_cli.rules_engine import RulesEngine


def _email(from_addr: str = "alice@example.com", subject: str = "Test") -> Email:
    return Email(
        id="1",
        from_addr=from_addr,
        subject=subject,
        date=datetime.now(UTC),
        flags={},
        folder="INBOX",
    )


class TestYamlDsl:
    def test_yaml_dsl_match(self, tmp_path: Path) -> None:
        rules = [
            {"from": "alice@example.com", "folder": "2_Projects/PRJ_Test"},
        ]
        yaml_file = tmp_path / "rules.yaml"
        with open(yaml_file, "w") as fh:
            yaml.safe_dump(rules, fh)
        loaded = yaml_dsl.load_rules_from_dir(tmp_path)
        result = yaml_dsl.evaluate_yaml_rules(loaded, "alice@example.com", "Test")
        assert result == "2_Projects/PRJ_Test"

    def test_yaml_dsl_no_match(self, tmp_path: Path) -> None:
        rules = [
            {"from": "alice@example.com", "folder": "2_Projects/PRJ_Test"},
        ]
        yaml_file = tmp_path / "rules.yaml"
        with open(yaml_file, "w") as fh:
            yaml.safe_dump(rules, fh)
        loaded = yaml_dsl.load_rules_from_dir(tmp_path)
        result = yaml_dsl.evaluate_yaml_rules(loaded, "bob@example.com", "Test")
        assert result is None


class TestPythonRules:
    def test_python_rules_match(self, tmp_path: Path) -> None:
        rules_file = tmp_path / "rules.py"
        rules_file.write_text(
            "def classify(email):\n"
            "    if 'budget' in email.subject.lower():\n"
            "        return '1_Management/MGT_Finance'\n"
        )
        ns = python_rules.load_python_rules(rules_file)
        email = _email(subject="Monthly Budget Report")
        result = python_rules.call_python_rules(ns, email)
        assert result == "1_Management/MGT_Finance"

    def test_python_rules_no_match(self, tmp_path: Path) -> None:
        rules_file = tmp_path / "rules.py"
        rules_file.write_text(
            "def classify(email):\n"
            "    if 'budget' in email.subject.lower():\n"
            "        return '1_Management/MGT_Finance'\n"
        )
        ns = python_rules.load_python_rules(rules_file)
        email = _email(subject="Hello World")
        result = python_rules.call_python_rules(ns, email)
        assert result is None


class TestNlRules:
    def test_nl_rules_format_loaded(self, tmp_path: Path) -> None:
        nl_file = tmp_path / "guidelines.rules.txt"
        nl_file.write_text(
            "All invoices from accounting@ go to Finance.\n---\nPR emails go to 3_External."
        )
        loaded = nl_rules.load_nl_rules(tmp_path)
        assert len(loaded) == 2
        assert "invoices" in loaded[0]

    def test_nl_rules_context(self) -> None:
        ctx = nl_rules.nl_rules_context(["Rule 1", "Rule 2"])
        assert "Rule 1" in ctx
        assert "Rule 2" in ctx
        assert ctx.startswith("- Rule 1")


class TestRulesEngine:
    def test_rules_priority_order(self, tmp_path: Path) -> None:
        """YAML DSL should take priority over Python module."""
        # YAML DSL rule
        yaml_file = tmp_path / "rules.yaml"
        with open(yaml_file, "w") as fh:
            yaml.safe_dump([{"from": "alice@example.com", "folder": "YAML_Folder"}], fh)
        # Python rule (should not fire because YAML matched first)
        rules_file = tmp_path / "rules.py"
        rules_file.write_text("def classify(email):\n    return 'Python_Folder'\n")
        nl_file = tmp_path / "guidelines.rules.txt"
        nl_file.write_text("NL rule")

        cfg = mock.MagicMock()
        cfg.rules_yaml_dir = tmp_path
        cfg.rules_python_file = rules_file
        cfg.rules_nl_dir = tmp_path

        engine = RulesEngine(cfg, cwd=tmp_path)
        result = engine.classify(_email())
        # YAML matched first
        assert result == "YAML_Folder"
