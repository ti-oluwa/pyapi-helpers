"""
Exception Capturing API.

Use an appropriate `ExceptionCaptured` exception handler` to enable exception capture globally.
Or use the `capture.enable` decorator to enable for specific controllers only.
"""

import copy
import logging
import json
import typing
import functools
from asyncio import iscoroutinefunction
import inspect
from typing_extensions import Self, TypeAlias
from dataclasses import dataclass, field

from src.dependencies import depends_on
from src.logging import log_exception
from src.generics.utils.misc import is_iterable, is_exception_class, is_mapping
from src.types import Function, CoroutineFunction, LoggerLike, P, R

# Why this you say? I'm just too lazy to catch exceptions myself. I know. Its overkill.


JSON_CONTENT_TYPE = "application/json"
TEXT_PREFIX = "text/"
JSON_SUFFIX = "+json"


@functools.lru_cache(maxsize=32)
def is_text_content_type(content_type: str) -> bool:
    """Return True if the content type is a text content type. Otherwise, False."""
    return (
        content_type.startswith(TEXT_PREFIX)
        or content_type == JSON_CONTENT_TYPE
        or content_type.endswith(JSON_SUFFIX)
    )


@functools.lru_cache(maxsize=32)
def is_json_content_type(content_type: str) -> bool:
    """Return True if the content type is a JSON content type. Otherwise, False."""
    return content_type == JSON_CONTENT_TYPE


class Response(typing.Protocol):
    """
    Protocol defining a generic interface for a HTTP response.
    """

    status_code: int
    headers: typing.Any
    body: typing.Any


ResponseT = typing.TypeVar("ResponseT", bound=Response, covariant=True)
ControllerFunc = typing.Union[Function[P, ResponseT], CoroutineFunction[P, ResponseT]]
ExceptionT = typing.TypeVar("ExceptionT", bound=BaseException, contravariant=True)


class DjangoControllerClass(typing.Generic[ResponseT], typing.Protocol):
    http_method_names: list[str]

    @classmethod
    def as_view(cls, **initkwargs: typing.Any) -> typing.Callable[..., ResponseT]: ...
    def setup(self, *args: typing.Any, **kwargs: typing.Any) -> None: ...
    def dispatch(self, *args: typing.Any, **kwargs: typing.Any) -> ResponseT: ...
    def http_method_not_allowed(
        self, *args: typing.Any, **kwargs: typing.Any
    ) -> ResponseT: ...
    def options(self, *args: typing.Any, **kwargs: typing.Any) -> ResponseT: ...


class ControllerContextDecorator(typing.Generic[ExceptionT, ResponseT]):
    """
    Context decorator interface.

    Can be used as a regular sync/async context manager,
    and as a decorator on request handlers/controllers.

    Works with both sync and async controllers.
    """

    @typing.overload
    def __call__(
        self, controller: typing.Type[DjangoControllerClass[ResponseT]]
    ) -> typing.Type[DjangoControllerClass[ResponseT]]: ...

    @typing.overload
    def __call__(
        self, controller: ControllerFunc[P, ResponseT]
    ) -> ControllerFunc[P, ResponseT]: ...

    @typing.overload
    def __call__(self) -> Self: ...

    def __call__(
        self,
        controller: typing.Optional[
            typing.Union[
                typing.Type[DjangoControllerClass[ResponseT]],
                ControllerFunc[P, ResponseT],
            ]
        ] = None,
    ) -> typing.Union[
        typing.Type[DjangoControllerClass[ResponseT]],
        ControllerFunc[P, ResponseT],
        Self,
    ]:
        """
        Allows usage as a decorator.

        If a controller is provided, it decorates the controller.
        Else, returns the instance for reuse.

        :param controller: The controller to decorate
        :return: The decorated controller or the instance
        """
        if controller is None:
            return self

        if inspect.isclass(controller):
            return self.decorate_controller_cls(controller)
        return self.decorate_controller_func(controller)

    def decorate_controller_cls(
        self, controller_cls: typing.Type[DjangoControllerClass[ResponseT]]
    ) -> typing.Type[DjangoControllerClass[ResponseT]]:
        """Decorate class-based controller."""
        if not hasattr(controller_cls, "http_method_names"):
            return controller_cls

        for method_name in controller_cls.http_method_names:
            method_name = method_name.lower()
            handler: typing.Optional[ControllerFunc] = getattr(
                controller_cls, method_name, None
            )
            if not handler or not callable(handler):
                continue
            setattr(controller_cls, method_name, self.decorate_controller_func(handler))
        return controller_cls

    def decorate_controller_func(
        self, controller_func: ControllerFunc[P, ResponseT]
    ) -> ControllerFunc[P, ResponseT]:
        """Decorate function-based controller."""
        wrapper = None
        if iscoroutinefunction(controller_func):

            @functools.wraps(controller_func)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> ResponseT:
                async with self:
                    return await controller_func(*args, **kwargs)

            wrapper = async_wrapper
        else:

            @functools.wraps(controller_func)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> ResponseT:
                with self:
                    return controller_func(*args, **kwargs)  # type: ignore

            wrapper = sync_wrapper

        return wrapper

    @classmethod
    @depends_on({"asgiref": "asgiref"})
    async def run_async(
        cls, sync_func: Function[P, R], *args: P.args, **kwargs: P.kwargs
    ) -> R:
        """
        Run a synchronous function asynchronously.

        :param sync_func: The synchronous function to run asynchronously
        :param args: The positional arguments to pass to the function
        :param kwargs: The keyword arguments to pass to the function
        """
        from asgiref.sync import sync_to_async  # type: ignore[import]

        return await sync_to_async(sync_func, thread_sensitive=True)(*args, **kwargs)

    def __enter__(self) -> typing.Any:
        raise NotImplementedError("Subclasses must implement this method")

    def __exit__(
        self, exc_type: typing.Type[ExceptionT], exc_value: ExceptionT, traceback
    ) -> bool:
        raise NotImplementedError("Subclasses must implement this method")

    async def __aenter__(self) -> typing.Any:
        return await self.run_async(self.__enter__)

    async def __aexit__(
        self, exc_type: typing.Type[ExceptionT], exc_value: ExceptionT, traceback
    ) -> bool:
        return await self.run_async(self.__exit__, exc_type, exc_value, traceback)


Rco = typing.TypeVar("Rco", covariant=True)


class ExceptionCallback(typing.Generic[ExceptionT, P, Rco], typing.Protocol):
    """Protocol defining the interface for exception callbacks"""

    def __call__(
        self, exc: ExceptionT, *args: P.args, **kwargs: P.kwargs
    ) -> typing.Union[Rco, typing.Awaitable[Rco]]: ...


ExceptionDetailHook: TypeAlias = typing.Callable[[ExceptionT], typing.Any]
"""Hook to get the detail of an exception for the response."""


@functools.total_ordering
@dataclass(frozen=True)  # Ensure immutability due to ordering and caching
class PrioritizedCallback(typing.Generic[ExceptionT, P, R]):
    """Callback with priority and instance-specific order tracking"""

    callback: ExceptionCallback[ExceptionT, P, R]
    priority: typing.Union[int, float] = 0
    args: typing.Tuple[typing.Any, ...] = field(default_factory=tuple)
    kwargs: typing.Dict[str, typing.Any] = field(default_factory=dict)
    # Track order within specific captor instance
    _order: int = field(default=0)

    def __call__(
        self, exc: ExceptionT, **kwargs: typing.Any
    ) -> typing.Union[R, typing.Awaitable[R]]:
        return self.callback(exc, *self.args, **{**self.kwargs, **kwargs})

    def __lt__(self, other: typing.Any) -> bool:
        if not isinstance(other, PrioritizedCallback):
            return NotImplemented
        return (-self.priority, self._order) < (-other.priority, other._order)

    @functools.cached_property
    def is_async(self):
        """Return True if the callback is an async type. Otherwise, False."""
        return iscoroutinefunction(self.callback)


def merge_json_content_with_exception_detail(
    content: typing.Any,
    exc_detail: typing.Any,
    prioritize_content: bool,
    is_special_exception: bool,
) -> typing.Any:
    """
    Compare the content with the exception detail, merging them into a single JSON serializable content.

    :param content: The content defined to be returned in the response
    :param exc_detail: The detail of the exception
    :param prioritize_content: Whether to prioritize the defined content over the exception detail when merging them.
    :param is_special_exception: Whether the exception is to be treated with preference.
    """
    priority = content if prioritize_content else exc_detail
    non_priority = exc_detail if prioritize_content else content
    if not priority:
        return {"detail": non_priority}

    if is_mapping(priority):
        if not is_mapping(non_priority):
            non_priority = {"detail": non_priority}
        return {**non_priority, **priority}

    elif is_iterable(priority, exclude=(str, bytes)):
        if is_iterable(non_priority, exclude=(str, bytes)):
            return {"detail": list(set([*non_priority, *priority]))}
        else:
            if not is_mapping(non_priority):
                non_priority = {"detail": non_priority}
            return {**non_priority, "detail": priority}

    elif isinstance(priority, str):
        if isinstance(non_priority, str):
            return {"detail": f"{priority}. {non_priority}"}
        elif is_mapping(non_priority):
            return {**non_priority, "detail": priority}
        elif is_iterable(non_priority, exclude=(str, bytes)):
            return {"detail": list(set([*non_priority, priority]))}
        else:
            return {"detail": priority}

    # If the priority is not a string, list or dict
    # negate the main context, that is, the priority
    # becomes non-priority and vice versa, and negate
    # the `prioritize_content` flag.
    json_content = merge_json_content_with_exception_detail(
        priority,
        non_priority,
        prioritize_content=not prioritize_content,
        is_special_exception=is_special_exception,
    )
    if is_special_exception:
        json_content = {**json_content, "detail": exc_detail}
    return json_content


CAPTURE_ENABLED_ATTR = "__capture_enabled"
WRAPPED_CONTROLLER_ATTR = "wrapped_controller"


class ExceptionCaptor(ControllerContextDecorator[ExceptionT, ResponseT]):
    """
    Captures and constructs a structured error response from exceptions.

    Ensure you have enabled the capture API for the controller using the `enable` decorator.
    Or globally, using an exception handler for `ExceptionCaptured` exceptions.

    Example:
    ```python
    from src.generics.exceptions import capture

    @capture.enable # Enable the exception capture API for the controller only
    def controller(*args, **kwargs):
        ...
        with capture.ExceptionCaptor(
            ValueError,
            content={"message": "Unexpected value"},
            code=422
        ) as captor:
            captor.add_callback(lambda exc: print(exc))
            raise ValueError(...)
        ...
    ```

    Or;
    ```python

    @capture.enable # or use the `exception_captured_handler` globally
    @capture.capture(
        (ValueError, KeyError),
        content="Invalid value",
        prioritize_content=True,
        code=400
    )
    async def controller(*args, **kwargs):
        key = kwargs["key"]
        if condition:
            raise ValueError(...)
    ```
    """

    EXCEPTION_CODES: typing.Mapping[typing.Type[BaseException], int] = {}
    """
    A mapping of special exceptions to the preferred status codes to be used for them
    when constructing response.
    """
    DEFAULT_RESPONSE_TYPE: typing.Optional[typing.Type[ResponseT]] = None
    """
    The default response type/class to use to construct the response.

    Make sure to set this to an appropriate response class before instantiation.
    Else, provide the `response_type` argument on instantiation.
    """
    CONTENT_TYPE_KWARG: str = "content_type"
    """
    The name of the keyword argument that represents the content type in the response constructor.
    """
    DEFAULT_CONTENT_TYPE: str = "application/json"
    """
    The default content type to use when constructing the response.

    Override this by providing the `response_kwargs["content_type"]` argument on instantiation.
    """
    STATUS_CODE_KWARG: str = "status_code"
    """
    The name of the keyword argument that represents the status code in the response constructor.
    """
    DEFAULT_STATUS_CODE: int = 500
    """
    The default status code to use when constructing the response.

    Override this by providing the `code` argument on instantiation.
    """

    @typing.final
    class ExceptionCaptured(Exception, typing.Generic[ExceptionT, ResponseT]):  # type: ignore
        """Raised when an exception is captured by an ExceptionCaptor instance."""

        __outer__ = None

        def __init__(
            self,
            captive: ExceptionT,
            captor: "ExceptionCaptor[ExceptionT, ResponseT]",
            response_getter: typing.Callable[
                [ExceptionT, "ExceptionCaptor[ExceptionT, ResponseT]"], ResponseT
            ],
        ) -> None:
            """
            Initialize the ExceptionCaptured instance.

            :param captive: The captured exception
            :param captor: The ExceptionCaptor instance that captured the exception
            :param response_getter: A callable that takes the captured exception and the captor,
                and returns the response to be returned.
            """
            super().__init__(captive)
            self.captive = captive
            self.get_response = response_getter
            self.captor = captor

        # This ensures lazy evaluation of the response.
        # Response is constructed only when accessed
        @functools.cached_property
        def response(self) -> ResponseT:
            """The response constructed from the captured exception."""
            return self.get_response(self.captive, self.captor)

    def __init__(
        self,
        target: typing.Optional[
            typing.Union[
                typing.Type[ExceptionT],
                typing.Tuple[typing.Type[ExceptionT], ...],
            ]
        ] = None,
        content: typing.Optional[typing.Any] = None,
        *,
        code: typing.Optional[int] = None,
        response_type: typing.Optional[typing.Type[ResponseT]] = None,
        response_kwargs: typing.Optional[typing.MutableMapping[str, typing.Any]] = None,
        prioritize_content: bool = False,
        exc_detail: typing.Optional[
            typing.Union[ExceptionDetailHook[ExceptionT], typing.Any]
        ] = None,
        callback: typing.Optional[
            typing.Union[
                ExceptionCallback[ExceptionT, P, R],
                PrioritizedCallback[ExceptionT, P, R],
            ]
        ] = None,
        log_errors: bool = True,
        logger: typing.Optional[typing.Union[str, LoggerLike]] = None,
        log_context: typing.Optional[typing.Dict[str, typing.Any]] = None,
        log_error_code_threshold: int = 500,
    ) -> None:
        """
        Initialize the `ExceptionCaptor` instance.

        :param target: Type of exception(s) to capture. Defaults to `BaseException`
        :param content: The content or message to be returned in the response. If not provided,
            exception detail will be used. This can also be a callable that will take the exception captured,
            process the result and return appropriate content to be returned in the response
        :param code: The status code of the response. Defaults to 500
        :param response_type: Type of response to return. Defaults to `HttpResponse`
        :param response_kwargs: Keyword arguments to pass on to the response constructor.
        :param prioritize_content: Whether to prioritize the content over the exception detail.
            By default, the exception detail takes precedence over the content.
        :param exc_detail: The detail of the exception to be used in the response, or a hook (callable)
            that takes the exception and returns the detail to be used in the response. e.g `exc_detail=str`,
            This returns the string representation of the exception. If None, the exception's `detail` attribute
            will be used if it exists. Defaults to None.
        :param callback: A callback to be called on exception capture. Should take the exception as an argument.
            By default, callback added on instantiation will have the highest priority, no matter the order of addition.
            However, the callback this can be circumvented by providing an already created `PrioritizedCallback` instance.
        :param log_errors: Whether to log critical exceptions (like server errors) or errors during captured
            exception processing. Defaults to True.
        :param logger: The logger to use for logging exceptions. Defaults to the module logger.
        :param log_context: Additional keyword arguments to be passed to the logger when logging exceptions.
        :param log_error_code_threshold: The minimum status code threshold for logging errors.
            If the status code of the response is greater than or equal to this threshold, the error will be logged.
        """
        target_exceptions = target or (BaseException,)
        if not is_iterable(target_exceptions):
            target_exceptions = (target_exceptions,)

        for exc_class in target_exceptions:
            if not is_exception_class(exc_class):
                raise ValueError("target should only hold exception classes")

        self.target = tuple(target_exceptions)
        self.content = content
        self.prioritize_content = prioritize_content
        self.get_exc_detail = (
            exc_detail if callable(exc_detail) else lambda exc: exc_detail
        )
        self.code = code or self.DEFAULT_STATUS_CODE

        self.response_type = response_type or self.DEFAULT_RESPONSE_TYPE
        if self.response_type is None:
            raise ValueError(
                "`response_type` must be provided if DEFAULT_RESPONSE_TYPE is not set"
            )

        response_kwargs = response_kwargs or {}
        response_kwargs.setdefault(self.CONTENT_TYPE_KWARG, self.DEFAULT_CONTENT_TYPE)
        self.response_kwargs = response_kwargs
        self._callback_counter: int = 0
        self.callbacks: typing.List[PrioritizedCallback] = []
        if callback:
            # Callback added on instantiation should have the highest priority
            self.add_callback(callback, priority=float("inf"))
        self.log_errors = log_errors
        self.logger = (
            logging.getLogger(logger or __name__) if isinstance(logger, str) else logger
        )
        self.log_context = log_context or {}
        if log_error_code_threshold < 400:
            raise ValueError(
                "`log_error_code_threshold` must be at least 400, "
                "as it is used to determine whether to log errors or not."
            )
        self.log_error_code_threshold = log_error_code_threshold
        self._init_args = ()
        self._init_kwargs = {}

    def __new__(cls, *args, **kwargs):
        instance = super().__new__(cls)
        instance._init_args = args
        instance._init_kwargs = kwargs
        return instance

    def _next_callback_order(self) -> int:
        """Get next callback order for this instance"""
        self._callback_counter += 1
        return self._callback_counter

    def __repr__(self) -> str:
        return f"{type(self).__name__}(target={self.target}, code={self.code})"

    def __copy__(self) -> Self:
        args = self._init_args
        kwargs = self._init_kwargs.copy()
        kwargs.pop("callback", None)
        copy = type(self)(*args, **kwargs)

        # Using `copy.callbacks.append(callback)` will lead to shared
        # callbacks state between instances. Hence, we add callbacks
        # to the new instance in the same order as the original instance.
        # This would create new priority callbacks for the new instance.
        # in the same order as they were added to the original instance.
        for callback in sorted(self.callbacks):
            copy.add_callback(callback)
        return copy

    def verify_target(self, exc_type: typing.Type[ExceptionT]) -> bool:
        """Returns True if the exception type is of the target type(s). Otherwise, False."""
        return issubclass(exc_type, self.target) and not issubclass(
            exc_type, self.ExceptionCaptured
        )

    def get_exception_detail(self, exc: ExceptionT) -> typing.Any:
        """Returns the detail of the exception."""
        return self.get_exc_detail(exc) or getattr(exc, "detail", None)

    def prepare_response_content(self, exc: ExceptionT) -> typing.Any:
        """Prepare and returns the content of the error response."""
        content = self.content
        if callable(content):
            content = content(exc)

        exc_detail = self.get_exception_detail(exc)
        special_exceptions = tuple(self.EXCEPTION_CODES.keys())
        is_special_exception = isinstance(exc, special_exceptions)

        content_type = self.response_kwargs.get(
            self.CONTENT_TYPE_KWARG, self.DEFAULT_CONTENT_TYPE
        )
        if is_json_content_type(content_type):
            content = merge_json_content_with_exception_detail(
                content,
                exc_detail,
                prioritize_content=self.prioritize_content,
                is_special_exception=is_special_exception,
            )
            content = json.dumps(content)
        else:
            if self.prioritize_content:
                content = content or exc_detail
            else:
                if is_special_exception:
                    content = exc_detail
                else:
                    content = exc_detail or content

            if is_text_content_type(content_type):
                content = str(content)
        return content

    def get_exception_status_code(self, exc: ExceptionT) -> int:
        """Returns the appropriate response status code for the exception."""
        # If the exception was explicitly defined in `target`,
        # return the status code defined in the instance
        if type(exc) in self.target:
            return self.code

        # If a status code was defined in `EXCEPTION_CODES`
        # for the exception type, return the status code
        for exc_class, code in self.EXCEPTION_CODES.items():
            if isinstance(exc, exc_class):
                return int(code)
        else:
            code = self.code
            try:
                if status_code := getattr(exc, "status_code", None):
                    code = int(status_code)  # type: ignore[index]
                elif exc_code := getattr(exc, "code", None):
                    code = int(exc_code)  # type: ignore[index]
            except (ValueError, TypeError):
                # If the status code is not an integer or cannot be converted to an integer,
                # we will use the default status code defined in the instance.
                pass
        return code

    def prepare_response_kwargs(self, exc: ExceptionT) -> typing.Dict[str, typing.Any]:
        """Prepares and returns the keyword arguments for the response constructor."""
        kwargs = copy.copy(self.response_kwargs)
        headers = kwargs.get("headers", {})
        if headers and "Content-Type" in headers:
            # Header's "Content-Type" takes precedence over `CONTENT_TYPE_KWARG`
            kwargs.pop(self.CONTENT_TYPE_KWARG, None)
            kwargs["headers"] = headers

        status_code = self.get_exception_status_code(exc)
        return {**kwargs, self.STATUS_CODE_KWARG: status_code}

    def construct_response(self, exc: ExceptionT) -> ResponseT:
        """Construct the response to be returned."""
        content = self.prepare_response_content(exc)
        kwargs = self.prepare_response_kwargs(exc)
        return self.response_type(content, **kwargs)  # type: ignore

    @staticmethod
    def get_response(
        exc: ExceptionT, captor: "ExceptionCaptor[ExceptionT, ResponseT]"
    ) -> ResponseT:
        """
        Get the response from the exception and captor.

        This is a static method to allow access to the response
        from the `ExceptionCaptured` exception.
        """
        response = captor.construct_response(exc)
        if response.status_code >= captor.log_error_code_threshold and captor.log_errors:
            log_exception(exc, logger=captor.logger, **captor.log_context)
        return response

    def raise_exception_captured(self, exc: ExceptionT) -> typing.NoReturn:
        """Re-raise the captured exception as an `ExceptionCaptured` exception."""
        raise type(self).ExceptionCaptured(
            captive=exc,
            captor=self,
            response_getter=self.get_response,
        ) from exc  # Preserve exception context for easier debugging

    @typing.overload
    def add_callback(
        self,
        callback: ExceptionCallback[ExceptionT, P, R],
        priority: typing.Union[int, float] = 0,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None: ...

    @typing.overload
    def add_callback(
        self,
        callback: PrioritizedCallback[ExceptionT, P, R],
        priority: typing.Union[int, float] = 0,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None: ...

    # Sorting the callbacks by priority should be done on execution
    # to avoid unnecessary sorting on every callback addition, leading
    # to an O(n log n) complexity on every addition.
    def add_callback(
        self,
        callback: typing.Union[
            ExceptionCallback[ExceptionT, P, R],
            PrioritizedCallback[ExceptionT, P, R],
        ],
        priority: typing.Union[int, float] = 0,
        *args: typing.Any,
        **kwargs: typing.Any,
    ) -> None:
        """
        Add callbacks to be called on exception capture.

        Provides an opportunity to add clean-up logic in the event of an exception capture,
        or any additional processing that should be done.

        :param callback: The callback to be called
        :param priority: Priority of callback execution (higher runs first)
        :param args: The positional arguments to pass to the exception callback alongside the exception captured.
        :param kwargs: The keyword arguments to pass to the exception callback alongside the exception captured.

        Example:
        ```python

        @capture.enable
        def controller(*args, **kwargs):
            with capture(ValueError) as captor:
                # Lower priority callback runs second, although added first
                captor.add_callback(log_error, priority=50)
                # High priority callback runs first
                captor.add_callback(cleanup, priority=100)
                raise ValueError("test")
            ...
        ```
        """
        if not isinstance(callback, PrioritizedCallback):
            callback = PrioritizedCallback(
                callback=callback,
                priority=priority,
                args=args,
                kwargs=kwargs,
                _order=self._next_callback_order(),
            )
        else:
            # If it's already a PrioritizedCallback, reassign order for this instance
            callback = PrioritizedCallback(
                callback=callback.callback,
                priority=callback.priority,
                args=callback.args,
                kwargs=callback.kwargs,
                _order=self._next_callback_order(),
            )

        self.callbacks.append(callback)
        return None

    def execute_callbacks(self, exc: ExceptionT) -> None:
        """Execute callbacks in priority order"""
        for callback in sorted(self.callbacks):
            try:
                if callback.is_async:
                    # Skip async callbacks with a warning.
                    # Run async callbacks only in async contexts.
                    # Doing so in a sync context would lead to unexpected behavior.
                    if self.log_errors and self.logger:
                        self.logger.warning(
                            f"Skipping async callback {callback.callback!r} "
                            f"in sync context. Use sync callbacks for sync contexts."
                        )
                    continue
                else:
                    callback(exc)
            except Exception as e:
                if self.log_errors:
                    log_exception(e, logger=self.logger, **self.log_context)
                pass
        return

    async def async_execute_callbacks(self, exc: ExceptionT) -> None:
        """Execute callbacks in priority order"""
        for callback in sorted(self.callbacks):
            try:
                if callback.is_async:
                    await callback(exc)
                else:
                    callback(exc)
            except Exception as e:
                if self.log_errors:
                    await self.run_async(
                        log_exception, e, logger=self.logger, **self.log_context
                    )
                pass
        return

    def __enter__(self):
        if not self.response_type:
            raise RuntimeError(
                "response_type must be set before using as context manager"
            )
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type and self.verify_target(exc_type):
            self.execute_callbacks(exc_value)
            self.raise_exception_captured(exc_value)
        # Raise the exception if it is not of the target type(s)
        return False

    async def __aenter__(self):
        return self.__enter__()

    async def __aexit__(self, exc_type, exc_value, traceback):
        if exc_type and self.verify_target(exc_type):
            await self.async_execute_callbacks(exc_value)
            self.raise_exception_captured(exc_value)
        # Raise the exception if it is not of the target type(s)
        return False

    def decorate_controller_func(
        self, controller_func: ControllerFunc[P, ResponseT]
    ) -> ControllerFunc[P, ResponseT]:
        # If the controller has been enabled for capture,
        # that means it has already been decorated
        # by the `enable` decorator, and is wrapped.
        # Hence, we decorate the wrapped controller instead
        if getattr(controller_func, CAPTURE_ENABLED_ATTR, False):
            wrapped_controller = getattr(controller_func, WRAPPED_CONTROLLER_ATTR)
            setattr(controller_func, WRAPPED_CONTROLLER_ATTR, self(wrapped_controller))
            return controller_func
        return super().decorate_controller_func(controller_func)

    @typing.overload
    @classmethod
    def enable(
        cls,
        controller: typing.Type[DjangoControllerClass[ResponseT]],
    ) -> typing.Type[DjangoControllerClass[ResponseT]]: ...

    @typing.overload
    @classmethod
    def enable(
        cls,
        controller: ControllerFunc[P, ResponseT],
    ) -> ControllerFunc[P, ResponseT]: ...

    @classmethod
    def enable(
        cls,
        controller: typing.Union[
            typing.Type[DjangoControllerClass[ResponseT]],
            ControllerFunc[P, ResponseT],
        ],
    ) -> typing.Union[
        typing.Type[DjangoControllerClass[ResponseT]],
        ControllerFunc[P, ResponseT],
    ]:
        """
        Enables the exception capture API on the decorated controller.

        Example:
        ```python
        @capture.enable
        def controller(request, *args, **kwargs):
            ...
            with capture.capture(ValueError, code=400) as captor:
                raise ValueError("Invalid value")
            ...
        ```

        Or;
        ```python
        @capture.capture(...)
        @capture.enable
        class MyController(BaseController):
            ...
        ```
        """
        if getattr(controller, CAPTURE_ENABLED_ATTR, False):
            return controller

        if inspect.isclass(controller):
            for method_name in controller.http_method_names:
                method_name = method_name.lower()
                method = getattr(controller, method_name, None)
                if not method:
                    continue
                setattr(controller, method_name, enable(method))
            return controller

        wrapper = None
        if iscoroutinefunction(controller):

            @functools.wraps(controller)
            async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> ResponseT:
                try:
                    return await getattr(wrapper, WRAPPED_CONTROLLER_ATTR)(
                        *args, **kwargs
                    )
                except cls.ExceptionCaptured as exc:
                    return exc.response

            wrapper = async_wrapper
        else:

            @functools.wraps(controller)
            def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> ResponseT:
                try:
                    return getattr(wrapper, WRAPPED_CONTROLLER_ATTR)(*args, **kwargs)
                except cls.ExceptionCaptured as exc:
                    return exc.response

            wrapper = sync_wrapper

        setattr(wrapper, CAPTURE_ENABLED_ATTR, True)
        setattr(wrapper, WRAPPED_CONTROLLER_ATTR, controller)
        return wrapper


####### EXPORT ALIASES #######
capture = ExceptionCaptor
enable = ExceptionCaptor.enable


__all__ = [
    "ControllerContextDecorator",
    "ExceptionCaptor",
    "capture",
    "enable",
    "ExceptionCallback",
    "PrioritizedCallback",
]
