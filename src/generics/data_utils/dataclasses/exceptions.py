from src.generics.data_utils.exceptions import DataError


class FieldError(DataError):
    """Exception raised for field-related errors."""

    pass


class FieldValidationError(FieldError):
    """Exception raised for validation errors."""

    pass


class SerializationError(DataError):
    """Exception raised for serialization errors."""

    pass


class DeserializationError(DataError):
    """Exception raised for deserialization errors."""

    pass


class FrozenError(DataError):
    """Exception raised for frozen data classes."""

    pass


class FrozenFieldError(FrozenError):
    """Exception raised for frozen fields."""

    pass


class FrozenInstanceError(FrozenError):
    """Exception raised for frozen instances."""

    pass
