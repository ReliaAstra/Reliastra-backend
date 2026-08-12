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
        self.smtp_username = settings.SMTP_USERNAME or None
        self.smtp_password = settings.SMTP_PASSWORD or None
        self.smtp_tls = settings.SMTP_TLS
        self.smtp_ssl = settings.SMTP_SSL

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
            if self.smtp_ssl:
                server = smtplib.SMTP_SSL(
                    self.smtp_host, self.smtp_port, timeout=3
                )
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=3)
                if self.smtp_tls:
                    server.starttls()
            try:
                if self.smtp_username and self.smtp_password:
                    server.login(self.smtp_username, self.smtp_password)
                server.send_message(msg)
            finally:
                server.quit()
            logger.info(
                "Successfully sent email via SMTP %s:%s%s",
                self.smtp_host,
                self.smtp_port,
                " (TLS)" if self.smtp_tls else (" (SSL)" if self.smtp_ssl else ""),
            )
            return True
        except Exception as exc:
            logger.warning("SMTP connect failed (%s), email not sent.", exc)
            return False


email_client = EmailClient()
