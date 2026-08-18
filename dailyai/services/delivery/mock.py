"""Mock delivery channel for unit testing."""

from typing import List
from dailyai.logging_config import get_logger
from dailyai.models.newsletter import Newsletter
from dailyai.services.delivery.base import BaseDeliveryChannel

logger = get_logger("delivery.mock")


class MockDeliveryChannel(BaseDeliveryChannel):
    """Mock delivery service recording delivered newsletters in memory."""

    def __init__(self):
        self.delivered_newsletters: List[Newsletter] = []

    def deliver(self, newsletter: Newsletter) -> bool:
        """Record newsletter delivery in memory."""
        self.delivered_newsletters.append(newsletter)
        newsletter.delivered_successfully = True
        logger.info(f"MockDeliveryChannel delivered newsletter: '{newsletter.title}'")
        return True
