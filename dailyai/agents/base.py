"""Base agent abstraction and execution context."""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
import time
from typing import Any, Dict, Generic, List, Optional, TypeVar
from pydantic import BaseModel, Field

from dailyai.logging_config import get_logger
from dailyai.models.pipeline import AgentExecutionRecord

logger = get_logger("agents.base")

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")


class AgentResult(BaseModel, Generic[OutputT]):
    """Standardized result wrapper returned by all pipeline agents."""
    success: bool = Field(..., description="Whether execution succeeded without fatal error")
    output: Optional[OutputT] = Field(default=None, description="Produced data payload")
    record: AgentExecutionRecord = Field(..., description="Execution performance metrics")
    errors: List[str] = Field(default_factory=list, description="Non-fatal errors or warnings")


class BaseAgent(ABC, Generic[InputT, OutputT]):
    """Abstract base class for all specialized pipeline agents."""

    def __init__(self, name: str):
        self.name = name
        self.logger = get_logger(f"agents.{name.lower().replace(' ', '_')}")

    @abstractmethod
    def _run(self, input_data: InputT) -> OutputT:
        """Internal execution logic implemented by child agents."""
        pass

    def execute(self, input_data: InputT) -> AgentResult[OutputT]:
        """Execute agent with lifecycle logging, exception handling, and metrics tracking."""
        self.logger.info(f"==> Starting execution of Agent: '{self.name}'")
        started_at = datetime.now(timezone.utc)
        start_mono = time.monotonic()
        errors: List[str] = []
        output: Optional[OutputT] = None
        status = "SUCCESS"
        items_in = len(input_data) if isinstance(input_data, (list, tuple, dict)) else 1
        items_out = 0

        try:
            output = self._run(input_data)
            if isinstance(output, (list, tuple, dict)):
                items_out = len(output)
            elif output is not None:
                items_out = 1
            self.logger.info(f"<== Finished execution of Agent: '{self.name}' (output items: {items_out})")
        except Exception as e:
            self.logger.error(f"Fatal error during agent '{self.name}' execution: {e}", exc_info=True)
            errors.append(str(e))
            status = "FAILED"
            output = None

        finished_at = datetime.now(timezone.utc)
        duration = round(time.monotonic() - start_mono, 3)

        record = AgentExecutionRecord(
            agent_name=self.name,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=duration,
            items_in=items_in,
            items_out=items_out,
            status=status,
            errors=errors,
        )

        return AgentResult(
            success=(status == "SUCCESS"),
            output=output,
            record=record,
            errors=errors,
        )
