"""Pipeline Orchestrator for DailyAI.

Coordinates the end-to-end execution of Agent 1 (Research), Agent 2 (Verification),
and Agent 3 (Newsletter Delivery), generating auditable run reports, awaiting
multi-channel webhook delivery, and enforcing explicit failure boundaries.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Type
import uuid

from dailyai.agents.base import AgentResult
from dailyai.agents.fact_check_agent import FactCheckAgent
from dailyai.agents.newsletter_agent import NewsletterAgent
from dailyai.agents.research_agent import ResearchAgent
from dailyai.config import Settings, get_settings, settings as delivery_settings
from dailyai.logging_config import get_logger
from dailyai.models.article import DomainType
from dailyai.models.newsletter import Newsletter
from dailyai.models.pipeline import (
    AgentExecutionRecord,
    ChannelDeliveryOutcome,
    DeliveryStatus,
    PipelineRunReport,
)
from dailyai.services.delivery import (
    DeliveryService,
    DiscordDeliveryService,
    SlackDeliveryService,
    TeamsDeliveryService,
)
from dailyai.services.storage.base import BaseDeduplicationStore
from dailyai.services.storage.sqlite import SQLiteDeduplicationStore
from dailyai.temporal import Clock, utc_now

logger = get_logger("pipeline.orchestrator")

_SECRET_PATTERNS = [
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._\-+/=]+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(https://discord\.com/api/webhooks/)[^\s'\"<>]+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"(https://hooks\.slack\.com/services/)[^\s'\"<>]+", re.IGNORECASE), r"\1[REDACTED]"),
    (re.compile(r"\b(api[_-]?key|token|secret|password)\s*([=:])\s*[^\s,'\"<>]+", re.IGNORECASE), r"\1\2[REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{10,}\b"), "[REDACTED]"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{20,}\b"), "[REDACTED]"),
]


def redact_secrets(text: str, settings: Optional[Settings] = None) -> str:
    """Scrub configured secrets and common credential patterns from error/log text."""
    if not text:
        return text

    sanitized = str(text)

    # Redact explicitly configured secret values from Settings
    if settings is not None:
        secret_fields = (
            "gemini_api_key",
            "openai_api_key",
            "tavily_api_key",
            "serper_api_key",
            "smtp_password",
        )
        for field_name in secret_fields:
            secret_val = getattr(settings, field_name, None)
            if secret_val is not None:
                raw = secret_val.get_secret_value() if hasattr(secret_val, "get_secret_value") else str(secret_val)
                if raw and len(raw) >= 4:
                    sanitized = sanitized.replace(raw, "[REDACTED]")

    # Redact configured webhook URLs
    for url_field in ("discord_webhook_url", "slack_webhook_url", "teams_webhook_url"):
        url_val = getattr(delivery_settings, url_field, None)
        if url_val:
            sanitized = sanitized.replace(str(url_val), "[REDACTED_WEBHOOK_URL]")

    # Redact generic credential patterns
    for pattern, replacement in _SECRET_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)

    return sanitized


def _resolve_webhook_channel_name(service: DeliveryService) -> str:
    """Return normalized channel name for a webhook DeliveryService."""
    explicit = getattr(service, "channel_name", None)
    if explicit:
        return explicit
    cls_name = service.__class__.__name__.lower()
    if "slack" in cls_name:
        return "slack"
    if "teams" in cls_name:
        return "teams"
    if "discord" in cls_name:
        return "discord"
    return cls_name


def compute_delivery_status(
    outcomes: List[ChannelDeliveryOutcome],
    newsletter_created: bool,
    had_stage_failure: bool,
) -> str:
    """Derive explicit aggregate delivery status across all channels."""
    if had_stage_failure or not newsletter_created:
        return DeliveryStatus.FAILED.value

    attempted = [o for o in outcomes if o.attempted]
    if not attempted:
        return DeliveryStatus.SAVED_ONLY.value

    succeeded = [o for o in attempted if o.status == "SUCCESS"]
    failed = [o for o in attempted if o.status == "FAILED"]

    if not succeeded and failed:
        return DeliveryStatus.FAILED.value
    if succeeded and failed:
        return DeliveryStatus.PARTIAL.value
    if succeeded and not failed:
        if all(o.channel == "file_export" for o in succeeded):
            return DeliveryStatus.SAVED_ONLY.value
        return DeliveryStatus.DELIVERED.value

    return DeliveryStatus.FAILED.value


class DeliveryFactory:
    @staticmethod
    def get_enabled_services() -> List[DeliveryService]:
        services: List[DeliveryService] = []
        if delivery_settings.enable_discord and delivery_settings.discord_webhook_url:
            services.append(DiscordDeliveryService(str(delivery_settings.discord_webhook_url)))
        if delivery_settings.enable_slack and delivery_settings.slack_webhook_url:
            services.append(SlackDeliveryService(str(delivery_settings.slack_webhook_url)))
        if delivery_settings.enable_teams and delivery_settings.teams_webhook_url:
            services.append(TeamsDeliveryService(str(delivery_settings.teams_webhook_url)))
        return services


async def distribute_results(
    data: Dict[str, Any],
    settings: Optional[Settings] = None,
) -> List[ChannelDeliveryOutcome]:
    """Concurrently distribute payload to all enabled webhook endpoints and return per-channel outcomes.

    Always closes all DeliveryService HTTP clients in a finally block, even if a
    delivery raises an unexpected exception.
    """
    services = DeliveryFactory.get_enabled_services()
    if not services:
        logger.warning("Notification sequence aborted: No delivery services are currently active.")
        return []

    logger.info(f"Initiating concurrent payload distribution to {len(services)} configured endpoints.")

    outcomes: List[ChannelDeliveryOutcome] = []
    try:
        tasks = [service.deliver(data) for service in services]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for service, result in zip(services, results):
            channel = _resolve_webhook_channel_name(service)
            completed_at = datetime.now(timezone.utc)
            if isinstance(result, Exception):
                sanitized_err = redact_secrets(f"{type(result).__name__}: {result}", settings)
                logger.error(
                    f"Subsystem fault detected: Delivery to {service.__class__.__name__} "
                    f"crashed unexpectedly: {sanitized_err}"
                )
                outcomes.append(
                    ChannelDeliveryOutcome(
                        channel=channel,
                        enabled=True,
                        attempted=True,
                        status="FAILED",
                        error=sanitized_err,
                        completed_at=completed_at,
                    )
                )
            elif result is True:
                outcomes.append(
                    ChannelDeliveryOutcome(
                        channel=channel,
                        enabled=True,
                        attempted=True,
                        status="SUCCESS",
                        completed_at=completed_at,
                    )
                )
            else:
                raw_err = getattr(service, "last_error", None) or f"{service.__class__.__name__} delivery returned False"
                sanitized_err = redact_secrets(raw_err, settings)
                outcomes.append(
                    ChannelDeliveryOutcome(
                        channel=channel,
                        enabled=True,
                        attempted=True,
                        status="FAILED",
                        error=sanitized_err,
                        completed_at=completed_at,
                    )
                )
    finally:
        cleanup_tasks = [service.close() for service in services]
        await asyncio.gather(*cleanup_tasks, return_exceptions=True)

    return outcomes


class PipelineOrchestrator:
    """Coordinates and executes the 3-agent intelligence pipeline."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        research_agent: Optional[ResearchAgent] = None,
        fact_check_agent: Optional[FactCheckAgent] = None,
        newsletter_agent: Optional[NewsletterAgent] = None,
        storage: Optional[BaseDeduplicationStore] = None,
        clock: Optional[Clock] = None,
    ):
        self.settings = settings or get_settings()
        self.storage = storage or SQLiteDeduplicationStore(self.settings.database_path)
        self._now: Clock = clock or utc_now

        self.agent1 = research_agent or ResearchAgent(
            settings=self.settings, storage=self.storage, clock=self._now
        )
        self.agent2 = fact_check_agent or FactCheckAgent(
            settings=self.settings, clock=self._now
        )
        self.agent3 = newsletter_agent or NewsletterAgent(
            settings=self.settings, storage=self.storage
        )

    def _execute_stage(
        self,
        stage_name: str,
        agent: Any,
        input_data: Any,
        expected_output_type: Optional[Type[Any]] = None,
    ) -> Tuple[Optional[AgentResult[Any]], AgentExecutionRecord, bool]:
        """Run a pipeline stage inside an explicit failure boundary.

        Returns (agent_result_or_none, execution_record, stage_succeeded).
        """
        agent_name = getattr(agent, "name", stage_name)
        stage_started_at = self._now()
        stage_start_mono = time.monotonic()
        items_in = len(input_data) if isinstance(input_data, (list, tuple, dict)) else (0 if input_data is None else 1)

        try:
            result = agent.execute(input_data)
        except Exception as exc:
            finished_at = self._now()
            duration = round(time.monotonic() - stage_start_mono, 3)
            sanitized_err = redact_secrets(f"{type(exc).__name__}: {exc}", self.settings)
            logger.error(
                "Unexpected exception in stage '%s' (%s): %s",
                stage_name,
                agent_name,
                sanitized_err,
                exc_info=True,
            )
            record = AgentExecutionRecord(
                agent_name=agent_name,
                started_at=stage_started_at,
                finished_at=finished_at,
                duration_seconds=duration,
                items_in=items_in,
                items_out=0,
                status="FAILED",
                errors=[sanitized_err],
                metadata={
                    "stage": stage_name,
                    "exception_type": type(exc).__name__,
                    "failed_at": finished_at.isoformat(),
                },
            )
            return None, record, False

        # Validate returned result contract
        if result is None or not hasattr(result, "record") or not hasattr(result, "success"):
            finished_at = self._now()
            duration = round(time.monotonic() - stage_start_mono, 3)
            err_msg = f"Stage '{stage_name}' returned invalid AgentResult: {type(result).__name__}"
            logger.error(err_msg)
            record = AgentExecutionRecord(
                agent_name=agent_name,
                started_at=stage_started_at,
                finished_at=finished_at,
                duration_seconds=duration,
                items_in=items_in,
                items_out=0,
                status="FAILED",
                errors=[err_msg],
                metadata={"stage": stage_name, "failed_at": finished_at.isoformat()},
            )
            return None, record, False

        # Sanitize any errors recorded by the agent itself
        sanitized_errors = [redact_secrets(e, self.settings) for e in (result.errors or [])]
        result.errors = sanitized_errors
        result.record.errors = [redact_secrets(e, self.settings) for e in (result.record.errors or [])]
        result.record.metadata.setdefault("stage", stage_name)

        if not result.success or result.record.status == "FAILED":
            return result, result.record, False

        if expected_output_type is not None and result.output is not None and not isinstance(result.output, expected_output_type):
            err_msg = (
                f"Stage '{stage_name}' produced unexpected output type "
                f"{type(result.output).__name__} (expected {expected_output_type.__name__})"
            )
            logger.error(err_msg)
            result.record.status = "FAILED"
            result.record.errors.append(err_msg)
            result.errors.append(err_msg)
            return result, result.record, False

        return result, result.record, True

    def _build_webhook_payload(
        self,
        newsletter: Newsletter,
        run_id: str,
        duration_seconds: float,
        domain_breakdown: Dict[DomainType, int],
    ) -> Dict[str, Any]:
        return {
            "title": newsletter.title,
            "content": (
                f"DailyAI Pipeline executed successfully. "
                f"{newsletter.total_articles} articles verified and published."
            ),
            "metadata": {
                "Run ID": run_id,
                "Duration": f"{duration_seconds}s",
                "AI Articles": domain_breakdown[DomainType.AI],
                "Cyber Articles": domain_breakdown[DomainType.CYBERSECURITY],
                "V2X Articles": domain_breakdown[DomainType.V2X],
            },
        }

    def _run_webhooks_sync(self, data: Dict[str, Any]) -> List[ChannelDeliveryOutcome]:
        """Run async webhook distribution to completion, whether or not an event loop is active."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(distribute_results(data, settings=self.settings))

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(asyncio.run, distribute_results(data, settings=self.settings))
            return future.result()

    def _finalize_and_persist(
        self,
        *,
        run_id: str,
        started_at: datetime,
        start_mono: float,
        drafts_collected: int,
        articles_verified: int,
        articles_rejected: int,
        articles_published: int,
        domain_breakdown: Dict[DomainType, int],
        agent_records: List[AgentExecutionRecord],
        delivery_outcomes: List[ChannelDeliveryOutcome],
        quarantined_items: List[Dict[str, Any]],
        errors: List[str],
        newsletter: Optional[Newsletter],
        had_stage_failure: bool,
    ) -> PipelineRunReport:
        """Assemble terminal PipelineRunReport and persist it safely."""
        finished_at = self._now()
        duration_seconds = round(time.monotonic() - start_mono, 3)

        delivery_status = compute_delivery_status(
            outcomes=delivery_outcomes,
            newsletter_created=(newsletter is not None),
            had_stage_failure=had_stage_failure,
        )

        # Update newsletter aggregate status if webhooks ran
        if newsletter is not None and delivery_outcomes:
            newsletter.delivered_successfully = delivery_status in (
                DeliveryStatus.DELIVERED.value,
                DeliveryStatus.PARTIAL.value,
                DeliveryStatus.SAVED_ONLY.value,
            )

        has_partial_agent = any(r.status == "PARTIAL_SUCCESS" for r in agent_records)
        if had_stage_failure or newsletter is None or delivery_status == DeliveryStatus.FAILED.value:
            run_status = "FAILED"
            is_success = False
        elif delivery_status == DeliveryStatus.PARTIAL.value or has_partial_agent or len(errors) > 0:
            run_status = "PARTIAL"
            is_success = False
        else:
            run_status = "SUCCESS"
            is_success = True

        report = PipelineRunReport(
            run_id=run_id,
            started_at=started_at,
            finished_at=finished_at,
            duration_seconds=duration_seconds,
            drafts_collected=drafts_collected,
            articles_verified=articles_verified,
            articles_rejected=articles_rejected,
            articles_published=articles_published,
            domain_breakdown=domain_breakdown,
            agent_records=agent_records,
            delivery_outcomes=delivery_outcomes,
            quarantined_items=quarantined_items,
            delivery_status=delivery_status,
            run_status=run_status,
            is_success=is_success,
            report_persisted=True,
            errors=list(errors),
            newsletter_id=newsletter.id if newsletter else None,
        )

        try:
            self.storage.record_pipeline_run(report)
        except Exception as exc:
            sanitized_err = redact_secrets(
                f"Failed to record pipeline run in database: {exc}", self.settings
            )
            logger.error(sanitized_err, exc_info=True)
            report.report_persisted = False
            report.errors.append(sanitized_err)
            if report.run_status == "SUCCESS":
                report.run_status = "PARTIAL"
            report.is_success = False

        logger.info("============================================================")
        logger.info(
            f"Pipeline Run {run_id} completed in {duration_seconds}s "
            f"(RunStatus: {report.run_status}, DeliveryStatus: {report.delivery_status})"
        )
        logger.info(
            f"Published: AI={domain_breakdown[DomainType.AI]}, "
            f"Cyber={domain_breakdown[DomainType.CYBERSECURITY]}, "
            f"V2X={domain_breakdown[DomainType.V2X]}"
        )
        logger.info("============================================================")
        return report

    def run(self) -> Tuple[PipelineRunReport, Optional[Newsletter]]:
        """Execute complete pipeline workflow with explicit failure boundaries and awaited delivery."""
        run_id = f"run-{uuid.uuid4().hex[:8]}"
        started_at = self._now()
        start_mono = time.monotonic()
        logger.info("============================================================")
        logger.info(f"Starting DailyAI Pipeline Run: {run_id}")
        logger.info("============================================================")

        agent_records: List[AgentExecutionRecord] = []
        delivery_outcomes: List[ChannelDeliveryOutcome] = []
        quarantined_items: List[Dict[str, Any]] = []
        errors: List[str] = []
        newsletter: Optional[Newsletter] = None

        drafts_collected = 0
        articles_verified = 0
        articles_rejected = 0
        articles_published = 0
        had_stage_failure = False
        domain_breakdown: Dict[DomainType, int] = {
            DomainType.AI: 0,
            DomainType.CYBERSECURITY: 0,
            DomainType.V2X: 0,
        }

        report: Optional[PipelineRunReport] = None
        try:
            # ------------------------------------------------------------------
            # STEP 1: Agent 1 — Research & Intelligence Gathering
            # ------------------------------------------------------------------
            res1, rec1, stage1_ok = self._execute_stage(
                "research", self.agent1, None, expected_output_type=list
            )
            agent_records.append(rec1)
            quarantined_items.extend(getattr(self.agent1, "last_quarantined_items", []) or [])

            if not stage1_ok:
                had_stage_failure = True
                err_msg = f"Agent 1 encountered failures: {', '.join(rec1.errors)}"
                logger.error(err_msg)
                errors.append(err_msg)
                drafts = None
            else:
                drafts = res1.output if (res1 and res1.output is not None) else []
                drafts_collected = len(drafts)
                if rec1.status == "PARTIAL_SUCCESS" and rec1.errors:
                    errors.extend(rec1.errors)

            logger.info(f"Agent 1 finished. Candidate drafts gathered: {drafts_collected}")

            # ------------------------------------------------------------------
            # STEP 2: Agent 2 — Independent Fact-Checking & Quality Gate
            # ------------------------------------------------------------------
            verified_articles = None
            stage2_ok = False
            if stage1_ok and isinstance(drafts, list):
                res2, rec2, stage2_ok = self._execute_stage(
                    "fact_check", self.agent2, drafts, expected_output_type=list
                )
                agent_records.append(rec2)
                quarantined_items.extend(getattr(self.agent2, "last_rejected_items", []) or [])

                if not stage2_ok:
                    had_stage_failure = True
                    err_msg = f"Agent 2 encountered failures: {', '.join(rec2.errors)}"
                    logger.error(err_msg)
                    errors.append(err_msg)
                else:
                    verified_articles = res2.output if (res2 and res2.output is not None) else []
                    articles_verified = len(verified_articles)
                    articles_rejected = max(0, drafts_collected - articles_verified)
                    if rec2.status == "PARTIAL_SUCCESS" and rec2.errors:
                        errors.extend(rec2.errors)

                logger.info(
                    f"Agent 2 finished. Verified & approved articles: {articles_verified} (Rejected: {articles_rejected})"
                )
            else:
                logger.warning("Skipping Agent 2 (Fact-Check) because Agent 1 did not produce a valid draft list.")

            # ------------------------------------------------------------------
            # STEP 3: Agent 3 — Newsletter Generation & Local/Email Delivery
            # ------------------------------------------------------------------
            stage3_ok = False
            if stage2_ok and isinstance(verified_articles, list):
                res3, rec3, stage3_ok = self._execute_stage(
                    "newsletter", self.agent3, verified_articles, expected_output_type=Newsletter
                )
                agent_records.append(rec3)

                if not stage3_ok:
                    had_stage_failure = True
                    err_msg = f"Agent 3 encountered failures: {', '.join(rec3.errors)}"
                    logger.error(err_msg)
                    errors.append(err_msg)
                else:
                    newsletter = res3.output if res3 else None
                    if newsletter:
                        articles_published = newsletter.total_articles
                        for sec in newsletter.sections:
                            domain_breakdown[sec.domain] = len(sec.articles)
                        delivery_outcomes.extend(newsletter.channel_outcomes)
                    if rec3.status == "PARTIAL_SUCCESS" and rec3.errors:
                        errors.extend(rec3.errors)
            else:
                logger.warning("Skipping Agent 3 (Newsletter) because prior stage failed.")

            # ------------------------------------------------------------------
            # STEP 4: Webhook Distribution (awaited before report persistence)
            # ------------------------------------------------------------------
            if stage3_ok and newsletter is not None:
                elapsed = round(time.monotonic() - start_mono, 3)
                payload = self._build_webhook_payload(newsletter, run_id, elapsed, domain_breakdown)
                try:
                    webhook_outcomes = self._run_webhooks_sync(payload)
                    delivery_outcomes.extend(webhook_outcomes)
                    for outcome in webhook_outcomes:
                        if outcome.status == "FAILED" and outcome.error:
                            errors.append(f"Webhook '{outcome.channel}' delivery failed: {outcome.error}")
                except Exception as exc:
                    sanitized_err = redact_secrets(f"{type(exc).__name__}: {exc}", self.settings)
                    logger.error("Webhook distribution failed unexpectedly: %s", sanitized_err, exc_info=True)
                    delivery_outcomes.append(
                        ChannelDeliveryOutcome(
                            channel="webhooks",
                            enabled=True,
                            attempted=True,
                            status="FAILED",
                            error=sanitized_err,
                            completed_at=self._now(),
                        )
                    )
                    errors.append(f"Webhook distribution failed: {sanitized_err}")
        except Exception as exc:
            had_stage_failure = True
            sanitized_err = redact_secrets(f"Unhandled orchestrator error: {type(exc).__name__}: {exc}", self.settings)
            logger.error(sanitized_err, exc_info=True)
            errors.append(sanitized_err)
        finally:
            report = self._finalize_and_persist(
                run_id=run_id,
                started_at=started_at,
                start_mono=start_mono,
                drafts_collected=drafts_collected,
                articles_verified=articles_verified,
                articles_rejected=articles_rejected,
                articles_published=articles_published,
                domain_breakdown=domain_breakdown,
                agent_records=agent_records,
                delivery_outcomes=delivery_outcomes,
                quarantined_items=quarantined_items,
                errors=errors,
                newsletter=newsletter,
                had_stage_failure=had_stage_failure,
            )

        return report, newsletter

    async def run_async(self) -> Tuple[PipelineRunReport, Optional[Newsletter]]:
        """Async entry point that awaits webhook delivery natively on the active event loop."""
        run_id = f"run-{uuid.uuid4().hex[:8]}"
        started_at = self._now()
        start_mono = time.monotonic()

        agent_records: List[AgentExecutionRecord] = []
        delivery_outcomes: List[ChannelDeliveryOutcome] = []
        quarantined_items: List[Dict[str, Any]] = []
        errors: List[str] = []
        newsletter: Optional[Newsletter] = None

        drafts_collected = 0
        articles_verified = 0
        articles_rejected = 0
        articles_published = 0
        had_stage_failure = False
        domain_breakdown: Dict[DomainType, int] = {
            DomainType.AI: 0,
            DomainType.CYBERSECURITY: 0,
            DomainType.V2X: 0,
        }

        report: Optional[PipelineRunReport] = None
        try:
            res1, rec1, stage1_ok = self._execute_stage(
                "research", self.agent1, None, expected_output_type=list
            )
            agent_records.append(rec1)
            quarantined_items.extend(getattr(self.agent1, "last_quarantined_items", []) or [])

            if not stage1_ok:
                had_stage_failure = True
                errors.append(f"Agent 1 encountered failures: {', '.join(rec1.errors)}")
                drafts = None
            else:
                drafts = res1.output if (res1 and res1.output is not None) else []
                drafts_collected = len(drafts)
                if rec1.status == "PARTIAL_SUCCESS" and rec1.errors:
                    errors.extend(rec1.errors)

            verified_articles = None
            stage2_ok = False
            if stage1_ok and isinstance(drafts, list):
                res2, rec2, stage2_ok = self._execute_stage(
                    "fact_check", self.agent2, drafts, expected_output_type=list
                )
                agent_records.append(rec2)
                quarantined_items.extend(getattr(self.agent2, "last_rejected_items", []) or [])

                if not stage2_ok:
                    had_stage_failure = True
                    errors.append(f"Agent 2 encountered failures: {', '.join(rec2.errors)}")
                else:
                    verified_articles = res2.output if (res2 and res2.output is not None) else []
                    articles_verified = len(verified_articles)
                    articles_rejected = max(0, drafts_collected - articles_verified)
                    if rec2.status == "PARTIAL_SUCCESS" and rec2.errors:
                        errors.extend(rec2.errors)

            stage3_ok = False
            if stage2_ok and isinstance(verified_articles, list):
                res3, rec3, stage3_ok = self._execute_stage(
                    "newsletter", self.agent3, verified_articles, expected_output_type=Newsletter
                )
                agent_records.append(rec3)

                if not stage3_ok:
                    had_stage_failure = True
                    errors.append(f"Agent 3 encountered failures: {', '.join(rec3.errors)}")
                else:
                    newsletter = res3.output if res3 else None
                    if newsletter:
                        articles_published = newsletter.total_articles
                        for sec in newsletter.sections:
                            domain_breakdown[sec.domain] = len(sec.articles)
                        delivery_outcomes.extend(newsletter.channel_outcomes)
                    if rec3.status == "PARTIAL_SUCCESS" and rec3.errors:
                        errors.extend(rec3.errors)

            if stage3_ok and newsletter is not None:
                elapsed = round(time.monotonic() - start_mono, 3)
                payload = self._build_webhook_payload(newsletter, run_id, elapsed, domain_breakdown)
                try:
                    webhook_outcomes = await distribute_results(payload, settings=self.settings)
                    delivery_outcomes.extend(webhook_outcomes)
                    for outcome in webhook_outcomes:
                        if outcome.status == "FAILED" and outcome.error:
                            errors.append(f"Webhook '{outcome.channel}' delivery failed: {outcome.error}")
                except Exception as exc:
                    sanitized_err = redact_secrets(f"{type(exc).__name__}: {exc}", self.settings)
                    logger.error("Webhook distribution failed unexpectedly: %s", sanitized_err, exc_info=True)
                    delivery_outcomes.append(
                        ChannelDeliveryOutcome(
                            channel="webhooks",
                            enabled=True,
                            attempted=True,
                            status="FAILED",
                            error=sanitized_err,
                            completed_at=self._now(),
                        )
                    )
                    errors.append(f"Webhook distribution failed: {sanitized_err}")
        except Exception as exc:
            had_stage_failure = True
            sanitized_err = redact_secrets(f"Unhandled orchestrator error: {type(exc).__name__}: {exc}", self.settings)
            logger.error(sanitized_err, exc_info=True)
            errors.append(sanitized_err)
        finally:
            report = self._finalize_and_persist(
                run_id=run_id,
                started_at=started_at,
                start_mono=start_mono,
                drafts_collected=drafts_collected,
                articles_verified=articles_verified,
                articles_rejected=articles_rejected,
                articles_published=articles_published,
                domain_breakdown=domain_breakdown,
                agent_records=agent_records,
                delivery_outcomes=delivery_outcomes,
                quarantined_items=quarantined_items,
                errors=errors,
                newsletter=newsletter,
                had_stage_failure=had_stage_failure,
            )

        return report, newsletter
