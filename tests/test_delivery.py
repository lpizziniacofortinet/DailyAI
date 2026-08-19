"""Unit tests for delivery channels (SMTP and FileExport)."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from dailyai.models.article import DomainType
from dailyai.models.newsletter import Newsletter, NewsletterSection
from dailyai.services.delivery.email_smtp import SMTPEmailDelivery
from dailyai.services.delivery.file_export import FileExportDelivery


@pytest.fixture
def mock_newsletter(sample_verified_article):
    """Provide a mock rendered newsletter."""
    section = NewsletterSection(
        domain=DomainType.AI,
        title=DomainType.AI.display_name,
        articles=[sample_verified_article],
    )
    return Newsletter(
        id="nl-delivery-test",
        title="[DailyAI] Test Delivery",
        date_str="Monday, Aug 17, 2026",
        sections=[section],
        total_articles=1,
        html_content="<html><body><h1>Test Newsletter</h1></body></html>",
        text_content="Test Newsletter Plain Text",
        recipients=["test@example.com"],
    )


def test_file_export_delivery(temp_output_dir, test_settings, mock_newsletter):
    """Verify FileExportDelivery saves HTML, TXT, and JSON files to disk."""
    delivery = FileExportDelivery(output_dir=temp_output_dir, settings=test_settings)
    success = delivery.deliver(mock_newsletter)
    assert success is True

    # Check files in output directory
    html_files = list(temp_output_dir.glob("*.html"))
    txt_files = list(temp_output_dir.glob("*.txt"))
    json_files = list(temp_output_dir.glob("*.json"))

    assert len(html_files) >= 1
    assert len(txt_files) >= 1
    assert len(json_files) >= 1

    latest_html = temp_output_dir / "latest.html"
    assert latest_html.exists()
    assert "Test Newsletter" in latest_html.read_text(encoding="utf-8")


def test_smtp_delivery_disabled_by_default(test_settings, mock_newsletter):
    """Verify SMTPEmailDelivery respects EMAIL_ENABLED=False."""
    test_settings.email_enabled = False
    delivery = SMTPEmailDelivery(settings=test_settings)
    success = delivery.deliver(mock_newsletter)
    assert success is True
    assert mock_newsletter.delivered_successfully is True


@patch("smtplib.SMTP")
def test_smtp_delivery_enabled(mock_smtp_class, test_settings, mock_newsletter):
    """Verify SMTPEmailDelivery connects and sends mail when enabled."""
    test_settings.email_enabled = True
    test_settings.smtp_use_tls = True
    test_settings.smtp_username = "bot@dailyai.local"
    
    mock_server = MagicMock()
    mock_smtp_class.return_value.__enter__.return_value = mock_server

    delivery = SMTPEmailDelivery(settings=test_settings)
    success = delivery.deliver(mock_newsletter)

    assert success is True
    assert mock_smtp_class.called
    assert mock_server.send_message.called

import respx
import httpx
from dailyai.services.delivery.discord import DiscordDeliveryService
from dailyai.services.delivery.slack import SlackDeliveryService
from dailyai.pipeline.orchestrator import distribute_results

@pytest.fixture
def sample_data():
    return {
        "title": "System Audit",
        "content": "Execution completed successfully.",
        "metadata": {"execution_id": "ABC-12345", "latency_ms": 42}
    }

@pytest.mark.asyncio
@respx.mock
async def test_discord_delivery_success(sample_data):
    url = "https://discord.com/api/webhooks/test-transaction"
    service = DiscordDeliveryService(url)

    request = respx.post(url).mock(return_value=httpx.Response(204))

    success = await service.deliver(sample_data)

    assert success is True
    assert request.called

    payload = request.calls.last.request.content.decode("utf-8")
    assert "embeds" in payload
    assert "System Audit" in payload

    await service.close()

@pytest.mark.asyncio
@respx.mock
async def test_orchestrator_fault_isolation(sample_data):
    discord_url = "https://discord.com/api/webhooks/fail"
    slack_url = "https://hooks.slack.com/services/success"

    services = [
        DiscordDeliveryService(discord_url),
        SlackDeliveryService(slack_url)
    ]

    discord_route = respx.post(discord_url).mock(return_value=httpx.Response(500))
    slack_route = respx.post(slack_url).mock(return_value=httpx.Response(200))

    with patch("dailyai.pipeline.orchestrator.DeliveryFactory.get_enabled_services", return_value=services):
        await distribute_results(sample_data)

    assert discord_route.called is True
    assert slack_route.called is True
