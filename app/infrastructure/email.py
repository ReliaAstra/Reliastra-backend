import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from app.config import settings

logger = logging.getLogger(__name__)


class EmailClient:
    def __init__(
        self,
        smtp_host: str | None = None,
        smtp_port: int | None = None,
        smtp_from: str | None = None,
    ) -> None:
        self.smtp_host = smtp_host or settings.SMTP_HOST
        self.smtp_port = smtp_port or settings.SMTP_PORT
        self.smtp_from = smtp_from or settings.SMTP_FROM

    def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: str | None = None,
    ) -> bool:
        logger.info(
            "Sending email to '%s': Subject='%s'\nBody:\n%s",
            to_email,
            subject,
            body,
        )
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.smtp_from
        msg["To"] = to_email

        msg.attach(MIMEText(body, "plain"))
        if html_body:
            msg.attach(MIMEText(html_body, "html"))

        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=3) as server:
                server.send_message(msg)
            logger.info("Successfully sent email via SMTP %s:%s", self.smtp_host, self.smtp_port)
            return True
        except Exception as exc:
            logger.warning("SMTP connect failed (%s), email logged to console only.", exc)
            return True  # Stubbed for MVP: return True even if SMTP server is not running


email_client = EmailClient()
