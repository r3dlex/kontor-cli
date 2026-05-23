# ADR-0002: himalaya CLI as the sole email interface

**Status:** Accepted  
**Date:** 2026-05-23

## Context

RIB Software uses Microsoft EWS. A bridge is needed to access email from CLI tooling.

## Decision

Use **himalaya CLI** as the interface to email, backed by **DavMail** as the EWS-to-IMAP bridge running locally. No direct EWS SDK calls.

## Consequences

- Requires DavMail process running on localhost ports (1110 IMAP, 1025 SMTP)
- Requires himalaya to be installed and in PATH
- Configuration includes version pinning for himalaya to protect against output format changes
- Native EWS SDK (exchangelib) is out of scope
