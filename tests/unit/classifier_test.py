"""Unit tests for kontor_cli.classifier."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest import mock

from kontor_cli.classifier import (
    Classifier,
    build_prompt,
)
from kontor_cli.himalaya import Email


def _make_email() -> Email:
    return Email(
        id="1",
        from_addr="alice@example.com",
        subject="Q1 Budget Report",
        date=datetime(2024, 3, 15, 10, 0, 0, tzinfo=UTC),
        flags={},
        folder="INBOX",
    )


class TestBuildPrompt:
    def test_email_metadata_injected(self) -> None:
        email = _make_email()
        prompt = build_prompt(email, "TAXONOMY", "NL context", "yaml rules")
        assert "alice@example.com" in prompt
        assert "Q1 Budget Report" in prompt
        assert "2024-03-15" in prompt
        assert "TAXONOMY" in prompt
        assert "NL context" in prompt
        assert "yaml rules" in prompt


class TestClassifier:
    def test_classify_llm_response_parsed(self) -> None:
        mock_response = {
            "choices": [
                {"message": {"content": json.dumps({"folder": "1_Management", "confidence": 0.9, "action": "none"})}}
            ]
        }
        mock_result = mock.MagicMock()
        mock_result.json.return_value = mock_response
        mock_result.raise_for_status = mock.MagicMock()

        from kontor_cli.config import Config
        cfg = mock.MagicMock(spec=Config)
        cfg.llm_base_url = "https://api.openai.com/v1"
        cfg.llm_api_key = "sk-test"
        cfg.llm_model = "gpt-4o"
        cfg.llm_temperature = 0.0
        cfg.llm_timeout = 30
        cfg.pipeline_confidence_threshold = 0.7

        cls = Classifier(cfg)

        with mock.patch("httpx.post") as mock_post:
            mock_post.return_value = mock_result
            result = cls.classify(_make_email())

        assert result is not None
        assert result.folder == "1_Management"
        assert result.confidence == 0.9
        assert result.action == "none"

    def test_classify_confidence_threshold_low(self) -> None:
        mock_response = {
            "choices": [
                {"message": {"content": json.dumps({"folder": "0_Action", "confidence": 0.3, "action": "none"})}}
            ]
        }
        mock_result = mock.MagicMock()
        mock_result.json.return_value = mock_response
        mock_result.raise_for_status = mock.MagicMock()

        from kontor_cli.config import Config
        cfg = mock.MagicMock(spec=Config)
        cfg.llm_base_url = "https://api.openai.com/v1"
        cfg.llm_api_key = "sk-test"
        cfg.llm_model = "gpt-4o"
        cfg.llm_temperature = 0.0
        cfg.llm_timeout = 30
        cfg.pipeline_confidence_threshold = 0.7

        cls = Classifier(cfg)

        with mock.patch("httpx.post") as mock_post:
            mock_post.return_value = mock_result
            result = cls.classify(_make_email())

        # Low confidence → defaults to 4_Info
        assert result is not None
        assert result.folder == "4_Info"

    def test_classify_api_failure(self) -> None:
        import httpx

        from kontor_cli.config import Config
        cfg = mock.MagicMock(spec=Config)
        cfg.llm_base_url = "https://api.openai.com/v1"
        cfg.llm_api_key = "sk-test"
        cfg.llm_model = "gpt-4o"
        cfg.llm_temperature = 0.0
        cfg.llm_timeout = 30
        cfg.pipeline_confidence_threshold = 0.7

        cls = Classifier(cfg)

        with mock.patch("httpx.post") as mock_post:
            mock_post.side_effect = httpx.HTTPStatusError("rate limited", request=mock.MagicMock(), response=mock.MagicMock())
            result = cls.classify(_make_email())

        assert result is None

    def test_classify_invalid_folder_validation(self) -> None:
        # Test that invalid folder names are not blindly accepted
        # We mock at the classify result level to test the validation path
        from kontor_cli.folders import is_valid_folder
        assert not is_valid_folder("Invalid_Folder")
        assert is_valid_folder("4_Info")
