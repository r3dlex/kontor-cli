"""Sample Python rules for testing."""

from kontor_cli.himalaya import Email


def classify(email: Email) -> str | None:
    """Route CI/CD emails to 9_System."""
    if "pipeline" in email.subject.lower() or "ci" in email.from_addr.lower():
        return "9_System"
    if "budget" in email.subject.lower():
        return "1_Management/MGT_Finance"
    return None
