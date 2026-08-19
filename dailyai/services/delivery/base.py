from abc import ABC, abstractmethod

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

import httpx
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

class DeliveryService(ABC):
    """
    Abstract base architectural component representing a generic delivery mechanism.
    Enforces the implementation of payload serialization and manages the HTTP socket layer.
    """

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url
        # Instantiate an isolated, asynchronous HTTP client.
        # Imposes a rigorous 10-second timeout ceiling to mitigate hanging connection vulnerabilities.
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))

    @abstractmethod
    def build_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Translates a normalized internal data dictionary into the specific JSON schema
        required by the target third-party API.
        """
        pass

    async def deliver(self, data: Dict[str, Any]) -> bool:
        """
        Executes the network transport protocol. Serializes the payload and dispatches
        it via an asynchronous POST request. Logs operational success or traps network anomalies.
        """
        payload = self.build_payload(data)
        try:
            response = await self.client.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            # Instruct httpx to raise an exception for HTTP 4xx/5xx status codes
            response.raise_for_status()
            logger.info(f"Transaction Success: Payload delivered via {self.__class__.__name__}")
            return True
        except httpx.HTTPStatusError as e:
            logger.error(f"{self.__class__.__name__} API Rejection: {e.response.status_code} - Payload: {e.response.text}")
            return False
        except httpx.RequestError as e:
            logger.error(f"{self.__class__.__name__} Transport Layer Error: {str(e)}")
            return False

    async def close(self):
        """
        Safely tears down the TCP connection pool allocated by the httpx async client.
        Must be invoked during application shutdown sequence.
        """
        await self.client.aclose()
