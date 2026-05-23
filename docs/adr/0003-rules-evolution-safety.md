# ADR-0003: LLM Rule Evolution Safety

**Status:** Accepted  
**Date:** 2026-05-23

## Context

The LLM may autonomously adjust or create rules when no explicit rule matches an email. Without safety rails, accumulated LLM rule drift can corrupt the ruleset silently.

## Decision

1. All LLM rule decisions are logged to `rules/evolved/<timestamp>_rule_adjustments.json`
2. `--rules-freeze` snapshots the evolved rules state before a heal run
3. `--dry-run` provides per-email rule-firing traceability before any changes
4. The evolved directory is gitignored

## Consequences

- Rules evolve autonomously without user prompting
- All changes are versioned and human-reviewable in JSON
- Freeze/snapshot enables rollback to a known-good rules state
