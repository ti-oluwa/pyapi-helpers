class DataError(Exception):
    """Base class for data errors."""

    pass


class DataFetchError(DataError):
    """Raised when there is an error fetching data from the Prembly API."""


__all__ = ["DataError", "DataFetchError"]
