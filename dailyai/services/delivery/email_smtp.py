"""SMTP email delivery implementation with TLS/SSL encryption and multipart MIME."""

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
import smtplib
import ssl
from typing import List, Optional
from tenacity import retry, stop_after_attempt, wait_exponential

from dailyai.config import Settings, get_settings
from dailyai.logging_config import get_logger
from dailyai.models.newsletter import Newsletter
from dailyai.services.delivery.base import BaseDeliveryChannel

logger = get_logger("delivery.smtp")


class SMTPEmailDelivery(BaseDeliveryChannel):
    """Sends newsletters via standard SMTP with STARTTLS or SSL encryption."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()

    def _create_message(self, newsletter: Newsletter) -> MIMEMultipart:
        """Create RFC-compliant multipart MIME email message."""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = newsletter.title
        msg["From"] = self.settings.email_from
        msg["To"] = ", ".join(newsletter.recipients or self.settings.email_recipients)
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain="dailyai.local")
        msg["Auto-Submitted"] = "auto-generated"

        # Plain text version (fallback)
        text_part = MIMEText(newsletter.text_content or "No plain text content available.", "plain", "utf-8")
        msg.attach(text_part)

        # HTML version (primary)
        if newsletter.html_content:
            html_part = MIMEText(newsletter.html_content, "html", "utf-8")
            msg.attach(html_part)

        return msg

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1.5, min=2, max=10),
    )
    def _send_smtp_payload(self, msg: MIMEMultipart, recipients: List[str]) -> None:
        """Connect to SMTP server and transmit message with retries."""
        host = self.settings.smtp_host
        port = self.settings.smtp_port
        username = self.settings.smtp_username
        password = (
            self.settings.smtp_password.get_secret_value()
            if self.settings.smtp_password
            else ""
        )

        logger.info(f"Connecting to SMTP server {host}:{port} (TLS: {self.settings.smtp_use_tls}, SSL: {self.settings.smtp_use_ssl})...")

        if self.settings.smtp_use_ssl:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as server:
                if username and password:
                    server.login(username, password)
                server.send_message(msg, from_addr=self.settings.email_from, to_addrs=recipients)
        else:
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.ehlo()
                if self.settings.smtp_use_tls:
                    context = ssl.create_default_context()
                    server.starttls(context=context)
                    server.ehlo()
                if username and password:
                    server.login(username, password)
                server.send_message(msg, from_addr=self.settings.email_from, to_addrs=recipients)

    def deliver(self, newsletter: Newsletter) -> bool:
        """Deliver newsletter to configured recipients."""
        recipients = newsletter.recipients or self.settings.email_recipients

        if not self.settings.email_enabled:
            logger.info(f"Email delivery disabled (EMAIL_ENABLED=False). Newsletter '{newsletter.title}' was generated and archived.")
            newsletter.delivered_successfully = True
            return True

        if not recipients:
            logger.warning("No email recipients configured. Skipping SMTP dispatch.")
            return False

        try:
            msg = self._create_message(newsletter)
            self._send_smtp_payload(msg, recipients)
            logger.info(f"Successfully sent newsletter '{newsletter.title}' to {len(recipients)} recipient(s): {', '.join(recipients)}")
            newsletter.delivered_successfully = True
            return True
        except Exception as e:
            logger.error(f"Failed to send email newsletter via SMTP: {e}", exc_info=True)
            newsletter.delivered_successfully = False
            return False
