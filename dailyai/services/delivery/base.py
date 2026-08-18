"""Base interface for newsletter delivery channels."""

from abc import ABC, abstractmethod
from dailyai.models.newsletter import Newsletter


class BaseDeliveryChannel(ABC):
    """Abstract delivery channel for publishing newsletters (Email, Slack, Webhook, Archive)."""

    @abstractmethod
    def deliver(self, newsletter: Newsletter) -> bool:
        """Deliver the generated newsletter.

        Returns:
            True if delivery succeeded, False otherwise.
        """
        pass
