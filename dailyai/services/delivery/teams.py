from typing import Any, Dict
from dailyai.services.delivery.base import DeliveryService

class TeamsDeliveryService(DeliveryService):

    def build_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Serializes DailyAI states into a Microsoft Adaptive Card v1.2 specification,
        subsequently wrapping it inside an incoming webhook envelope structure.
        """
        title = data.get("title", "DailyAI Update")
        content = data.get("content", "")

        # Construct the deeply nested Adaptive Card component
        adaptive_card = {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.2", # Utilized for maximum cross-tenant compatibility
            "body": [
                {
                    "type": "TextBlock",
                    "text": title,
                    "weight": "Bolder",
                    "size": "Large",
                    "wrap": True
                },
                {
                    "type": "TextBlock",
                    "text": content,
                    "wrap": True # Required to prevent horizontal overflow in UI
                }
            ]
        }

        # Inject metadata via the FactSet component
        metadata = data.get("metadata", {})
        if metadata:
            facts = [{"title": str(k), "value": str(v)} for k, v in metadata.items()]
            adaptive_card["body"].append({
                "type": "FactSet",
                "facts": facts
            })

        # Return the strictly required Microsoft 365 JSON wrapper structure.
        return {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "contentUrl": None,
                    "content": adaptive_card
                }
            ]
        }
