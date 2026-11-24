"""Integration tests for the end-to-end PipelineOrchestrator."""

import pytest
from dailyai.agents.fact_check_agent import FactCheckAgent
from dailyai.agents.newsletter_agent import NewsletterAgent
from dailyai.agents.research_agent import ResearchAgent
from dailyai.models.article import DomainType
from dailyai.pipeline.orchestrator import PipelineOrchestrator
from dailyai.services.delivery.mock import MockDeliveryChannel


def test_pipeline_orchestrator_e2e(test_settings, mock_llm, mock_search, sqlite_store):
    """Verify complete end-to-end flow: Agent 1 -> Agent 2 -> Agent 3 -> Output & Storage."""
    mock_delivery = MockDeliveryChannel()

    research_agent = ResearchAgent(
        settings=test_settings,
        llm_client=mock_llm,
        search_engine=mock_search,
        storage=sqlite_store,
    )
    fact_check_agent = FactCheckAgent(
        settings=test_settings,
        llm_client=mock_llm,
        search_engine=mock_search,
    )
    newsletter_agent = NewsletterAgent(
        settings=test_settings,
        llm_client=mock_llm,
        delivery_channels=[mock_delivery],
        storage=sqlite_store,
    )

    orchestrator = PipelineOrchestrator(
        settings=test_settings,
        research_agent=research_agent,
        fact_check_agent=fact_check_agent,
        newsletter_agent=newsletter_agent,
        storage=sqlite_store,
    )

    report, newsletter = orchestrator.run()

    assert report.is_success is True
    assert report.drafts_collected > 0
    assert report.articles_verified > 0
    assert report.articles_published > 0
    assert len(report.agent_records) == 3
    assert report.delivery_status == "DELIVERED"

    # Verify domain breakdown
    assert DomainType.AI in report.domain_breakdown
    assert DomainType.CYBERSECURITY in report.domain_breakdown
    assert DomainType.V2X in report.domain_breakdown

    # Verify newsletter was generated and passed to delivery channel
    assert newsletter is not None
    assert len(mock_delivery.delivered_newsletters) == 1

    # Verify report was recorded in SQLite database
    recent = sqlite_store.get_recent_runs(limit=1)
    assert len(recent) == 1
    assert recent[0]["run_id"] == report.run_id


def test_pipeline_orchestrator_subsequent_run_deduplication(test_settings, mock_llm, mock_search, sqlite_store):
    """Verify that subsequent run does not re-publish previously published articles."""
    mock_delivery = MockDeliveryChannel()

    research_agent = ResearchAgent(
        settings=test_settings,
        llm_client=mock_llm,
        search_engine=mock_search,
        storage=sqlite_store,
    )
    fact_check_agent = FactCheckAgent(
        settings=test_settings,
        llm_client=mock_llm,
        search_engine=mock_search,
    )
    newsletter_agent = NewsletterAgent(
        settings=test_settings,
        llm_client=mock_llm,
        delivery_channels=[mock_delivery],
        storage=sqlite_store,
    )

    orchestrator = PipelineOrchestrator(
        settings=test_settings,
        research_agent=research_agent,
        fact_check_agent=fact_check_agent,
        newsletter_agent=newsletter_agent,
        storage=sqlite_store,
    )

    # First run publishes articles
    report1, _ = orchestrator.run()
    assert report1.articles_published > 0

    # Second run finds no novel articles (all previously seen URLs deduplicated)
    report2, nl2 = orchestrator.run()
    assert report2.drafts_collected == 0
    assert report2.articles_published == 0


# ------------------------------------------------------------------------------
# Issue #4 Tests: Awaited webhook delivery & per-channel outcome tracking
# ------------------------------------------------------------------------------

def _build_orchestrator(test_settings, mock_llm, mock_search, sqlite_store, delivery_channels=None):
    research_agent = ResearchAgent(
        settings=test_settings,
        llm_client=mock_llm,
        search_engine=mock_search,
        storage=sqlite_store,
    )
    fact_check_agent = FactCheckAgent(
        settings=test_settings,
        llm_client=mock_llm,
        search_engine=mock_search,
    )
    newsletter_agent = NewsletterAgent(
        settings=test_settings,
        llm_client=mock_llm,
        delivery_channels=delivery_channels,
        storage=sqlite_store,
    )
    return PipelineOrchestrator(
        settings=test_settings,
        research_agent=research_agent,
        fact_check_agent=fact_check_agent,
        newsletter_agent=newsletter_agent,
        storage=sqlite_store,
    )


def test_pipeline_saved_only_when_only_file_export_succeeds(test_settings, mock_llm, mock_search, sqlite_store):
    """When email is disabled and no webhooks are configured, status is SAVED_ONLY."""
    from unittest.mock import patch

    test_settings.email_enabled = False
    orchestrator = _build_orchestrator(test_settings, mock_llm, mock_search, sqlite_store, delivery_channels=None)

    with patch("dailyai.pipeline.orchestrator.DeliveryFactory.get_enabled_services", return_value=[]):
        report, newsletter = orchestrator.run()

    assert report.delivery_status == "SAVED_ONLY"
    assert report.run_status == "SUCCESS"
    assert report.is_success is True
    channels = {o.channel: o for o in report.delivery_outcomes}
    assert channels["file_export"].status == "SUCCESS"
    assert channels["email"].status == "SKIPPED"
    assert channels["email"].attempted is False


def test_pipeline_webhooks_awaited_without_active_event_loop_partial_and_persisted(
    test_settings, mock_llm, mock_search, sqlite_store
):
    """Without an active event loop, webhooks complete before report persistence and track partial success."""
    import asyncio
    from unittest.mock import patch
    from dailyai.services.delivery.base import DeliveryService

    completed_events = []

    class FakeWebhook(DeliveryService):
        def __init__(self, channel_name: str, should_succeed: bool):
            self.channel_name = channel_name
            self._should_succeed = should_succeed
            self.last_error = None
            self.closed = False

        def build_payload(self, data):
            return data

        async def deliver(self, data):
            await asyncio.sleep(0.02)
            completed_events.append(self.channel_name)
            if not self._should_succeed:
                self.last_error = f"{self.channel_name} HTTP 500"
                return False
            return True

        async def close(self):
            self.closed = True

    slack = FakeWebhook("slack", True)
    discord = FakeWebhook("discord", False)
    teams = FakeWebhook("teams", True)

    orchestrator = _build_orchestrator(
        test_settings, mock_llm, mock_search, sqlite_store, delivery_channels=[MockDeliveryChannel()]
    )

    with patch(
        "dailyai.pipeline.orchestrator.DeliveryFactory.get_enabled_services",
        return_value=[slack, discord, teams],
    ):
        report, _ = orchestrator.run()

    # All webhooks finished BEFORE run() returned
    assert set(completed_events) == {"slack", "discord", "teams"}
    assert slack.closed and discord.closed and teams.closed
    assert report.delivery_status == "PARTIAL"
    assert report.run_status == "PARTIAL"

    # Verify channel-level outcomes were persisted to SQLite
    stored = sqlite_store.get_recent_runs(limit=1)[0]
    stored_channels = {o["channel"]: o for o in stored["delivery_outcomes"]}
    assert stored_channels["slack"]["status"] == "SUCCESS"
    assert stored_channels["teams"]["status"] == "SUCCESS"
    assert stored_channels["discord"]["status"] == "FAILED"
    assert "HTTP 500" in stored_channels["discord"]["error"]
    assert stored_channels["discord"]["completed_at"] is not None


@pytest.mark.asyncio
async def test_pipeline_webhooks_awaited_inside_active_event_loop(
    test_settings, mock_llm, mock_search, sqlite_store
):
    """When run() is called inside an already-running event loop, webhooks still complete before return & persistence."""
    import asyncio
    from unittest.mock import patch
    from dailyai.services.delivery.base import DeliveryService

    delivered = []

    class SlowWebhook(DeliveryService):
        channel_name = "slack"

        def __init__(self):
            self.last_error = None
            self.closed = False

        def build_payload(self, data):
            return data

        async def deliver(self, data):
            await asyncio.sleep(0.03)
            delivered.append("slack")
            return True

        async def close(self):
            self.closed = True

    svc = SlowWebhook()
    orchestrator = _build_orchestrator(
        test_settings, mock_llm, mock_search, sqlite_store, delivery_channels=[MockDeliveryChannel()]
    )

    with patch("dailyai.pipeline.orchestrator.DeliveryFactory.get_enabled_services", return_value=[svc]):
        report, _ = orchestrator.run()

    assert delivered == ["slack"]
    assert svc.closed is True
    assert report.delivery_status == "DELIVERED"
    assert report.run_status == "SUCCESS"
    stored = sqlite_store.get_recent_runs(limit=1)[0]
    assert any(o["channel"] == "slack" and o["status"] == "SUCCESS" for o in stored["delivery_outcomes"])


def test_pipeline_all_channels_failed_sets_failed_status(test_settings, mock_llm, mock_search, sqlite_store):
    """When all attempted delivery channels fail, aggregate status is FAILED."""
    from unittest.mock import patch
    from dailyai.services.delivery.base import BaseDeliveryChannel, DeliveryService

    class FailingChannel(BaseDeliveryChannel):
        channel_name = "email"

        def deliver(self, newsletter):
            raise RuntimeError("SMTP connection refused")

    class FailingWebhook(DeliveryService):
        channel_name = "discord"

        def __init__(self):
            self.last_error = "HTTP 502"
            self.closed = False

        def build_payload(self, data):
            return data

        async def deliver(self, data):
            return False

        async def close(self):
            self.closed = True

    orchestrator = _build_orchestrator(
        test_settings, mock_llm, mock_search, sqlite_store, delivery_channels=[FailingChannel()]
    )

    with patch("dailyai.pipeline.orchestrator.DeliveryFactory.get_enabled_services", return_value=[FailingWebhook()]):
        report, _ = orchestrator.run()

    assert report.delivery_status == "FAILED"
    assert report.run_status == "FAILED"
    assert report.is_success is False
    by_channel = {o.channel: o for o in report.delivery_outcomes}
    assert by_channel["email"].status == "FAILED"
    assert by_channel["discord"].status == "FAILED"


# ------------------------------------------------------------------------------
# Issue #7 Tests: Agent failure isolation, secret redaction & guaranteed persistence
# ------------------------------------------------------------------------------

@pytest.mark.parametrize("failing_stage", ["agent1", "agent2", "agent3"])
def test_pipeline_isolates_unexpected_agent_exceptions_and_persists_report(
    failing_stage, test_settings, mock_llm, mock_search, sqlite_store
):
    """Unexpected exceptions escaping any agent are captured, downstream stages are gated, and a terminal report is persisted."""
    from unittest.mock import MagicMock

    orchestrator = _build_orchestrator(
        test_settings, mock_llm, mock_search, sqlite_store, delivery_channels=[MockDeliveryChannel()]
    )

    secret_val = test_settings.gemini_api_key.get_secret_value()
    boom_msg = f"Unexpected crash with key={secret_val} and Bearer supersecrettoken123"

    agent2_spy = MagicMock(wraps=orchestrator.agent2.execute)
    agent3_spy = MagicMock(wraps=orchestrator.agent3.execute)
    orchestrator.agent2.execute = agent2_spy
    orchestrator.agent3.execute = agent3_spy

    if failing_stage == "agent1":
        orchestrator.agent1.execute = MagicMock(side_effect=RuntimeError(boom_msg))
    elif failing_stage == "agent2":
        orchestrator.agent2.execute = MagicMock(side_effect=RuntimeError(boom_msg))
    elif failing_stage == "agent3":
        orchestrator.agent3.execute = MagicMock(side_effect=RuntimeError(boom_msg))

    report, newsletter = orchestrator.run()

    assert report.run_status == "FAILED"
    assert report.is_success is False
    assert report.delivery_status == "FAILED"
    assert report.report_persisted is True
    assert newsletter is None

    # Downstream gating verified
    if failing_stage == "agent1":
        assert len(report.agent_records) == 1
        agent2_spy.assert_not_called()
        agent3_spy.assert_not_called()
    elif failing_stage == "agent2":
        assert len(report.agent_records) == 2
        agent3_spy.assert_not_called()
    elif failing_stage == "agent3":
        assert len(report.agent_records) == 3

    # Diagnostic metadata and secret redaction verified
    failed_rec = report.agent_records[-1]
    assert failed_rec.status == "FAILED"
    assert failed_rec.metadata.get("exception_type") == "RuntimeError"
    assert failed_rec.metadata.get("failed_at") is not None
    joined_errors = " ".join(report.errors + failed_rec.errors)
    assert secret_val not in joined_errors
    assert "supersecrettoken123" not in joined_errors
    assert "[REDACTED]" in joined_errors

    # Terminal report persisted in SQLite
    recent = sqlite_store.get_recent_runs(limit=1)
    assert len(recent) == 1
    assert recent[0]["run_id"] == report.run_id
    assert recent[0]["run_status"] == "FAILED"


def test_pipeline_handles_report_persistence_exception_gracefully(
    test_settings, mock_llm, mock_search, sqlite_store
):
    """If report persistence raises, orchestrator does not crash and surfaces the persistence error."""
    from unittest.mock import MagicMock

    orchestrator = _build_orchestrator(
        test_settings, mock_llm, mock_search, sqlite_store, delivery_channels=[MockDeliveryChannel()]
    )
    sqlite_store.record_pipeline_run = MagicMock(side_effect=OSError("disk full"))

    report, newsletter = orchestrator.run()

    assert newsletter is not None
    assert report.report_persisted is False
    assert report.run_status == "PARTIAL"
    assert report.is_success is False
    assert any("disk full" in e for e in report.errors)
