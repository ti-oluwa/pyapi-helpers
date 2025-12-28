import typing
from typing_extensions import Self, TypedDict
import logging
from sqlalchemy.ext.asyncio import AsyncSession

from src.fastapi.apps import discover_apps
from src.types import LoggerLike


class ServiceError(Exception):
    """Custom exception for service-related errors."""

    def __init__(self, message: str, service_name: str, http_status: int = 500) -> None:
        """
        Initialize the ServiceError.

        :param message: The error message.
        :param service_name: The name of the service or sub-service that caused the error.
        :param http_status: The HTTP status code associated with the error (default is 500).
        """
        super().__init__(message)
        self.service_name = service_name
        self.http_status = http_status


class ServiceStatus(TypedDict, total=True):
    """
    TypedDict for service health status.

    This dictionary contains the status of a service, including its name, current status,
    and any error message if the service is unhealthy.
    """

    name: str
    """Name of the service."""
    status: typing.Literal["healthy", "unhealthy"]
    """Current status of the service (e.g., 'healthy', 'unhealthy')."""
    error: typing.Optional[str]
    """Error message if the service is unhealthy."""


@typing.runtime_checkable
class Service(typing.Protocol):
    """
    Protocol for service classes.


    **N.B:** Always prefer raising a `ServiceError` from any exception caught during the
    service's start, stop, or health check methods.

    This ensures that the service manager can handle the error appropriately and the exception
    trace is logged properly.
    """

    name: typing.ClassVar[str]
    """Unique name of the service type."""
    id: typing.ClassVar[str]
    """Unique identifier for the service type."""

    async def start(self) -> None:
        """
        Start the service.

        :raises ServiceError: If the service fails to start properly.
        """
        pass

    async def stop(self) -> None:
        """
        Stop the service.

        :raises ServiceError: If the service fails to stop properly.
        """
        pass

    async def health_check(self, db: typing.Optional[AsyncSession]) -> ServiceStatus:
        """
        Check the health of the service.

        :param db: Optional database session for health checks that require database access.
        :return: A dictionary containing the service status.
        :raises ServiceError: If the health check fails.
        """
        return {
            "name": type(self).name,
            "status": "healthy",
            "error": None,
        }


class ServiceManager:
    """
    Manager for handling services in the application.
    """

    def __init__(self, logger: typing.Optional[LoggerLike] = None) -> None:
        """
        Initialize the service manager.

        :param logger: Optional custom logger for the service manager.
        If not provided, the default logger will be used.
        """
        if logger is None:
            self.logger = logging.getLogger(__name__)
        else:
            self.logger = logger
        self.services: typing.Dict[str, Service] = {}

    def list_services(self) -> typing.List[Service]:
        """List all registered services."""
        return list(self.services.values())

    def discover(self) -> None:
        """
        Discover and register all services defined in the `services` module
        in project apps.
        """
        seen = set()
        for app in discover_apps():
            services_module = app.services
            if services_module:
                self.logger.debug(f"Discovering services in app: {app.name}...")
                for attr_name in dir(services_module):
                    attr = getattr(services_module, attr_name)

                    if (
                        not isinstance(attr, type)
                        and isinstance(attr, Service)
                        and not attr_name.startswith("_")  # Skip private attributes
                    ):
                        if attr.id in seen:
                            continue

                        try:
                            self.register(attr)
                        except TypeError as exc:
                            self.logger.error(
                                f"Failed to register service {attr_name!r}: {exc}",
                                exc_info=True,
                            )
                        seen.add(attr.id)
            else:
                self.logger.debug(
                    f"No services found in app {app.name!r}. Skipping discovery."
                )

    def register(self, service: Service) -> None:
        """
        Register a service.

        :param service: An instance of a service that implements the Service protocol.
        """
        if not isinstance(service, Service):
            raise TypeError(
                f"Expected service to implement `Service` protocol, got {type(service)}"
            )
        self.services[service.id] = service
        self.logger.debug(f"Registered service: {service.name!r} (ID: {service.id})")

    def unregister(self, service_id: str) -> None:
        """
        Unregister a service by its ID.

        :param service_id: The unique identifier of the service to unregister.
        """
        if service_id in self.services:
            service = self.services.pop(service_id)
            self.logger.debug(
                f"Unregistered service: {service.name!r} (ID: {service.id})"
            )
        else:
            self.logger.warning(
                f"Attempted to unregister non-existent service ID: {service_id!r}"
            )

    async def start(self, *, ignore_errors: bool = False) -> None:
        """
        Start all registered services.

        :param ignore_errors: If True, errors during service start will be logged but not raised.
        """
        for service in self.services.values():
            self.logger.debug(f"Starting service: {service.name!r} (ID: {service.id})")
            try:
                await service.start()
            except ServiceError as exc:
                self.logger.error(
                    f"Failed to start service {service.name!r} (ID: {service.id}): {exc}",
                    exc_info=True,
                    extra={
                        "service_name": exc.service_name,
                        "http_status": exc.http_status,
                    },
                )
                if not ignore_errors:
                    raise

    async def stop(self, *, ignore_errors: bool = False) -> None:
        """
        Stop all registered services.

        :param ignore_errors: If True, errors during service stop will be logged but not raised.
        """
        for service in self.services.values():
            self.logger.debug(f"Stopping service: {service.name!r} (ID: {service.id})")
            try:
                await service.stop()
            except ServiceError as exc:
                self.logger.error(
                    f"Failed to stop service {service.name!r} (ID: {service.id}): {exc}",
                    exc_info=True,
                    extra={
                        "service_name": exc.service_name,
                        "http_status": exc.http_status,
                    },
                )
                if not ignore_errors:
                    raise

    async def health_check(
        self, db: typing.Optional[AsyncSession] = None
    ) -> typing.Tuple[bool, typing.Dict[str, ServiceStatus]]:
        """
        Run health checks for all registered services.

        :param db: Optional database session for health checks that require database access.
        :return: A tuple containing:
            - A boolean indicating if all services are healthy.
            - A dictionary with service names as keys and their health status as values.
        """
        health_report = {}
        all_healthy = True
        for service in self.services.values():
            try:
                status = await service.health_check(db)
                health_report[service.name] = status
                if status["status"] == "unhealthy":
                    self.logger.error(
                        f"Service {service.name!r} (ID: {service.id}) is unhealthy: {status['error']}"
                    )
                else:
                    self.logger.debug(
                        f"Service {service.name!r} (ID: {service.id}) is healthy."
                    )
            except ServiceError as exc:
                all_healthy = False
                self.logger.error(
                    f"Health check for service {service.name!r} (ID: {service.id}) failed: {exc}",
                    extra={
                        "service_name": exc.service_name,
                        "http_status": exc.http_status,
                    },
                    exc_info=True,
                )
                health_report[service.name] = {
                    "name": exc.service_name,
                    "status": "unhealthy",
                    "error": str(exc),
                }
        return all_healthy, health_report

    async def reload(self, *, ignore_errors: bool = False) -> None:
        """
        Reload all registered services.

        This method stops all services, then starts them again.

        :param ignore_errors: If True, errors during service reload will be logged but not raised.
        :raises ServiceError: If any service fails to stop or start during the reload process.
        """
        self.logger.info("Reloading all registered services...")
        await self.stop(ignore_errors=ignore_errors)
        await self.start(ignore_errors=ignore_errors)
        self.logger.info("All services reloaded successfully.")

    def get_service(self, service_id: str) -> typing.Optional[Service]:
        """Get a service by its ID."""
        return self.services.get(service_id)

    async def start_service(
        self, service_id: str, *, ignore_errors: bool = False
    ) -> None:
        """
        Start a specific service by its ID.

        :param service_id: The unique identifier of the service to start.
        :param ignore_errors: If True, errors during service start will be logged but not raised.
        """
        service = self.get_service(service_id)
        if service:
            self.logger.debug(f"Starting service: {service.name!r} (ID: {service.id})")
            try:
                await service.start()
            except ServiceError as exc:
                self.logger.error(
                    f"Failed to start service {service.name!r} (ID: {service.id}): {exc}",
                    exc_info=True,
                    extra={
                        "service_name": exc.service_name,
                        "http_status": exc.http_status,
                    },
                )
                if not ignore_errors:
                    raise
            else:
                self.logger.debug(f"Service {service.name!r} started successfully.")
        else:
            self.logger.warning(f"Service with ID {service_id!r} not found.")

    async def stop_service(
        self, service_id: str, *, ignore_errors: bool = False
    ) -> None:
        """
        Stop a specific service by its ID.

        :param service_id: The unique identifier of the service to stop.
        :param ignore_errors: If True, errors during service stop will be logged but not raised.
        """
        service = self.get_service(service_id)
        if service:
            self.logger.debug(f"Stopping service: {service.name!r} (ID: {service.id})")
            try:
                await service.stop()
            except ServiceError as exc:
                self.logger.error(
                    f"Failed to stop service {service.name!r} (ID: {service.id}): {exc}",
                    exc_info=True,
                    extra={
                        "service_name": exc.service_name,
                        "http_status": exc.http_status,
                    },
                )
                if not ignore_errors:
                    raise
            else:
                self.logger.debug(f"Service {service.name!r} stopped successfully.")
        else:
            self.logger.warning(f"Service with ID {service_id!r} not found.")

    async def reload_service(
        self, service_id: str, *, ignore_errors: bool = False
    ) -> None:
        """
        Reload a specific service by its ID.

        This method stops the service and then starts it again.

        :param service_id: The unique identifier of the service to reload.
        :param ignore_errors: If True, errors during service reload will be logged but not raised.
        """
        service = self.get_service(service_id)
        if service:
            self.logger.debug(f"Reloading service: {service.name!r} (ID: {service.id})")
            await self.stop_service(service_id, ignore_errors=ignore_errors)
            await self.start_service(service_id, ignore_errors=ignore_errors)
            self.logger.debug(f"Service {service.name!r} reloaded successfully.")
        else:
            self.logger.warning(f"Service with ID {service_id!r} not found for reload.")

    async def __aenter__(self) -> Self:
        """Enter the runtime context for the service manager."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        """Exit the runtime context for the service manager."""
        await self.stop()
        self.logger.debug("Service manager exited and all services stopped.")
