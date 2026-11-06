
"""Pipeline Orchestrator for DailyAI.

Coordinates the end-to-end execution of Agent 1 (Research), Agent 2 (Verification),
and Agent 3 (Newsletter Delivery), generating auditable run reports and managing
failure boundaries.
"""

from datetime import datetime, timezone
import time
from typing import Dict, List, Optional, Tuple
import uuid

import asyncio
from dailyai.agents.fact_check_agent import FactCheckAgent
from dailyai.agents.newsletter_agent import NewsletterAgent
from dailyai.agents.research_agent import ResearchAgent
from dailyai.config import Settings, get_settings
from dailyai.logging_config import get_logger
from dailyai.models.article import DomainType
from dailyai.models.newsletter import Newsletter
from dailyai.models.pipeline import AgentExecutionRecord, PipelineRunReport
from dailyai.services.storage.base import BaseDeduplicationStore
from dailyai.services.storage.sqlite import SQLiteDeduplicationStore

logger = get_logger("pipeline.orchestrator")


class PipelineOrchestrator:
    """Coordinates and executes the 3-agent intelligence pipeline."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        research_agent: Optional[ResearchAgent] = None,
        fact_check_agent: Optional[FactCheckAgent] = None,
        newsletter_agent: Optional[NewsletterAgent] = None,
        storage: Optional[BaseDeduplicationStore] = None,
    ):
        self.settings = settings or get_settings()
        self.storage = storage or SQLiteDeduplicationStore(self.settings.database_path)

        self.agent1 = research_agent or ResearchAgent(settings=self.settings, storage=self.storage)
        self.agent2 = fact_check_agent or FactCheckAgent(settings=self.settings)
        self.agent3 = newsletter_agent or NewsletterAgent(settings=self.settings, storage=self.storage)

    def run(self) -> Tuple[PipelineRunReport, Optional[Newsletter]]:
        """Execute complete pipeline workflow.

        Workflow:
            Web/RSS Sources -> Agent 1 (Research) -> Agent 2 (Fact-Check) -> Agent 3 (Newsletter) -> Delivery

        Returns:
            Tuple of (PipelineRunReport, Optional[Newsletter])
        """
        run_id = f"run-{uuid.uuid4().hex[:8]}"
        started_at = datetime.now(timezone.utc)
        start_mono = time.monotonic()
        logger.info(f"============================================================")
        logger.info(f"Starting DailyAI Pipeline Run: {run_id}")
        logger.info(f"============================================================")

        agent_records: List[AgentExecutionRecord] = []
        errors: List[str] = []
        newsletter: Optional[Newsletter] = None

        drafts_collected = 0
        articles_verified = 0
        articles_rejected = 0
        articles_published = 0
        domain_breakdown: Dict[DomainType, int] = {
            DomainType.AI: 0,
            DomainType.CYBERSECURITY: 0,
            DomainType.V2X: 0,
        }

        # ----------------------------------------------------------------------
        # STEP 1: Agent 1 — Research & Intelligence Gathering
        # ----------------------------------------------------------------------
        res1 = self.agent1.execute(None)
        agent_records.append(res1.record)
        drafts = res1.output or []
        drafts_collected = len(drafts)

        if not res1.success:
            err_msg = f"Agent 1 encountered failures: {', '.join(res1.errors)}"
            logger.error(err_msg)
            errors.append(err_msg)

        logger.info(f"Agent 1 finished. Candidate drafts gathered: {drafts_collected}")

        # ----------------------------------------------------------------------
        # STEP 2: Agent 2 — Independent Fact-Checking & Quality Gate
        # ----------------------------------------------------------------------
        res2 = self.agent2.execute(drafts)
        agent_records.append(res2.record)
        verified_articles = res2.output or []
        articles_verified = len(verified_articles)
        articles_rejected = max(0, drafts_collected - articles_verified)

        if not res2.success:
            err_msg = f"Agent 2 encountered failures: {', '.join(res2.errors)}"
            logger.error(err_msg)
            errors.append(err_msg)

        logger.info(f"Agent 2 finished. Verified & approved articles: {articles_verified} (Rejected: {articles_rejected})")

        # ----------------------------------------------------------------------
        # STEP 3: Agent 3 — Newsletter Generation & Multi-Channel Delivery
        # ----------------------------------------------------------------------
        res3 = self.agent3.execute(verified_articles)
        agent_records.append(res3.record)
        newsletter = res3.output

        if newsletter:
            articles_published = newsletter.total_articles
            for sec in newsletter.sections:
                domain_breakdown[sec.domain] = len(sec.articles)
        else:
            articles_published = 0

        if not res3.success:
            err_msg = f"Agent 3 encountered failures: {', '.join(res3.errors)}"
            logger.error(err_msg)
            errors.append(err_msg)

        delivery_status = (
            "DELIVERED"
            if (newsletter and newsletter.delivered_successfully)
            else ("FAILED" if errors else "SAVED_TO_DISK")
        )

        finished_at = datetime.now(timezone.utc)
        duration_seconds = round(time.monotonic() - start_mono, 3)
        is_success = len(errors) == 0 and (newsletter is not None)

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
            delivery_status=delivery_status,
            is_success=is_success,
            errors=errors,
            newsletter_id=newsletter.id if newsletter else None,
        )

        # Record run history in persistent database
        try:
            self.storage.record_pipeline_run(report)
        except Exception as e:
            logger.error(f"Failed to record pipeline run in database: {e}")

        # Execute webhooks delivery if newsletter is generated
        if newsletter:
            data = {
                "title": newsletter.title,
                "content": f"DailyAI Pipeline executed successfully. {newsletter.total_articles} articles verified and published.",
                "metadata": {
                    "Run ID": run_id,
                    "Duration": f"{duration_seconds}s",
                    "AI Articles": domain_breakdown[DomainType.AI],
                    "Cyber Articles": domain_breakdown[DomainType.CYBERSECURITY],
                    "V2X Articles": domain_breakdown[DomainType.V2X]
                }
            }
            # Run the async distribution
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(distribute_results(data))
            except RuntimeError:
                asyncio.run(distribute_results(data))

        logger.info(f"============================================================")
        logger.info(f"Pipeline Run {run_id} completed in {duration_seconds}s (Status: {delivery_status})")
        logger.info(f"Published: AI={domain_breakdown[DomainType.AI]}, Cyber={domain_breakdown[DomainType.CYBERSECURITY]}, V2X={domain_breakdown[DomainType.V2X]}")
        logger.info(f"============================================================")

        return report, newsletter


from typing import Any

from dailyai.config import settings as delivery_settings
from dailyai.services.delivery import (
    DeliveryService,
    DiscordDeliveryService,
    SlackDeliveryService,
    TeamsDeliveryService
)

class DeliveryFactory:
    @staticmethod
    def get_enabled_services() -> List[DeliveryService]:
        services = []
        if delivery_settings.enable_discord and delivery_settings.discord_webhook_url:
            services.append(DiscordDeliveryService(str(delivery_settings.discord_webhook_url)))
        if delivery_settings.enable_slack and delivery_settings.slack_webhook_url:
            services.append(SlackDeliveryService(str(delivery_settings.slack_webhook_url)))
        if delivery_settings.enable_teams and delivery_settings.teams_webhook_url:
            services.append(TeamsDeliveryService(str(delivery_settings.teams_webhook_url)))
        return services

async def distribute_results(data: Dict[str, Any]):
    services = DeliveryFactory.get_enabled_services()
    if not services:
        logger.warning("Notification sequence aborted: No delivery services are currently active.")
        return

    logger.info(f"Initiating concurrent payload distribution to {len(services)} configured endpoints.")

    tasks = [service.deliver(data) for service in services]

    # Execute non-blocking I/O operations simultaneously.
    # The return_exceptions=True intercepts tracebacks natively.
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for service, result in zip(services, results):
        if isinstance(result, Exception):
            logger.error(
                f"Subsystem fault detected: Delivery to {service.__class__.__name__} "
                f"crashed unexpectedly with trace: {repr(result)}"
            )

    cleanup_tasks = [service.close() for service in services]
    await asyncio.gather(*cleanup_tasks, return_exceptions=True)
