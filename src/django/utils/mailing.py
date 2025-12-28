from django.core.mail import EmailMessage, get_connection as get_smtp_connection
from typing import Any, Optional
from django.conf import settings


def get_app_name():
    """Returns the django application name as set in `settings.APPLICATION_NAME`"""
    getattr(settings, "APPLICATION_NAME", None)


def send_smtp_mail(
    subject: str,
    message: str,
    to_email: str,
    from_email: str = settings.DEFAULT_FROM_EMAIL,
    connection: Optional[Any] = None,
    html: bool = False,
) -> None:
    """
    Send email.

    :param subject: The subject of the email.
    :param message: The message to send.
    :param to_email: The email address to send to.
    :param from_email: The email address to send from.
    :param connection: The email connection to use.
    :param html: Whether the message is an html message.
    """
    connection = connection or get_smtp_connection()
    app_name = get_app_name()
    if app_name:
        sender = f"{app_name} <{from_email}>"
    else:
        sender = from_email

    email = EmailMessage(
        subject=subject,
        body=message,
        from_email=sender,
        to=[to_email],
        connection=connection,
    )
    if html:
        email.content_subtype = "html"
    email.send(fail_silently=False)
    return None
