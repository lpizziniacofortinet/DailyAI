"""Agent 3 — Newsletter & Delivery Agent.

Assembles strictly verified intelligence from Agent 2 into professional HTML and
text newsletters, executes email delivery, and archives publication records to
prevent future duplicates.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional
import uuid

from dailyai.agents.base import BaseAgent
from dailyai.config import Settings, get_settings
from dailyai.models.article import DomainType
from dailyai.models.fact_check import VerifiedArticle
from dailyai.models.newsletter import Newsletter, NewsletterSection
from dailyai.services.delivery.base import BaseDeliveryChannel
from dailyai.services.delivery.email_smtp import SMTPEmailDelivery
from dailyai.services.delivery.file_export import FileExportDelivery
from dailyai.services.llm.base import BaseLLMClient
from dailyai.services.llm.factory import get_llm_client
from dailyai.services.storage.base import BaseDeduplicationStore
from dailyai.services.storage.sqlite import SQLiteDeduplicationStore
from dailyai.templates import get_template_environment


class NewsletterAgent(BaseAgent[List[VerifiedArticle], Newsletter]):
    """Agent 3: Synthesizes, formats, renders, and distributes the final newsletter."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        llm_client: Optional[BaseLLMClient] = None,
        delivery_channels: Optional[List[BaseDeliveryChannel]] = None,
        storage: Optional[BaseDeduplicationStore] = None,
    ):
        super().__init__(name="Agent 3 — Newsletter & Delivery")
        self.settings = settings or get_settings()
        self.llm = llm_client or get_llm_client(self.settings)
        self.storage = storage or SQLiteDeduplicationStore(self.settings.database_path)
        self.jinja_env = get_template_environment()

        if delivery_channels is not None:
            self.delivery_channels = delivery_channels
        else:
            # Default channels: Always export files to disk + send SMTP email if enabled
            self.delivery_channels = [
                FileExportDelivery(output_dir=self.settings.output_dir, settings=self.settings),
                SMTPEmailDelivery(settings=self.settings),
            ]

    def _generate_subject_line(self, sections: List[NewsletterSection], date_str: str) -> str:
        """Generate a punchy, executive-level email subject line highlighting key headlines."""
        top_headlines: List[str] = []
        for sec in sections:
            if sec.articles:
                top_headlines.append(sec.articles[0].final_headline)

        if not top_headlines:
            return f"{self.settings.email_subject_prefix} Intelligence Brief — {date_str}"

        prompt = f"""
Create a compelling, professional, concise email subject line for today's tech intelligence brief.
Date: {date_str}
Top Stories:
{chr(10).join('- ' + h for h in top_headlines)}

Requirements:
- Prefix: None (prefix is handled separately)
- Length: 60-90 characters
- Tone: Executive, informative, technical
- Mention 2-3 key entities or topics from the stories
"""
        try:
            generated = self.llm.generate_text(
                prompt=prompt,
                system_instruction="Output ONLY the raw subject line text without quotes.",
                temperature=0.2,
            ).strip().strip('"').strip("'")
            return f"{self.settings.email_subject_prefix} {generated}"
        except Exception:
            return f"{self.settings.email_subject_prefix} AI, Cyber & V2X Intelligence Brief — {date_str}"

    def _build_sections(self, articles: List[VerifiedArticle]) -> List[NewsletterSection]:
        """Group verified articles into the 3 standardized domain sections."""
        domain_order = [DomainType.AI, DomainType.CYBERSECURITY, DomainType.V2X]
        sections: List[NewsletterSection] = []

        for domain in domain_order:
            domain_items = [a for a in articles if a.domain == domain and a.is_approved]
            # Ensure items are ordered by relevance_rank
            domain_items.sort(key=lambda a: a.relevance_rank)

            section = NewsletterSection(
                domain=domain,
                title=domain.display_name,
                articles=domain_items,
            )
            sections.append(section)

        return sections

    def _render_newsletter(
        self,
        newsletter_id: str,
        title: str,
        date_str: str,
        sections: List[NewsletterSection],
        total_articles: int,
    ) -> tuple[str, str]:
        """Render HTML and plain-text newsletter using Jinja2 templates."""
        context = {
            "id": newsletter_id,
            "title": title,
            "date_str": date_str,
            "sections": sections,
            "total_articles": total_articles,
        }

        html_template = self.jinja_env.get_template("email_html.jinja2")
        text_template = self.jinja_env.get_template("email_text.jinja2")

        html_content = html_template.render(context)
        text_content = text_template.render(context)

        return html_content, text_content

    def _run(self, input_data: List[VerifiedArticle]) -> Newsletter:
        """Assemble, render, deliver, and record the final newsletter."""
        newsletter_id = f"nl-{uuid.uuid4().hex[:8]}"
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%A, %B %d, %Y")

        # Build sections
        sections = self._build_sections(input_data or [])
        total_articles = sum(len(s.articles) for s in sections)

        self.logger.info(f"Assembling newsletter with {total_articles} verified articles.")

        # Generate subject line
        title = self._generate_subject_line(sections, date_str)

        # Render HTML and Plain Text
        html_content, text_content = self._render_newsletter(
            newsletter_id=newsletter_id,
            title=title,
            date_str=date_str,
            sections=sections,
            total_articles=total_articles,
        )

        newsletter = Newsletter(
            id=newsletter_id,
            title=title,
            date_str=date_str,
            generated_at=now,
            sections=sections,
            total_articles=total_articles,
            html_content=html_content,
            text_content=text_content,
            recipients=self.settings.email_recipients,
        )

        # A successful archive or delivery channel is a durable publication outcome.
        # SMTP failure must not erase a successful file archive, but total channel failure
        # must leave articles eligible for retry.
        successful_channels = 0
        for channel in self.delivery_channels:
            try:
                if channel.deliver(newsletter):
                    successful_channels += 1
            except Exception as e:
                self.logger.error(f"Delivery channel '{channel.__class__.__name__}' error: {e}")

        newsletter.delivered_successfully = successful_channels > 0
        newsletter.delivery_timestamp = (
            datetime.now(timezone.utc) if successful_channels else None
        )

        # Record articles only when at least one configured channel succeeded.
        if successful_channels and not self.settings.dry_run:
            for section in sections:
                for article in section.articles:
                    self.storage.mark_article_published(
                        url=article.source_url,
                        title=article.final_headline,
                        domain=section.domain.value,
                        newsletter_id=newsletter.id,
                    )
            self.logger.info(f"Recorded {total_articles} published articles in database.")

        return newsletter
