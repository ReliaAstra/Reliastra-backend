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
        use_tls: bool | None = None,
    ) -> None:
        self.smtp_host = smtp_host or settings.SMTP_HOST
        self.smtp_port = smtp_port or settings.SMTP_PORT
        self.smtp_from = smtp_from or settings.SMTP_FROM
        self.use_tls = settings.SMTP_USE_TLS if use_tls is None else use_tls

    def send_email(
        self,
        to_email: str,
        subject: str,
        body: str,
        html_body: str | None = None,
    ) -> bool:
        logger.info("Sending email to '%s': Subject='%s'", to_email, subject)
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = self.smtp_from
        message["To"] = to_email
        message.attach(MIMEText(body, "plain"))
        if html_body:
            message.attach(MIMEText(html_body, "html"))

        server: smtplib.SMTP | smtplib.SMTP_SSL | None = None
        try:
            if self.smtp_port == 465:
                server = smtplib.SMTP_SSL(
                    self.smtp_host, self.smtp_port, timeout=3
                )
            else:
                server = smtplib.SMTP(
                    self.smtp_host, self.smtp_port, timeout=3
                )
                if self.use_tls or self.smtp_port == 587:
                    server.starttls()
            server.send_message(message)
            server.quit()
            server = None
            logger.info(
                "Successfully sent email via SMTP %s:%s",
                self.smtp_host,
                self.smtp_port,
            )
            return True
        except Exception as exc:
            logger.warning("SMTP delivery failed (%s), email not sent.", exc)
            return False
        finally:
            if server is not None:
                try:
                    server.quit()
                except Exception:
                    pass


email_client = EmailClient()
