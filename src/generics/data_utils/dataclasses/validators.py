import inspect
import typing
import operator
import re

from src.types import SupportsRichComparison
from .exceptions import FieldValidationError

typing.Sized

_Validator: typing.TypeAlias = typing.Callable[
    [
        typing.Any,
        typing.Optional[typing.Any],
        typing.Optional[typing.Any],
    ],
    None,
]

Bound = SupportsRichComparison
ComparableValue = SupportsRichComparison
CountableValue = typing.Sized


class FieldValidator(typing.NamedTuple):
    func: _Validator
    message: typing.Optional[str] = None

    @property
    def name(self) -> str:
        return self.func.__name__

    def __call__(
        self,
        value: typing.Any,
        field: typing.Optional[typing.Any] = None,
        instance: typing.Optional[typing.Any] = None,
    ):
        try:
            self.func(value, field, instance)
        except (ValueError, TypeError) as exc:
            msg = self.message or str(exc)
            name = field.effective_name if field else "value"
            raise FieldValidationError(
                msg.format_map(
                    {
                        "name": field.effective_name if field else "value",
                        "value": value,
                        "field": field,
                    }
                ),
                name,
                value,
            ) from exc

    def __hash__(self) -> int:
        try:
            return hash(self.func)
        except TypeError:
            return hash(id(self.func))


def load_validators(
    *validators: _Validator,
) -> typing.Set[FieldValidator]:
    """Load the field validators into preferred internal type."""
    loaded_validators: typing.Set[FieldValidator] = set()
    for validator in validators:
        if isinstance(validator, FieldValidator):
            loaded_validators.add(validator)
            continue

        if not callable(validator):
            raise TypeError(f"Field validator '{validator}' is not callable.")

        loaded_validators.add(FieldValidator(validator))
    return loaded_validators


def pipe(
    *validators: typing.Union[_Validator, FieldValidator],
) -> FieldValidator:
    """
    A function that takes a list of validators and returns a single validator
    that applies all the validators in sequence.

    :param validators: A list of validator functions
    :return: A single validator function
    """
    if not validators:
        raise ValueError("At least one validator must be provided.")

    loaded_validators = load_validators(*validators)

    def validation_pipeline(
        value: typing.Any,
        field: typing.Optional[typing.Any] = None,
        instance: typing.Optional[typing.Any] = None,
    ):
        nonlocal loaded_validators

        for validator in loaded_validators:
            validator(value, field, instance)

    validation_pipeline.__name__ = f"pipe({[v.name for v in loaded_validators]})"
    return FieldValidator(validation_pipeline)


_NUMBER_VALIDATION_FAILURE_MESSAGE = (
    "'{value} {symbol} {bound}' is not True for {name!r}"
)


def number_validator_factory(
    comparison_func: typing.Callable[[ComparableValue, Bound], bool],
    symbol: str,
):
    """
    Builds a validator that performs a number comparison.

    :param comparison_func: The comparison function to use
    :param symbol: The symbol to use in the error message
    :return: A validator function
    """

    def validator_factory(
        bound: Bound,
        message: typing.Optional[str] = None,
        pre_validation_hook: typing.Optional[
            typing.Callable[[typing.Any], ComparableValue]
        ] = None,
    ) -> FieldValidator:
        global _NUMBER_VALIDATION_FAILURE_MESSAGE

        msg = message or _NUMBER_VALIDATION_FAILURE_MESSAGE

        def validator(
            value: typing.Any,
            field: typing.Optional[typing.Any] = None,
            instance: typing.Optional[typing.Any] = None,
        ):
            nonlocal msg

            if pre_validation_hook:
                value = pre_validation_hook(value)
            if comparison_func(value, bound):
                return

            name = field.effective_name if field else "value"
            raise ValueError(
                msg.format_map(
                    {
                        "value": value,
                        "symbol": symbol,
                        "bound": bound,
                        "name": name,
                        "field": field,
                    }
                ),
                name,
                value,
                bound,
                symbol,
            )

        validator.__name__ = f"value_{symbol}_{bound}"
        return FieldValidator(validator)

    validator_factory.__name__ = f"value_{symbol}_validator_factory"
    return validator_factory


gte = number_validator_factory(operator.ge, ">=")
lte = number_validator_factory(operator.le, "<=")
gt = number_validator_factory(operator.gt, ">")
lt = number_validator_factory(operator.lt, "<")
eq = number_validator_factory(operator.eq, "=")


def number_range(
    min_val: SupportsRichComparison,
    max_val: SupportsRichComparison,
    message: typing.Optional[str] = None,
    pre_validation_hook: typing.Optional[
        typing.Callable[[typing.Any], ComparableValue]
    ] = None,
) -> FieldValidator:
    """
    Number range validator.

    :param min_val: Minimum allowed value
    :param max_val: Maximum allowed value
    :param message: Error message template
    :param pre_validation_hook: A function to preprocess the value before validation
    :return: A validator function
    :raises ValueError: If the value is not within the specified range
    """
    msg = message or "'{name}' must be between {min} and {max}"

    def validator(
        value: typing.Any,
        field: typing.Optional[typing.Any] = None,
        instance: typing.Optional[typing.Any] = None,
    ):
        nonlocal msg
        if pre_validation_hook:
            value = pre_validation_hook(value)
        if value < min_val or value > max_val:
            name = field.effective_name if field else "value"
            raise ValueError(
                msg.format(name=name, min=min_val, max=max_val),
                name,
                value,
                min_val,
                max_val,
            )

    validator.__name__ = f"value_between_{min_val}_{max_val}"
    return FieldValidator(validator)


_LENGTH_VALIDATION_FAILURE_MESSAGE = (
    "'len({name}) {symbol} {bound}' is not True, got {length}"
)


def length_validator_factory(
    comparison_func: typing.Callable[[int, Bound], bool], symbol: str
):
    def validator_factory(
        bound: Bound,
        message: typing.Optional[str] = None,
        pre_validation_hook: typing.Optional[
            typing.Callable[[typing.Any], CountableValue]
        ] = None,
    ) -> FieldValidator:
        global _LENGTH_VALIDATION_FAILURE_MESSAGE

        msg = message or _LENGTH_VALIDATION_FAILURE_MESSAGE

        def validator(
            value: typing.Union[CountableValue, typing.Any],
            field: typing.Optional[typing.Any] = None,
            instance: typing.Optional[typing.Any] = None,
        ) -> None:
            nonlocal msg

            if pre_validation_hook:
                value = pre_validation_hook(value)
            if comparison_func(len(value), bound):
                return
            name = field.effective_name if field else "value"
            length = len(value)
            raise ValueError(
                msg.format_map(
                    {
                        "name": name,
                        "field": name,
                        "symbol": symbol,
                        "bound": bound,
                        "value": value,
                        "length": length,
                    }
                ),
                name,
                value,
                bound,
                symbol,
                length,
            )

        validator.__name__ = f"value_length_{symbol}_{bound}"
        return FieldValidator(validator)

    validator_factory.__name__ = f"value_length_{symbol}_validator_factory"
    return validator_factory


min_len = length_validator_factory(operator.ge, ">=")
max_len = length_validator_factory(operator.le, "<=")
len_ = length_validator_factory(operator.eq, "=")


_NO_MATCH_MESSAGE = "'{name}' must match pattern {pattern!r} ({value!r} doesn't)"


def pattern(
    regex: typing.Union[re.Pattern, typing.AnyStr],
    flags: typing.Union[re.RegexFlag, typing.Literal[0]] = 0,
    func: typing.Optional[typing.Callable] = None,
    message: typing.Optional[str] = None,
    pre_validation_hook: typing.Optional[
        typing.Callable[[typing.Any], typing.Any]
    ] = None,
):
    r"""
    A validator that raises `ValueError` if the initializer is called with a
    string that doesn't match *regex*.

    :param regex: A regex string or precompiled pattern to match against
    :param message: Error message template
    :param flags: Flags that will be passed to the underlying re function (default 0)
    :param func: Which underlying `re` function to call. Valid options are
        `re.fullmatch`, `re.search`, and `re.match`; the default `None`
        means `re.fullmatch`. For performance reasons, the pattern is
        always precompiled using `re.compile`.
    :param pre_validation_hook: A function to preprocess the value before matching
    :return: A validator function
    :raises ValueError: If the value does not match the regex
    """
    global _NO_MATCH_MESSAGE

    valid_funcs = (re.fullmatch, None, re.search, re.match)
    if func not in valid_funcs:
        msg = "'func' must be one of {}.".format(
            ", ".join(sorted((e and e.__name__) or "None" for e in set(valid_funcs)))
        )
        raise ValueError(msg)

    if isinstance(regex, re.Pattern):
        if flags:
            msg = "'flags' can only be used with a string pattern; pass flags to re.compile() instead"
            raise TypeError(msg)
        pattern = regex
    else:
        pattern = re.compile(regex, flags)

    if func is re.match:
        match_func = pattern.match
    elif func is re.search:
        match_func = pattern.search
    else:
        match_func = pattern.fullmatch

    msg = message or _NO_MATCH_MESSAGE

    def validator(
        value: typing.Any,
        field: typing.Optional[typing.Any] = None,
        instance: typing.Optional[typing.Any] = None,
    ):
        nonlocal msg

        if pre_validation_hook:
            value = pre_validation_hook(value)
        if not match_func(value):
            name = field.effective_name if field else "value"
            raise ValueError(
                msg.format_map(
                    {
                        "name": name,
                        "pattern": pattern.pattern,
                        "value": value,
                    }
                ),
                name,
                pattern,
                value,
            )

    validator.__name__ = f"validate_pattern_{pattern.pattern!r}"
    return FieldValidator(validator)


_INSTANCE_CHECK_FAILURE_MESSAGE = "Value must be an instance of {cls!r}"


def instance_of(
    cls: typing.Union[typing.Type, typing.Tuple[typing.Type, ...]],
    message: typing.Optional[str] = None,
    pre_validation_hook: typing.Optional[
        typing.Callable[[typing.Any], typing.Any]
    ] = None,
) -> FieldValidator:
    """
    A validator that raises `ValueError` if the initializer is called with a
    value that is not an instance of *cls*.

    :param cls: A type or tuple of types to check against
    :param message: Error message template
    :param pre_validation_hook: A function to preprocess the value before validation
    :return: A validator function
    :raises ValueError: If the value is not an instance of the specified type
    """
    global _INSTANCE_CHECK_FAILURE_MESSAGE

    msg = message or _INSTANCE_CHECK_FAILURE_MESSAGE

    def validator(
        value: typing.Any,
        field: typing.Optional[typing.Any] = None,
        instance: typing.Optional[typing.Any] = None,
    ):
        nonlocal msg

        if pre_validation_hook:
            value = pre_validation_hook(value)
        if not isinstance(value, cls):
            name = field.effective_name if field else "value"
            raise ValueError(
                msg.format_map(
                    {"cls": cls, "value": value, "name": name, "field": field}
                ),
                name,
                value,
                cls,
            )

    validator.__name__ = f"isinstance_of_{cls!r}"
    return FieldValidator(validator)


_SUBCLASS_CHECK_FAILURE_MESSAGE = "Value must be a subclass of {cls!r}"


def subclass_of(
    cls: typing.Union[typing.Type, typing.Tuple[typing.Type, ...]],
    message: typing.Optional[str] = None,
    pre_validation_hook: typing.Optional[
        typing.Callable[[typing.Any], typing.Any]
    ] = None,
) -> FieldValidator:
    """
    A validator that raises `ValueError` if the initializer is called with a
    value that is not a subclass of *cls*.

    :param cls: A type or tuple of types to check against
    :param message: Error message template
    :param pre_validation_hook: A function to preprocess the value before validation
    :return: A validator function
    :raises ValueError: If the value is not a subclass of the specified type
    """
    global _SUBCLASS_CHECK_FAILURE_MESSAGE

    msg = message or _SUBCLASS_CHECK_FAILURE_MESSAGE

    def validator(
        value: typing.Any,
        field: typing.Optional[typing.Any] = None,
        instance: typing.Optional[typing.Any] = None,
    ):
        nonlocal msg

        if pre_validation_hook:
            value = pre_validation_hook(value)
        if not (inspect.isclass(value) and issubclass(value, cls)):
            name = field.effective_name if field else "value"
            raise ValueError(
                msg.format_map(
                    {"cls": cls, "value": value, "name": name, "field": field}
                ),
                name,
                value,
                cls,
            )

    validator.__name__ = f"issubclass_of_{cls!r}"
    return FieldValidator(validator)


def optional(validator: _Validator) -> FieldValidator:
    """
    A validator that allows `None` as a valid value for the field.

    :param validator: The validator to apply to the field, if the field is not `None`
    :return: A validator function that applies the given validator if the value is not `None`
    :raises ValueError: If the value is not `None` and does not pass the validator
    """
    _validator = load_validators(validator).pop()

    def optional_validator(
        value: typing.Any,
        field: typing.Optional[typing.Any] = None,
        instance: typing.Optional[typing.Any] = None,
    ):
        if field and field.is_null(value):
            return
        if value is None:
            return
        return _validator(value, field, instance)

    optional_validator.__name__ = f"optional({validator.__name__})"
    return FieldValidator(optional_validator)


_IN_CHECK_FAILURE_MESSAGE = "Value must be in {choices!r}"


def in_(
    choices: typing.Iterable[typing.Any],
    message: typing.Optional[str] = None,
    pre_validation_hook: typing.Optional[
        typing.Callable[[typing.Any], typing.Any]
    ] = None,
) -> FieldValidator:
    """
    A validator that raises `ValueError` if the initializer is called with a
    value that is not in *choices*.

    :param choices: An iterable of valid values
    :param message: Error message template
    :param pre_validation_hook: A function to preprocess the value before validation
    :return: A validator function
    :raises ValueError: If the value is not in the specified choices
    """
    global _IN_CHECK_FAILURE_MESSAGE

    msg = message or _IN_CHECK_FAILURE_MESSAGE

    def validator(
        value: typing.Any,
        field: typing.Optional[typing.Any] = None,
        instance: typing.Optional[typing.Any] = None,
    ):
        nonlocal msg

        if pre_validation_hook:
            value = pre_validation_hook(value)
        if value not in choices:
            name = field.effective_name if field else "value"
            raise ValueError(
                msg.format_map(
                    {"choices": choices, "value": value, "name": name, "field": field}
                ),
                name,
                value,
                choices,
            )

    validator.__name__ = f"member_of_{choices!r}"
    return FieldValidator(validator)


_NEGATION_CHECK_FAILURE_MESSAGE = "Value must not validate {validator!r}"


def not_(
    validator: _Validator,
    message: typing.Optional[str] = None,
    pre_validation_hook: typing.Optional[
        typing.Callable[[typing.Any], typing.Any]
    ] = None,
) -> FieldValidator:
    """
    A validator that raises `ValueError` if the initializer is called with a
    value that validates against *validator*.

    :param validator: The validator to check against
    :param message: Error message template
    :param pre_validation_hook: A function to preprocess the value before validation
    :return: A validator function
    :raises ValueError: If the value validates against the specified validator
    """
    global _NEGATION_CHECK_FAILURE_MESSAGE

    msg = message or _NEGATION_CHECK_FAILURE_MESSAGE
    _validator = load_validators(validator).pop()

    def negative_validator(
        value: typing.Any,
        field: typing.Optional[typing.Any] = None,
        instance: typing.Optional[typing.Any] = None,
    ):
        nonlocal msg

        if pre_validation_hook:
            value = pre_validation_hook(value)
        try:
            _validator(value, field, instance)
        except ValueError:
            return
        name = field.effective_name if field else "value"
        raise ValueError(
            msg.format_map(
                {"validator": validator, "value": value, "name": name, "field": field}
            ),
            name,
            value,
            validator,
        )

    negative_validator.__name__ = f"negate({validator.__name__})"
    return FieldValidator(negative_validator)


def and_(*validators: _Validator) -> FieldValidator:
    """
    A validator that raises `ValueError` if the initializer is called with a
    value that does not validate against all of *validators*.

    :param validators: The validators to check against
    :return: A validator function
    :raises ValueError: If the value does not validate against all of the specified validators
    """

    def validator(
        value: typing.Any,
        field: typing.Optional[typing.Any] = None,
        instance: typing.Optional[typing.Any] = None,
    ):
        for validator in validators:
            validator(value, field, instance)
        return

    validator.__name__ = f"conjunction({[v.__name__ for v in validators]})"
    return FieldValidator(validator)


_DISJUNCTION_CHECK_FAILURE_MESSAGE = (
    "Value must validate at least one of {validators!r}"
)


def or_(
    *validators: _Validator,
    message: typing.Optional[str] = None,
    pre_validation_hook: typing.Optional[
        typing.Callable[[typing.Any], typing.Any]
    ] = None,
):
    """
    A validator that raises `ValueError` if the initializer is called with a
    value that does not validate against any of *validators*.

    :param validators: The validators to check against
    :param message: Error message template
    :param pre_validation_hook: A function to preprocess the value before validation
    :return: A validator function
    :raises ValueError: If the value does not validate against any of the specified validators
    """
    global _DISJUNCTION_CHECK_FAILURE_MESSAGE

    msg = message or _DISJUNCTION_CHECK_FAILURE_MESSAGE

    def validator(
        value: typing.Any,
        field: typing.Optional[typing.Any] = None,
        instance: typing.Optional[typing.Any] = None,
    ):
        nonlocal msg

        if pre_validation_hook:
            value = pre_validation_hook(value)

        for validator in validators:
            try:
                validator(value, field, instance)
                return
            except ValueError:
                continue
        name = field.effective_name if field else "value"
        raise ValueError(
            msg.format_map(
                {
                    "validators": [v.__name__ for v in validators],
                    "value": value,
                    "name": name,
                    "field": field,
                }
            ),
            name,
            value,
            [v.__name__ for v in validators],
        )

    validator.__name__ = f"disjunction({[v.__name__ for v in validators]})"
    return validator


def _is_callable(
    value: typing.Any,
    field: typing.Optional[typing.Any] = None,
    instance: typing.Optional[typing.Any] = None,
):
    """Check if the value is callable."""
    if not callable(value):
        name = field.effective_name if field else "value"
        raise ValueError(
            f"'{name}' must be callable",
            name,
            value,
        )


is_callable = FieldValidator(_is_callable)
