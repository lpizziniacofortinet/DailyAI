"""Unit tests for configuration management."""

from pathlib import Path
import pytest
from pydantic import SecretStr

from dailyai.config import Settings, get_settings, reset_settings


def test_default_settings():
    """Verify default setting values and types."""
    settings = Settings()
    assert settings.llm_provider in ["gemini", "openai", "mock"]
    assert settings.lookback_hours >= 1
    assert settings.min_confidence_score == 0.75
    assert isinstance(settings.output_dir, Path)
    assert isinstance(settings.database_path, Path)


def test_recipients_parsing_from_string():
    """Verify email recipients validator parses comma-separated strings."""
    settings = Settings(email_recipients="alice@example.com, bob@example.com ,charlie@example.com")
    assert len(settings.email_recipients) == 3
    assert "alice@example.com" in settings.email_recipients
    assert "bob@example.com" in settings.email_recipients
    assert "charlie@example.com" in settings.email_recipients


def test_recipients_parsing_from_list():
    """Verify email recipients validator accepts list."""
    settings = Settings(email_recipients=["dev@dailyai.local", "ops@dailyai.local"])
    assert settings.email_recipients == ["dev@dailyai.local", "ops@dailyai.local"]


def test_secret_string_masking():
    """Verify API keys and passwords are masked by SecretStr."""
    settings = Settings(
        gemini_api_key=SecretStr("super-secret-key-12345"),
        smtp_password=SecretStr("smtp-secret-pass"),
    )
    assert "super-secret-key-12345" not in repr(settings.gemini_api_key)
    assert settings.gemini_api_key.get_secret_value() == "super-secret-key-12345"
    assert settings.smtp_password.get_secret_value() == "smtp-secret-pass"


def test_get_and_reset_settings():
    """Verify singleton get_settings and reset_settings."""
    custom = Settings(llm_provider="mock", lookback_hours=48)
    reset_settings(custom)
    retrieved = get_settings()
    assert retrieved.lookback_hours == 48
    assert retrieved.llm_provider == "mock"
