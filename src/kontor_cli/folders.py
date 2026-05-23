"""Folder taxonomy model and archive enforcement for kontor-cli."""
from __future__ import annotations

from datetime import datetime

from dateutil.relativedelta import relativedelta


class FolderInvariantError(ValueError):
    """Raised when a folder name violates the taxonomy."""


# Valid root-level folder prefixes
VALID_ROOT_PREFIXES = (
    "0_Action",
    "1_Management",
    "2_Projects",
    "3_External",
    "4_Info",
    "9_System",
    "Archive",
    "Drafts",
    "Sent",
    "Trash",
)

# Valid sub-prefixes by parent
VALID_SUB_PREFIXES: dict[str, tuple[str, ...]] = {
    "1_Management": ("MGT_",),
    "2_Projects": ("PRJ_",),
    "3_External": ("EXT_",),
    "Archive": (
        "0_Action",
        "1_Management",
        "2_Projects",
        "3_External",
        "4_Info",
        "9_System",
    ),
}

ARCHIVE_ROOT = "Archive"


def is_valid_folder(folder_name: str) -> bool:
    """Return True if folder_name conforms to the taxonomy rules."""
    if not folder_name or folder_name.startswith("."):
        return False
    if "/" in folder_name:
        parts = folder_name.split("/", 1)
        parent, child = parts[0], parts[1]
    else:
        parent, child = folder_name, ""

    # Root folder must have valid prefix
    root_valid: bool = any(parent.startswith(p) for p in VALID_ROOT_PREFIXES)
    if not root_valid:
        return False

    # Check sub-folder prefixes
    if child:
        valid_subs = VALID_SUB_PREFIXES.get(parent, ())
        child_valid: bool = any(child.startswith(s) for s in valid_subs)
        if not child_valid:
            return False
    return True


def validate_folder(folder_name: str) -> None:
    """Raise FolderInvariantError if folder_name violates taxonomy."""
    if not is_valid_folder(folder_name):
        raise FolderInvariantError(
            f"Invalid folder name: {folder_name!r}. "
            f"Must follow taxonomy: 0_Action, 1_Management/MGT_*, "
            f"2_Projects/PRJ_*, 3_External/EXT_*, 4_Info, 9_System, Archive/*"
        )


def get_archive_path(folder: str) -> str:
    """Return the Archive mirror path for a given folder."""
    if folder.startswith(ARCHIVE_ROOT + "/"):
        return folder  # already in archive
    return f"{ARCHIVE_ROOT}/{folder}"


def is_older_than_6months(date: datetime) -> bool:
    """Return True if date is strictly older than 6 months from now."""
    threshold = datetime.now(date.tzinfo) - relativedelta(months=6)
    return date < threshold  # type: ignore[no-any-return]


def get_target_for_email(
    email_date: datetime,
    classified_folder: str | None,
    archive_age_months: int = 6,
) -> str:
    """Determine the target folder for an email.

    If the email is older than archive_age_months and is not already
    in the Archive tree, redirect to the Archive mirror path.
    Otherwise return the classified folder (or 4_Info if None).
    """
    if classified_folder is None:
        return "4_Info"

    # Check if already in Archive tree
    if classified_folder.startswith(ARCHIVE_ROOT + "/") or classified_folder == ARCHIVE_ROOT:
        return classified_folder

    # Apply archive enforcement
    threshold = datetime.now(email_date.tzinfo) - relativedelta(months=archive_age_months)
    if email_date < threshold:
        return get_archive_path(classified_folder)

    return classified_folder
