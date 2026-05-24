"""Vault integration module for kontor-cli.

Extracts important emails and creates/updates structured notes in the
ObsidianVault. Supports deadlines, C-Level requests, follow-ups,
customer exchanges, escalations, and employee information.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger("kontor_cli.vault_integration")


@dataclass
class VaultNote:
    """A structured note to be written to the ObsidianVault."""

    title: str
    note_type: str  # meeting, escalation, decision, deadline, follow-up, info
    tags: list[str] = field(default_factory=list)
    content: str = ""
    source_email_id: str = ""
    source_email_subject: str = ""
    source_email_from: str = ""
    source_email_date: str = ""
    deadline: str = ""
    action_items: list[str] = field(default_factory=list)
    related_customer: str = ""
    related_project: str = ""


# Patterns for detecting important content
# Key senders whose emails should ALWAYS trigger vault note creation
KEY_SENDERS = [
    "arthur.berganski@rib-software.com",
    "julien.seroi@rib-software.com",
    "rolf.helmes@rib-software.com",
    "martin.murth@rib-software.com",
    "martin.biesinger@rib-software.com",
    "georg.reitschmidt@rib-software.com",
    "joe.deklerk@rib-software.com",
    "gabriel.cerrada@rib-software.com",
    "cordula.trillhaas@rib-software.com",
    "adam.lipinski@rib-software.com",
    "ak.dash@rib-software.com",
    "jon.sigbjornsson@rib-software.com",
    "jakob.pichlmayr@rib-software.com",
    "jeff.ruan@rib-software.com",
    "gautam.makker@rib-software.com",
    "beate.kasper@rib-software.com",
    "reinhardt.fraunhoffer@rib-software.com",
    "christopher.leineweber@rib-software.com",
]

# Known customers for extraction
KNOWN_CUSTOMERS = [
    "Willemen",
    "Eiffage",
    "Vinci",
    "Ratisbona",
    "Budimex",
    "FischerWeilheim",
    "Zeppelin",
    "Augment",
]


def _extract_deadline(subject: str, body: str) -> str:
    """Extract deadline date from subject or body text."""
    combined = f"{subject}\n{body}"
    patterns = [
        r"(?i)bis\s+(\d{1,2})\.(\d{1,2})\.(\d{4})",
        r"(?i)due by (\d{1,2})/(\d{1,2})/(\d{4})",
        r"(?i)deadline:\s*(\d{4})-(\d{1,2})-(\d{1,2})",
        r"(?i)frist\s+(\d{1,2})\.(\d{1,2})\.(\d{4})",
        r"(?i)bis\s+(\d{1,2})\.\s*([A-Za-z]+)\s*(\d{4})",
    ]
    for pattern in patterns:
        match = re.search(pattern, combined)
        if match:
            groups = match.groups()
            if len(groups) == 3 and groups[0].isdigit() and groups[1].isdigit():
                return f"{groups[2]}-{int(groups[1]):02d}-{int(groups[0]):02d}"
            elif len(groups) == 3 and not groups[1].isdigit():
                months = {
                    "january": 1,
                    "february": 2,
                    "march": 3,
                    "april": 4,
                    "may": 5,
                    "june": 6,
                    "july": 7,
                    "august": 8,
                    "september": 9,
                    "october": 10,
                    "november": 11,
                    "december": 12,
                    "januar": 1,
                    "februar": 2,
                    "marz": 3,
                    "mai": 5,
                    "juni": 6,
                    "juli": 7,
                    "oktober": 10,
                    "dezember": 12,
                }
                month_num = months.get(groups[1].lower(), 0)
                if month_num:
                    return f"{groups[2]}-{month_num:02d}-{int(groups[0]):02d}"
    return ""


IMPORTANCE_PATTERNS = {
    "deadline": [
        r"(?i)deadline",
        r"(?i)due\s+by",
        r"(?i)eod\s+(today|tomorrow)",
        r"(?i)by\s+(end\s+of\s+day|end\s+of\s+week)",
        r"(?i)urgent",
        r"(?i)asap",
        r"(?i)time\s+(sensitive|critical)",
        r"(?i)action\s+required",
        r"(?i)response\s+needed",
        r"(?i)bis\s+[0-9]+\.[0-9]+",  # German: bis date
        r"(?i)frist",  # German: deadline
    ],
    "c_level": [
        r"(?i)vorstand",
        r"(?i)gesch[iä]ftsf[iü]hrung",
        r"(?i)ceo",
        r"(?i)cto",
        r"(?i)cio",
        r"(?i)exec(?:utive)?",
        r"(?i)board",
        r"(?i)management\s+(board|team)",
        r"(?i)head of",
        r"(?i)vp\s+of",
        r"(?i)director",
    ],
    "customer_escalation": [
        r"(?i)escalat",
        r"(?i)complaint",
        r"(?i)beschwerde",
        r"(?i)problem",
        r"(?i)issue\s+(with|regarding)",
        r"(?i)critical\s+(issue|bug)",
        r"(?i)production\s+(issue|outage|down)",
        r"(?i)hypercare",
        r"(?i)customers?\s+(dissatisfied|unhappy)",
    ],
    "follow_up": [
        r"(?i)follow.?up",
        r"(?i)nachfass",
        r"(?i)warte\s+auf",
        r"(?i)waiting\s+(for|on)",
        r"(?i)status\s+(update|check)",
        r"(?i)update\s+(on|regarding)",
        r"(?i)next\s+steps?",
    ],
    "decision": [
        r"(?i)decision",
        r"(?i)entscheidung",
        r"(?i)approved",
        r"(?i)genehmigt",
        r"(?i)agreed",
        r"(?i)vereinbart",
        r"(?i)confirmed",
        r"(?i)beschlossen",
    ],
    "employee_info": [
        r"(?i)onboarding",
        r"(?i)offboarding",
        r"(?i)new\s+(hire|joiner|starter)",
        r"(?i)resignation",
        r"(?i)k[iü]ndigung",
        r"(?i)termination",
        r"(?i)vacation",
        r"(?i)urlaub",
        r"(?i)sick\s+(leave|note)",
        r"(?i)krankmeldung",
        r"(?i)parental\s+leave",
        r"(?i)elternzeit",
    ],
}

# Folder categories that map to vault content paths
FOLDER_TO_VAULT_PATH = {
    "1_Management/MGT": "RIB/2026/Meetings",
    "1_Management/MGT_1on1": "RIB/Meetings/1on1",
    "1_Management/MGT_Recruiting": "RIB/Hiring",
    "1_Management/MGT_Compensation": "RIB/Operations/Compensation",
    "1_Management/MGT_Travel": "RIB/Operations/Travel",
    "2_Projects/PRJ_RIB4_Customer": "RIB/2026/Customer",
    "2_Projects/PRJ_RIB4_Release": "RIB/2026/Release",
    "2_Projects/PRJ_RIB4_Infrastructure": "RIB/Operations",
    "3_External/EXT_": "RIB/2026/Vendors",
    "4_Info": "RIB/2026/Daily Digests",
}

# Base path for the ObsidianVault
VAULT_BASE = Path("/Users/andreburgstahler/Ws/Rib/ObisidanVault")


def extract_important_email(email_id: str, folder: str) -> VaultNote | None:
    """Extract an email from himalaya and determine if it's vault-worthy."""
    try:
        result = subprocess.run(
            [
                "himalaya",
                "--config",
                str(
                    Path(
                        "/Users/andreburgstahler/Library/Application Support/himalaya/config.toml"
                    )
                ),
                "message",
                "get",
                email_id,
                "-f",
                folder,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        content = result.stdout
        if not content:
            return None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        logger.warning(f"Failed to get email {email_id} content: {exc}")
        return None

    # Parse headers manually (the himalaya output format)
    headers: dict[str, str] = {}
    body_parts: list[str] = []
    in_body = False

    for line in content.split("\n"):
        if not in_body:
            # Try to match "Header: value" pattern
            match = re.match(r"^([\w-]+):\s+(.+)$", line)
            if match:
                headers[match.group(1).lower()] = match.group(2).strip()
                continue
        if line.strip() and not line.startswith("--") and not line.startswith("Date:"):
            in_body = True
            body_parts.append(line)

    # Still in headers area if we've passed known headers but haven't switched
    # himalaya often puts a blank line then body
    found_blank = False
    actual_body: list[str] = []
    for line in content.split("\n"):
        if not line.strip():
            found_blank = True
            continue
        if found_blank and not line.startswith("Date:") and not line.startswith("--"):
            actual_body.append(line)

    body_text = "\n".join(actual_body)
    subject = headers.get("subject", "")
    from_addr_raw = headers.get("from", "")
    sender_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", from_addr_raw)
    sender = sender_match.group(0) if sender_match else from_addr_raw
    date_str = headers.get("date", "")

    # Determine vault-worthiness
    importance = _assess_importance(subject, body_text, sender=sender)
    if not importance["is_important"]:
        return None

    # Extract deadline from content
    deadline_text = _extract_deadline(subject, body_text)
    if deadline_text and not importance.get("deadline"):
        importance["deadline"] = deadline_text

    # Build the vault note
    note = VaultNote(
        title=_build_title(subject, date_str),
        note_type=importance["primary_type"],
        tags=importance["tags"],
        content=body_text[:2000],  # Truncate long bodies
        source_email_id=email_id,
        source_email_subject=subject,
        source_email_from=sender,
        source_email_date=date_str,
        deadline=importance.get("deadline", deadline_text),
        action_items=importance.get("action_items", []),
        related_customer=_extract_customer(subject, body_text),
        related_project=_extract_project(subject, body_text, folder),
    )
    return note


def _assess_importance(subject: str, body: str, sender: str = "") -> dict[str, Any]:
    """Scan subject + body for importance indicators."""
    combined = f"{subject}\n{body}"
    found_categories: dict[str, list[str]] = {}
    is_important = False

    # Key sender check
    if sender:
        sender_lower = sender.lower()
        for ks in KEY_SENDERS:
            if ks in sender_lower:
                is_important = True
                found_categories.setdefault("key_sender", []).append(ks)
                break

    for category, patterns in IMPORTANCE_PATTERNS.items():
        matches = []
        for pattern in patterns:
            m = re.search(pattern, combined)
            if m:
                matches.append(m.group())
        if matches:
            found_categories[category] = matches
            is_important = True

    # Default type if nothing matched
    primary_type = "info"
    if "deadline" in found_categories:
        primary_type = "deadline"
    elif "c_level" in found_categories:
        primary_type = "c_level"
    elif "customer_escalation" in found_categories:
        primary_type = "escalation"
    elif "decision" in found_categories:
        primary_type = "decision"
    elif "follow_up" in found_categories:
        primary_type = "follow-up"
    elif "employee_info" in found_categories:
        primary_type = "employee"

    # Extract deadline text if present
    deadline = ""
    for match in found_categories.get("deadline", []):
        deadline = match
        break

    return {
        "is_important": is_important,
        "primary_type": primary_type,
        "tags": list(found_categories.keys()),
        "deadline": deadline,
        "action_items": found_categories.get("follow_up", []),
    }


def _build_title(subject: str, date_str: str) -> str:
    """Build a clean vault note title from subject + date."""
    # Remove common prefixes
    clean = re.sub(r"^(RE:|Fwd:|AW:|WG:)\s*", "", subject, flags=re.I).strip()
    # Extract date parts
    date_part = date_str[:10] if date_str else ""
    if date_part:
        return f"{date_part} - {clean}"
    return clean


def _extract_customer(subject: str, body: str) -> str:
    """Try to extract customer name from subject/body."""
    patterns = [
        r"(?i)customer[:\s]+([A-Za-z0-9-_]+)",
        r"(?i)kunde[:\s]+([A-Za-z0-9-_]+)",
        r"(?i)(Willemen)",
        r"(?i)(Zeppelin)",
        r"(?i)(Fischer)",
    ]
    combined = f"{subject}\n{body}"
    for pattern in patterns:
        m = re.search(pattern, combined)
        if m:
            return m.group(1)
    return ""


def _extract_project(subject: str, body: str, folder: str) -> str:
    """Extract project from folder path or subject."""
    if folder.startswith("2_Projects/"):
        return folder.split("/", 1)[1]
    patterns = [r"(?i)project[:\s]+([A-Za-z0-9-_]+)"]
    combined = f"{subject}\n{body}"
    for pattern in patterns:
        m = re.search(pattern, combined)
        if m:
            return m.group(1)
    return ""


def get_vault_path(note: VaultNote, folder: str) -> Path:
    """Determine the ObsidianVault path for this note based on folder/category."""
    # Map folder to vault path
    vault_subpath = None
    for prefix, path in FOLDER_TO_VAULT_PATH.items():
        if folder.startswith(prefix):
            vault_subpath = path
            break

    if not vault_subpath:
        vault_subpath = "RIB/raw"

    # Build year/month path
    now = datetime.now(UTC)
    year_month = now.strftime("%Y/%m")
    vault_path = VAULT_BASE / vault_subpath / year_month
    vault_path.mkdir(parents=True, exist_ok=True)

    return vault_path


def write_vault_note(note: VaultNote, folder: str) -> Path | None:
    """Write a vault note for an important email. Returns the file path or None."""
    vault_dir = get_vault_path(note, folder)
    sanitized_title = re.sub(r'[<>:"/\\|?*]', "_", note.title)[:100]
    filepath = vault_dir / f"{sanitized_title}.md"

    # Frontmatter
    frontmatter = {
        "type": f"email-{note.note_type}",
        "last_updated": datetime.now(UTC).strftime("%Y-%m-%d"),
        "tags": sorted(set(note.tags + ["email"] + [note.note_type])),
        "source": {
            "email_id": note.source_email_id,
            "subject": note.source_email_subject,
            "from": note.source_email_from,
            "date": note.source_email_date,
        },
    }
    if note.deadline:
        frontmatter["deadline"] = note.deadline
    if note.action_items:
        frontmatter["action_items"] = note.action_items
    if note.related_customer:
        frontmatter["customer"] = note.related_customer
    if note.related_project:
        frontmatter["project"] = note.related_project

    yaml_front = "---\n"
    for key, value in frontmatter.items():
        if isinstance(value, dict):
            yaml_front += f"{key}:\n"
            for sk, sv in value.items():
                yaml_front += f"  {sk}: {json.dumps(sv)}\n"
        elif isinstance(value, list):
            yaml_front += f"{key}:\n"
            for item in value:
                yaml_front += f"  - {json.dumps(item)}\n"
        else:
            yaml_front += f"{key}: {json.dumps(value)}\n"
    yaml_front += "---\n"

    note_content = f"{yaml_front}\n# {note.title}\n\n"
    note_content += f"**From:** {note.source_email_from}  \n"
    note_content += f"**Date:** {note.source_email_date}  \n"
    note_content += f"**Subject:** {note.source_email_subject}  \n"
    if note.deadline:
        note_content += f"**Deadline:** {note.deadline}  \n"
    if note.action_items:
        note_content += "\n## Action Items\n\n"
        for item in note.action_items:
            note_content += f"- [ ] {item}\n"
    note_content += f"\n## Content\n\n{note.content}\n"

    try:
        filepath.write_text(note_content)
        logger.info(f"Wrote vault note: {filepath}")

        # Create review link for key-sender emails
        if "key_sender" in note.tags:
            raw_dir = VAULT_BASE / "RIB" / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            link_path = raw_dir / f"REVIEW_{sanitized_title}.md"
            link_lines = []
            link_lines.append("---")
            link_lines.append("type: email-review-link")
            link_lines.append(f"last_updated: {datetime.now(UTC).strftime('%Y-%m-%d')}")
            link_lines.append(f"tags: [needs-review, email, {note.note_type}]")
            link_lines.append(f"source: {note.source_email_id}")
            link_lines.append("review: pending")
            link_lines.append("---")
            link_lines.append("")
            link_lines.append(f"# Review: {note.title}")
            link_lines.append("")
            link_lines.append("This email from a key sender needs your review.")
            link_lines.append("")
            link_lines.append(f"**From:** {note.source_email_from}")
            link_lines.append(f"**Subject:** {note.source_email_subject}")
            link_lines.append(f"**Date:** {note.source_email_date}")
            link_lines.append(f"**Classification:** {note.note_type}")
            link_lines.append("")
            rel_path = str(filepath.relative_to(VAULT_BASE)).replace(".md", "")
            link_lines.append(f"See full note: [[{rel_path}]]")
            link_path.write_text("\n".join(link_lines))
            logger.info(f"Created review link: {link_path}")

        return filepath
    except OSError as exc:
        logger.error(f"Failed to write vault note: {exc}")
        return None


def process_for_vault(email_id: str, folder: str, dry_run: bool = False) -> Path | None:
    """Process an email for vault integration. Returns note path or None."""
    note = extract_important_email(email_id, folder)
    if note is None:
        logger.info(f"Email {email_id} not important enough for vault")
        return None

    if dry_run:
        logger.info(
            f"[DRY-RUN] Would write vault note: {note.title} "
            f"(type={note.note_type}, tags={note.tags})"
        )
        return None

    return write_vault_note(note, folder)
