"""LLM-based email classifier for kontor-cli."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from kontor_cli.config import Config
    from kontor_cli.himalaya import Email


logger = logging.getLogger("kontor_cli.classifier")


@dataclass
class ClassificationResult:
    """Result from LLM classification."""
    folder: str
    confidence: float
    action: str  # "adjust" | "create" | "none"


FOLDER_TAXONOMY = """
## Email Folder Taxonomy

Emails MUST be placed in exactly one of these folders:

- **0_Action** — Requires immediate action from you. Not a storage folder.
- **1_Management/MGT_<Topic>** — Management topics: reporting, HR, legal, compliance, meetings, 1:1s.
- **2_Projects/PRJ_<Domain>_<Initiative>_<Scope>** — Project work: specs, status updates, reviews, kickoffs.
- **3_External/EXT_<Company>_<Topic>** — External parties: vendors, partners, clients.
- **4_Info** — Informational only. Newsletters, announcements, system notifications.
- **9_System** — System emails: password resets, security alerts, CI/CD pipelines, infra.
- **Archive/<same path>** — Emails older than 6 months, or already-processed emails from any folder.

Folder naming rules:
- Sub-folders use "/" (e.g., "2_Projects/PRJ_Finance_ERP_Global")
- Archive mirrors the exact structure (e.g., Archive/2_Projects/PRJ_Finance_ERP_Global)
- Never create folders outside this taxonomy.
"""


SYSTEM_PROMPT = """You are an email classifier for kontor-cli. Your job is to classify emails into the correct folder based on the folder taxonomy.

For each email, you MUST respond with ONLY valid JSON:
{
  "folder": "<folder_name>",
  "confidence": <0.0 to 1.0>,
  "action": "adjust" | "create" | "none",
  "reasoning": "<brief explanation>"
}

- folder: Must match the taxonomy exactly. Default to "4_Info" if uncertain.
- confidence: 1.0 = certain, 0.5 = uncertain. Below 0.7 should default to "4_Info".
- action: "adjust" = modify an existing rule, "create" = write a new rule, "none" = one-off decision.
- reasoning: One sentence explaining why this folder was chosen.
"""


def build_prompt(email: Email, taxonomy: str, rules_context: str, yaml_rules: str = "") -> str:
    """Build the classification prompt for the LLM."""
    return f"""{SYSTEM_PROMPT}

{taxonomy}

## Current Rules (YAML DSL)
{yaml_rules if yaml_rules else "(No YAML DSL rules defined yet.)"}

## Natural-Language Rules
{rules_context}

## Email to Classify
- **From:** {email.from_addr}
- **Subject:** {email.subject}
- **Date:** {email.date.isoformat()}
"""


class ClassifierError(Exception):
    """Raised when classification fails."""


class Classifier:
    """OpenAI-compatible LLM classifier."""

    def __init__(self, config: Config) -> None:
        self.base_url = config.llm_base_url
        self.api_key = config.llm_api_key
        self.model = config.llm_model
        self.temperature = config.llm_temperature
        self.timeout = config.llm_timeout
        self.confidence_threshold = config.pipeline_confidence_threshold

    def classify(
        self,
        email: Email,
        rules_context: str = "",
        yaml_rules: str = "",
    ) -> ClassificationResult | None:
        """Classify a single email using the LLM. Returns None on failure."""
        prompt = build_prompt(email, FOLDER_TAXONOMY, rules_context, yaml_rules)

        try:
            response = httpx.post(
                f"{self.base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": self.temperature,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error(f"LLM API returned {exc.response.status_code}: {exc.response.text[:200]}")
            return None
        except httpx.RequestError as exc:
            logger.error(f"LLM API request failed: {exc}")
            return None

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            # Strip markdown code fences if present
            if content.strip().startswith("```"):
                content = content.strip()[content.strip().find("\n") + 1:]
                if content.endswith("```"):
                    content = content[:-3].strip()
            result: dict[str, Any] = {}
            import json
            result = json.loads(content)
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            logger.error(f"Failed to parse LLM response: {exc} — content: {content[:200]}")
            return None

        folder = result.get("folder", "4_Info")
        confidence = float(result.get("confidence", 0.0))
        action = result.get("action", "none")

        # Low confidence → default to 4_Info
        if confidence < self.confidence_threshold:
            logger.warning(
                f"Low confidence ({confidence:.2f}), defaulting to 4_Info",
                extra={"email_id": email.id, "llm_folder": folder},
            )
            folder = "4_Info"

        logger.info(
            "LLM classified email",
            extra={
                "email_id": email.id,
                "folder": folder,
                "confidence": confidence,
                "llm_action": action,
            },
        )
        return ClassificationResult(folder=folder, confidence=confidence, action=action)
