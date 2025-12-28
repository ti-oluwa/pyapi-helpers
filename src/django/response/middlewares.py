import re
import functools
from typing import Dict, Mapping, Union, Any, List
from django.utils.deprecation import MiddlewareMixin
from django.utils.module_loading import import_string
from django.http import HttpRequest, HttpResponse
from django.core.exceptions import ImproperlyConfigured

from src.django.config import settings
from .format import drf_response_formatter, Formatter
from src.logging import log_exception
from src import RESOURCES_PATH


class FormatJSONResponseMiddleware(MiddlewareMixin):
    """
    Middleware to format JSON response data to a structured and consistent format (as defined by formatter).

    In settings.py:

    ```python
    HELPERS_SETTINGS = {
        ...,
        "RESPONSE_FORMATTER": {
            "formatter": "path.to.formatter_function", # Default formatter is used if not set
            "exclude": [r"^/admin*", ...] # Routes to exclude from formatting
        }
    }
    ```
    """

    default_formatter = drf_response_formatter
    """The default response formatter."""
    setting_name = "RESPONSE_FORMATTER"
    """The name of the setting for the middleware in the helpers settings."""

    def __init__(
        self, *args, **kwargs
    ) -> None:
        super().__init__(*args, **kwargs)
        self.formatter = self.get_formatter()

    @classmethod
    @functools.cache
    def settings(cls):
        return getattr(settings, cls.setting_name)

    @classmethod
    def get_formatter(cls):
        """Return the response formatter."""
        formatter_path: str = getattr(cls.settings(), "formatter", "default")

        if formatter_path.lower() == "default":
            formatter: Formatter = cls.default_formatter
        else:
            formatter: Formatter = import_string(formatter_path)
            if not callable(formatter):
                raise TypeError("Response formatter must be a callable")

        return formatter

    def is_json_response(self, response: HttpResponse) -> bool:
        """
        Check if the response is a JSON response.

        :param response: The response object.
        :return: True if the response is a JSON response, False otherwise.
        """
        return response.get("Content-Type", "").startswith("application/json")

    def can_format(self, request: HttpRequest, response: HttpResponse) -> bool:
        """
        Check if the response can be formatted.

        :param request: The request object.
        :param response: The response object.
        :return: True if the response can be formatted, False otherwise.
        """
        if not getattr(
            self.settings(), "enforce_format", True
        ) and not self.is_json_response(response):
            return False

        excluded_paths: List[str] = getattr(self.settings(), "exclude", [])
        request_path = request.get_full_path()

        for path in excluded_paths:
            path_pattern = re.compile(path)
            if path_pattern.match(request_path):
                return False
        return True

    def format(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        """
        Format the response.

        :param request: The request object.
        :param response: The response object.
        :return: The formatted response object.
        """
        if not self.can_format(request, response):
            return response

        try:
            formatted_response = self.formatter(response)
        except Exception as exc:
            log_exception(exc)
            return response
        return formatted_response

    def pre_format(self, request: HttpRequest, response: HttpResponse) -> HttpResponse:
        """
        Should contain logic to be executed before formatting the response.
        """
        return response

    def post_format(
        self, request: HttpRequest, formatted_response: HttpResponse
    ) -> HttpResponse:
        """
        Should contain logic to be executed after formatting the response.
        """
        return formatted_response

    def process_response(
        self, request: HttpRequest, response: HttpResponse
    ) -> HttpResponse:
        response = self.pre_format(request, response)
        formatted_response = self.format(request, response)
        return self.post_format(request, formatted_response)


class MaintenanceMiddleware(MiddlewareMixin):
    """
    Middleware to handle application maintenance mode.
    The middleware will return a 503 Service Unavailable response with the maintenance message.

    #### Ensure to place this middleware at the top of `MIDDLEWARE` settings.

    Middleware settings:

    - `MAINTENANCE_MODE.status`: Set as "ON" or "OFF", True or False, to enable or disable maintenance mode.
    - `MAINTENANCE_MODE.message`: The message to display in maintenance mode. Can be a path to a template file or a string.

    There are default maintenance message templates available:

    - `default:minimal`: Minimal and clean. Light-themed
    - `default:minimal_dark`: Dark-themed minimal
    - `default:techno`: Techno-themed
    - `default:jazz`: Playful jazz-themed

    In settings.py:

    ```python
    HELPERS_SETTINGS = {
        ...,
        "MAINTENANCE_MODE": {
            "status": True,
            "message": "default:techno"
        }
    }
    ```
    """

    templates_dir = RESOURCES_PATH / "templates/maintenance"
    defaults_prefix = "default:"
    setting_name = "MAINTENANCE_MODE"

    def __init__(
        self, *args, **kwargs
    ) -> None:
        super().__init__(*args, **kwargs)
        self.settings: Mapping[str, Any] = getattr(settings, self.setting_name)

    def _maintenance_mode_on(self) -> bool:
        """Check if the application is in maintenance mode."""
        status = str(self.settings.get("status", "off"))
        return status.lower() in ["on", "true"]

    def get_message(self) -> Union[str, bytes]:
        """Return the maintenance message."""
        msg = self.settings.get("message", "default:minimal")

        if not isinstance(msg, str):
            raise ImproperlyConfigured(f"{self.setting_name}.message must be a string")

        if msg.lower().startswith(self.defaults_prefix.lower()):
            slice_start = len(self.defaults_prefix)
            template_name = msg[slice_start:]
            msg = self.get_default_template(template_name)

        return msg or "Service Unavailable"

    def get_default_template(self, name: str) -> Union[bytes, None]:
        """Get the default maintenance template content."""
        template_path = self.templates_dir / f"{name.lower()}.html"
        try:
            if template_path.exists():
                with open(template_path, "rb") as file:
                    return file.read()
        except Exception as exc:
            log_exception(exc)
        return None

    def get_response_content(self) -> Union[str, bytes]:
        """Returns the response content."""
        return self.get_message()

    def get_response_headers(self) -> Dict[str, Any]:
        """Returns the response headers."""
        return {
            "Content-Type": "text/html",
        }

    def process_request(self, request: HttpRequest) -> HttpResponse:
        """Process the request."""
        if self._maintenance_mode_on():
            content = self.get_response_content()
            headers = self.get_response_headers()
            return HttpResponse(content, status=503, headers=headers)
        return None
