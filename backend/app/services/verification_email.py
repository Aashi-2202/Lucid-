"""TLS-only verification email transport; codes and credentials are never logged."""
from email.message import EmailMessage
import smtplib
import ssl

from app.core.config import settings


class EmailDeliveryError(Exception):
    pass


def configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_username and settings.smtp_password.get_secret_value()
                and (settings.smtp_from_email or settings.smtp_username))


def send_verification(email: str, code: str):
    if not configured():
        raise EmailDeliveryError("Email verification is not configured. Contact the administrator.")
    message = EmailMessage()
    message["Subject"] = "Your Lucid verification code"
    message["From"] = settings.smtp_from_email or settings.smtp_username
    message["To"] = email
    message.set_content(f"Your Lucid verification code is: {code}\n\n"
                        "This code expires in 10 minutes and can be used once.\n"
                        "If you did not request a Lucid account, ignore this email.\n"
                        "Lucid will never ask you to share this code with anyone.")
    context = ssl.create_default_context()
    try:
        client_type = smtplib.SMTP_SSL if settings.smtp_security == "ssl" else smtplib.SMTP
        kwargs = {"timeout": 15}
        if settings.smtp_security == "ssl":
            kwargs["context"] = context
        with client_type(settings.smtp_host, settings.smtp_port, **kwargs) as client:
            client.ehlo()
            if settings.smtp_security == "starttls":
                client.starttls(context=context)
                client.ehlo()
            client.login(settings.smtp_username, settings.smtp_password.get_secret_value())
            if client.send_message(message):
                raise EmailDeliveryError("Verification email could not be delivered. Please try again later.")
    except (OSError, smtplib.SMTPException, ValueError):
        raise EmailDeliveryError("Verification email could not be delivered. Please try again later.") from None
