import typing
from starlette.requests import HTTPConnection
import ipaddress


def get_ip_address(
    connection: HTTPConnection,
) -> typing.Optional[typing.Union[ipaddress.IPv4Address, ipaddress.IPv6Address]]:
    """
    Returns the IP address of the connection client.

    :param connection: The HTTP connection
    """
    x_forwarded_for = connection.headers.get(
        "x-forwarded-for"
    ) or connection.headers.get("remote-addr")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0]
    else:
        ip = connection.client.host if connection.client else None
    if not ip:
        return None
    return ipaddress.ip_address(ip)
