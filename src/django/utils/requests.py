import re
import typing
from ipaddress import ip_address

from django.http import HttpRequest


def get_ip_address(request: HttpRequest):
    """Get the requestor's IP address form the Django request object"""
    if not hasattr(request, "META"):
        raise ValueError("Request object must have a 'META' attribute")

    ip = request.META.get("REMOTE_ADDR") or request.META.get("HTTP_X_FORWARDED_FOR")
    return ip_address(ip)


def parse_query_params_from_request(
    request: HttpRequest,
) -> typing.Dict[str, typing.Any]:
    """Parses the query parameters from a request. Returns a dictionary of the query parameters."""
    if request.method != "POST":
        return request.GET.dict()

    query_param_pattern = re.compile(
        r"&?(?P<param_name>[a-zA-Z0-9-_\s]+)=(?P<param_value>[a-zA-Z0-9-_/\?=\\\s]+)"
    )
    request_path: str = request.get_full_path()
    try:
        _, query_params_part = request_path.split("?", maxsplit=1)
        results = re.findall(query_param_pattern, query_params_part)
        if not results:
            return {}
    except ValueError:
        return {}
    return {param_name: param_value for param_name, param_value in results}
