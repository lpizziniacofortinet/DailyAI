from typing import Any, Dict
from dailyai.services.delivery.base import DeliveryService

class DiscordDeliveryService(DeliveryService):

    def _truncate(self, text: str, limit: int) -> str:
        """
        Executes strict string length reduction to satisfy Discord's algorithmic boundaries,
        appending an ellipsis to signify data reduction.
        """
        return text[:limit-3] + "..." if len(text) > limit else text

    def build_payload(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Maps normalized DailyAI output to the Discord Rich Embed JSON architecture.
        Expected internal signature: {"title": str, "content": str, "metadata": dict}
        """
        # Title limit is architecturally defined as 256 characters max.
        title = self._truncate(data.get("title", "DailyAI System Update"), 256)
        # Description limit is defined as 4096 characters max.
        description = self._truncate(data.get("content", ""), 4096)

        fields = []
        for key, value in data.get("metadata", {}).items():
            fields.append({
                "name": self._truncate(str(key), 256),
                "value": self._truncate(str(value), 1024),
                "inline": True
            })
            # Algorithmic ceiling: The Discord API rejects any embed containing more than 25 fields.
            if len(fields) == 25:
                break

        embed = {
            "title": title,
            "description": description,
            "color": 5793266, # Distinctive UI accent color (integer format)
            "fields": fields,
            "footer": {"text": "Delivered securely by the DailyAI Notification Subsystem"}
        }

        # Embeds must be nested within a root array in the JSON tree.
        return {"embeds": [embed]}
