"""Configuration management for DailyAI using Pydantic Settings."""

from pathlib import Path
from typing import List, Literal, Optional, Union
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
    )

    # --------------------------------------------------------------------------
    # 1. LLM Provider Configuration
    # --------------------------------------------------------------------------
    llm_provider: Literal["gemini", "openai", "mock"] = Field(
        default="gemini",
        description="LLM provider backend ('gemini', 'openai', or 'mock')",
    )

    # Google Gemini
    gemini_api_key: Optional[SecretStr] = Field(
        default=None,
        description="Google Gemini API key",
    )
    gemini_model: str = Field(
        default="gemini-2.5-flash",
        description="Gemini model identifier",
    )

    # OpenAI / Compatible
    openai_api_key: Optional[SecretStr] = Field(
        default=None,
        description="OpenAI API Key (or compatible provider)",
    )
    openai_model: str = Field(
        default="gpt-4o-mini",
        description="OpenAI model identifier",
    )
    openai_base_url: Optional[str] = Field(
        default=None,
        description="Custom OpenAI API base URL for compatible gateways",
    )

    # --------------------------------------------------------------------------
    # 2. Intelligence Gathering & Search
    # --------------------------------------------------------------------------
    search_provider: Literal["duckduckgo", "tavily", "serper", "rss_only", "mock"] = Field(
        default="duckduckgo",
        description="Web search engine provider",
    )
    tavily_api_key: Optional[SecretStr] = Field(
        default=None,
        description="Tavily API key",
    )
    serper_api_key: Optional[SecretStr] = Field(
        default=None,
        description="Google Serper API key",
    )

    search_queries_per_category: int = Field(
        default=4,
        ge=1,
        le=20,
        description="Number of search query patterns executed per domain",
    )
    max_search_results_per_query: int = Field(
        default=5,
        ge=1,
        le=50,
        description="Maximum raw search hits retrieved per query",
    )
    lookback_hours: int = Field(
        default=24,
        ge=1,
        le=8760,
        description="Hours of history to consider for recent news (up to 365 days)",
    )
    enable_rss_feeds: bool = Field(
        default=True,
        description="Whether to ingest authoritative RSS feeds alongside search",
    )

    # --------------------------------------------------------------------------
    # 3. Agent 2: Fact-Checking & Quality Gate
    # --------------------------------------------------------------------------
    fact_check_strict_mode: bool = Field(
        default=True,
        description="Strict mode rejects articles lacking verifiable grounding",
    )
    min_confidence_score: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="Minimum credibility score required to pass verification",
    )
    max_articles_per_category: int = Field(
        default=4,
        ge=1,
        le=50,
        description="Maximum articles published per category in final newsletter",
    )

    # --------------------------------------------------------------------------
    # 4. Email Delivery & SMTP (Agent 3)
    # --------------------------------------------------------------------------
    email_enabled: bool = Field(
        default=False,
        description="Enable actual outbound email dispatch via SMTP",
    )
    smtp_host: str = Field(
        default="smtp.gmail.com",
        description="SMTP server hostname",
    )
    smtp_port: int = Field(
        default=587,
        ge=1,
        le=65535,
        description="SMTP port (e.g. 587 for STARTTLS, 465 for SSL)",
    )
    smtp_use_tls: bool = Field(
        default=True,
        description="Whether to use STARTTLS encryption",
    )
    smtp_use_ssl: bool = Field(
        default=False,
        description="Whether to use direct SSL/TLS wrapper",
    )
    smtp_username: str = Field(
        default="",
        description="SMTP authentication username",
    )
    smtp_password: Optional[SecretStr] = Field(
        default=None,
        description="SMTP authentication password / app password",
    )
    email_from: str = Field(
        default="DailyAI Intelligence <noreply@dailyai.local>",
        description="Sender email address",
    )
    email_recipients: List[str] = Field(
        default_factory=lambda: ["subscriber@example.com"],
        description="List of recipient email addresses",
    )
    email_subject_prefix: str = Field(
        default="[DailyAI Intelligence]",
        description="Subject prefix for newsletters",
    )
    output_dir: Path = Field(
        default=Path("output/newsletters"),
        description="Directory where newsletters and reports are archived",
    )

    # --------------------------------------------------------------------------
    # 5. Persistent Storage & Deduplication
    # --------------------------------------------------------------------------
    database_path: Path = Field(
        default=Path("data/dailyai.sqlite"),
        description="SQLite database path for URL deduplication and run logs",
    )

    # --------------------------------------------------------------------------
    # 6. Scheduling & Runtime Controls
    # --------------------------------------------------------------------------
    schedule_cron: str = Field(
        default="0 8 * * *",
        description="Standard 5-field cron expression for recurring runs",
    )
    schedule_interval_minutes: int = Field(
        default=1440,
        ge=1,
        description="Recurring run interval in minutes if cron is not used",
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level",
    )
    dry_run: bool = Field(
        default=False,
        description="Dry-run mode skips sending email and permanent persistence",
    )

    @field_validator("email_recipients", mode="before")
    @classmethod
    def parse_email_recipients(cls, v: Union[str, List[str]]) -> List[str]:
        """Allow comma-separated strings or python lists for email recipients."""
        if isinstance(v, str):
            parts = [addr.strip() for addr in v.split(",") if addr.strip()]
            return parts if parts else ["subscriber@example.com"]
        if isinstance(v, list):
            return [str(item).strip() for item in v if str(item).strip()]
        return ["subscriber@example.com"]

    @field_validator("database_path", "output_dir", mode="before")
    @classmethod
    def parse_path(cls, v: Union[str, Path]) -> Path:
        """Convert string paths to Path objects."""
        return Path(v)


_global_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Retrieve global cached settings instance."""
    global _global_settings
    if _global_settings is None:
        _global_settings = Settings()
    return _global_settings


def reset_settings(new_settings: Optional[Settings] = None) -> None:
    """Reset global settings (useful for tests)."""
    global _global_settings
    _global_settings = new_settings
