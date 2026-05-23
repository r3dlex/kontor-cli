"""Natural-language rule file loader for kontor-cli."""
from __future__ import annotations

from pathlib import Path


def load_nl_rules(rules_dir: Path) -> list[str]:
    """Load all natural-language rule files from the rules directory.

    Looks for files matching *.nl.txt or *.rules.txt.
    Returns their combined content as a list of rule strings.
    """
    nl_rules: list[str] = []
    patterns = ["*.nl.txt", "*.rules.txt"]
    for pattern in patterns:
        for rule_file in rules_dir.glob(pattern):
            try:
                content = rule_file.read_text()
                # Split by double newline or rule separators
                rules = [r.strip() for r in content.split("\n---\n") if r.strip()]
                nl_rules.extend(rules)
            except OSError:
                continue
    return nl_rules


def nl_rules_context(nl_rules: list[str]) -> str:
    """Format NL rules for injection into the LLM prompt."""
    if not nl_rules:
        return "(No natural-language rules defined.)"
    return "\n\n".join(f"- {r}" for r in nl_rules)
