"""Data models for pipeline tracking, audit logs, and performance metrics."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field
from dailyai.models.article import DomainType


class DeliveryStatus(str, Enum):
    """Aggregate delivery status for a pipeline run."""

    DELIVERED = "DELIVERED"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    SAVED_ONLY = "SAVED_ONLY"
    PENDING = "PENDING"


class ChannelDeliveryOutcome(BaseModel):
    """Per-channel delivery audit record."""

    channel: str = Field(..., description="Normalized channel identifier (e.g. file_export, email, slack, teams, discord)")
    enabled: bool = Field(default=True, description="Whether this channel was enabled for delivery")
    attempted: bool = Field(default=True, description="Whether a delivery attempt was executed")
    status: Literal["SUCCESS", "FAILED", "SKIPPED"] = Field(
        ...,
        description="Channel-level delivery outcome",
    )
    error: Optional[str] = Field(default=None, description="Sanitized error detail if delivery failed")
    completed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when this channel completed",
    )


class AgentExecutionRecord(BaseModel):
    """Audit record capturing an individual agent's execution performance."""
    agent_name: str = Field(..., description="Name of the agent")
    started_at: datetime = Field(..., description="Execution start timestamp")
    finished_at: datetime = Field(..., description="Execution completion timestamp")
    duration_seconds: float = Field(..., description="Execution duration in seconds")
    items_in: int = Field(default=0, description="Count of input items processed")
    items_out: int = Field(default=0, description="Count of output items produced")
    status: Literal["SUCCESS", "PARTIAL_SUCCESS", "FAILED"] = Field(
        default="SUCCESS",
        description="Outcome of agent run",
    )
    errors: List[str] = Field(default_factory=list, description="Errors or warnings captured")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Diagnostic metadata")


class PipelineRunReport(BaseModel):
    """Comprehensive execution summary for a full pipeline run."""
    run_id: str = Field(..., description="Unique pipeline execution identifier")
    started_at: datetime = Field(..., description="Pipeline start timestamp")
    finished_at: datetime = Field(..., description="Pipeline completion timestamp")
    duration_seconds: float = Field(..., description="Total pipeline runtime in seconds")
    
    drafts_collected: int = Field(default=0, description="Number of drafts produced by Agent 1")
    articles_verified: int = Field(default=0, description="Number of drafts approved by Agent 2")
    articles_rejected: int = Field(default=0, description="Number of drafts rejected by Agent 2")
    articles_published: int = Field(default=0, description="Number of articles included in newsletter")
    
    domain_breakdown: Dict[DomainType, int] = Field(
        default_factory=dict,
        description="Published articles per domain",
    )
    agent_records: List[AgentExecutionRecord] = Field(
        default_factory=list,
        description="Execution trace for each agent",
    )
    delivery_outcomes: List[ChannelDeliveryOutcome] = Field(
        default_factory=list,
        description="Per-channel delivery outcomes across archive, email, and webhooks",
    )
    quarantined_items: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Audit details of articles quarantined or rejected during research/fact-check",
    )
    delivery_status: str = Field(default=DeliveryStatus.PENDING.value, description="Aggregate delivery outcome status")
    run_status: Literal["SUCCESS", "PARTIAL", "FAILED"] = Field(
        default="SUCCESS",
        description="Overall pipeline execution status",
    )
    is_success: bool = Field(default=True, description="Whether overall pipeline succeeded without failure")
    report_persisted: bool = Field(default=True, description="Whether this report was durably persisted")
    errors: List[str] = Field(default_factory=list, description="Any critical or non-fatal error messages")
    newsletter_id: Optional[str] = Field(default=None, description="Generated newsletter ID if created")
