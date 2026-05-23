"""YAML DSL rule evaluator for kontor-cli."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class YamlRule:
    """A single YAML DSL rule."""

    pattern: str | None
    from_addr: str | None
    subject: str | None
    to: str | None
    folder: str
    priority: int = 0

    def matches(self, from_addr: str, subject: str, to: str = "") -> bool:
        """Return True if this rule matches the given email fields."""
        if self.pattern:
            if not re.search(self.pattern, f"{from_addr} {subject}", re.IGNORECASE):
                return False
        if self.from_addr:
            if not re.search(self.from_addr, from_addr, re.IGNORECASE):
                return False
        if self.subject:
            if not re.search(self.subject, subject, re.IGNORECASE):
                return False
        if self.to:
            if not re.search(self.to, to, re.IGNORECASE):
                return False
        return True


def load_rules_from_dir(rules_dir: Path) -> list[YamlRule]:
    """Load all YAML DSL rules from the given directory.

    Looks for:
    1. rules_dir/rules.d/*.yaml  (multiple rule files)
    2. rules_dir/yaml_dsl.yaml (single combined file)
    3. rules_dir/*.yaml         (root-level rule files)
    """
    rules: list[YamlRule] = []

    # Try rules.d/ subdirectory first
    yaml_subdir = rules_dir / "rules.d"
    if yaml_subdir.is_dir():
        for yaml_file in sorted(yaml_subdir.glob("*.yaml")):
            rules.extend(_load_file(yaml_file))

    # Try yaml_dsl.yaml at the root
    combined = rules_dir / "yaml_dsl.yaml"
    if combined.is_file():
        rules.extend(_load_file(combined))

    # Also scan root-level *.yaml files (skip config.yaml and similar)
    skip_names = {"config.yaml", "config.example.yaml", "config.yml"}
    for yaml_file in sorted(rules_dir.glob("*.yaml")):
        if yaml_file.name not in skip_names:
            rules.extend(_load_file(yaml_file))

    return rules


def _load_file(path: Path) -> list[YamlRule]:
    """Load rules from a single YAML file."""
    try:
        with open(path) as fh:
            raw = yaml.safe_load(fh)
    except (yaml.YAMLError, OSError):
        return []

    entries = raw if isinstance(raw, list) else []
    rules: list[YamlRule] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        rules.append(
            YamlRule(
                pattern=entry.get("pattern"),
                from_addr=entry.get("from"),
                subject=entry.get("subject"),
                to=entry.get("to"),
                folder=entry.get("folder", ""),
                priority=entry.get("priority", 0),
            )
        )
    return rules


def evaluate_yaml_rules(
    rules: list[YamlRule],
    from_addr: str,
    subject: str,
    to: str = "",
) -> str | None:
    """Evaluate YAML DSL rules in priority order. Returns folder or None."""
    for rule in sorted(rules, key=lambda r: r.priority, reverse=True):
        if rule.matches(from_addr, subject, to):
            return rule.folder
    return None
