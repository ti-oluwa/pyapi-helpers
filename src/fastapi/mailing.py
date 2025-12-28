from src.dependencies import deps_required

deps_required(
    {
        "fastapi_mail": "fastapi-mail",
    }
)

import fastapi
import fastapi_mail
import typing

from src.fastapi.config import settings


def get_connection(connection: str = "fastapi_mail") -> fastapi_mail.ConnectionConfig:
    """
    Get the connection configuration for the specified connection.

    :param connection: The name of the connection to get as defined in the project settings.
    :return: The connection configuration.
    """
    connection_config = dict(settings.MAILING[connection])
    return fastapi_mail.ConnectionConfig(**connection_config)


class MailError(fastapi.exceptions.FastAPIError):
    """Raised when an error occurs while sending a mail"""


async def send_message(
    message: fastapi_mail.MessageSchema,
    *,
    template_name: typing.Optional[str] = None,
    connection: typing.Union[fastapi_mail.ConnectionConfig, str] = "fastapi_mail",
    fail_silently: bool = False,
) -> None:
    """
    Send a fastapi_mail message using the specified connection.

    :param message: The message to send.
    :param template_name: The name of the template to use.
    :param connection: The connection configuration to use.
    :param fail_silently: Whether to raise an error if the mail fails to send.
    Ignores any exceptions raised if fail_silently is True.
    """
    if isinstance(connection, str):
        connection = get_connection(connection)
    try:
        await fastapi_mail.FastMail(connection).send_message(
            message, template_name=template_name
        )
    except Exception as exc:
        if not fail_silently:
            raise MailError(exc) from exc
    return


async def send_mail(
    subject: str,
    body: str,
    recipients: typing.List[str],
    *,
    context: typing.Optional[typing.Dict[str, typing.Any]] = None,
    template_name: typing.Optional[str] = None,
    connection: typing.Union[fastapi_mail.ConnectionConfig, str] = "fastapi_mail",
    fail_silently: bool = False,
) -> None:
    """
    Send a mail to the specified recipients.

    :param subject: The subject of the mail.
    :param body: The body of the mail.
    :param recipients: The recipients of the mail.
    :param context: Additional context for constructing the mail message.
    :param template_name: The name of the template to use.
    :param connection: The connection configuration to use.
    :param fail_silently: Whether to raise an error if the mail fails to send.
    Ignores any exceptions raised if fail_silently is True.
    """
    if context is None:
        context = dict()
    context.setdefault("subtype", "html")

    message = fastapi_mail.MessageSchema(
        subject=subject,
        recipients=recipients,
        body=body,
        **context,
    )
    await send_message(
        message,
        template_name=template_name,
        connection=connection,
        fail_silently=fail_silently,
    )
    return
