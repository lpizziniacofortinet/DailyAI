from typing import Any, Dict
from dailyai.services.delivery.base import DeliveryService

class SlackDeliveryService(DeliveryService):

    def build_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Translates application data into the modular Slack Block Kit hierarchy.
        """
        # Header text elements are subject to a strict 150 character limit.
        title = data.get("title", "DailyAI Update")[:150]
        # Section text elements using mrkdwn are capped at 3000 characters.
        content = data.get("content", "")[:3000]

        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text", # Headers prohibit markdown interpretation
                    "text": title,
                    "emoji": True
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn", # Standard slack markdown dialect
                    "text": content
                }
            }
        ]

        # Assemble context blocks for secondary metadata display
        metadata = data.get("metadata", {})
        if metadata:
            elements = []
            for k, v in metadata.items():
                elements.append({"type": "mrkdwn", "text": f"*{k}*: {v}"})
                # The context block array is limited to exactly 10 child elements.
                if len(elements) == 10:
                    break

            blocks.append({
                "type": "context",
                "elements": elements
            })

        return {"blocks": blocks}
