"""File export delivery service for archiving newsletters and previews."""

import json
import os
from pathlib import Path
from typing import Optional, Union
from dailyai.config import Settings, get_settings
from dailyai.logging_config import get_logger
from dailyai.models.newsletter import Newsletter
from dailyai.services.delivery.base import BaseDeliveryChannel

logger = get_logger("delivery.file_export")


class FileExportDelivery(BaseDeliveryChannel):
    """Saves generated newsletters to local disk in HTML, Markdown/Text, and JSON."""

    def __init__(self, output_dir: Optional[Union[str, Path]] = None, settings: Optional[Settings] = None):
        cfg = settings or get_settings()
        self.output_dir = Path(output_dir or cfg.output_dir)
        os.makedirs(self.output_dir, exist_ok=True)

    def deliver(self, newsletter: Newsletter) -> bool:
        """Save newsletter artifacts to disk."""
        try:
            timestamp_str = newsletter.generated_at.strftime("%Y%m%d_%H%M%S")
            safe_id = newsletter.id.replace(" ", "_")

            # 1. Save HTML file
            html_file = self.output_dir / f"newsletter_{timestamp_str}_{safe_id}.html"
            with open(html_file, "w", encoding="utf-8") as f:
                f.write(newsletter.html_content)

            # 2. Save Plain Text / Markdown file
            text_file = self.output_dir / f"newsletter_{timestamp_str}_{safe_id}.txt"
            with open(text_file, "w", encoding="utf-8") as f:
                f.write(newsletter.text_content)

            # 3. Save Structured JSON data
            json_file = self.output_dir / f"newsletter_{timestamp_str}_{safe_id}.json"
            with open(json_file, "w", encoding="utf-8") as f:
                f.write(newsletter.model_dump_json(indent=2))

            # Also create/update 'latest.html' and 'latest.txt' for easy preview
            latest_html = self.output_dir / "latest.html"
            with open(latest_html, "w", encoding="utf-8") as f:
                f.write(newsletter.html_content)

            latest_text = self.output_dir / "latest.txt"
            with open(latest_text, "w", encoding="utf-8") as f:
                f.write(newsletter.text_content)

            logger.info(f"Archived newsletter files to: {self.output_dir.resolve()}")
            return True
        except Exception as e:
            logger.error(f"Failed to export newsletter files: {e}")
            return False
