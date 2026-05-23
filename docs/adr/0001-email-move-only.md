# ADR-0001: Email Move-Only Policy

**Status:** Accepted  
**Date:** 2026-05-23

## Context

kontor-cli operates on a production email mailbox. Any email deletion is irreversible and poses a risk of data loss.

## Decision

Emails must **never be deleted**. All email management operations must move emails to appropriate folders (including Archive) rather than removing them.

## Consequences

- `delete_email()` raises `DeleteNotSupportedError` unconditionally
- Archive enforcement moves emails to Archive mirror paths, never removes them
- This is enforced by `.rules.ts` archgate rule `no-delete-emails`
