from typing import Any, Callable, Dict, Iterable, List, Literal, TypeVar, Generic
from django.db import models

from src.generics.data_utils.parsers import cleanString
from src.generics.utils.misc import get_value_by_traversal_path


_Model = TypeVar("_Model", bound=models.Model)


class ModelDataCleanerMeta(type):
    def __new__(cls, name, bases, attrs):
        new_class = super().__new__(cls, name, bases, attrs)
        # Run checks if the model attribute is set, That means the class is a subclass
        if new_class.model:
            cls.run_checks(new_class)
        return new_class

    @classmethod
    def run_checks(meta_cls, new_class) -> None:
        """Run all checks on the class."""

        def attr_is_check(attr_name: str, attr_value: Any):
            return attr_name.startswith("check") and callable(attr_value)

        for attr_name in dir(meta_cls):
            attr_value = getattr(meta_cls, attr_name)
            if not attr_name.startswith("__") and attr_is_check(attr_name, attr_value):
                attr_value(new_class)
        return

    @staticmethod
    def check_model(cls) -> None:
        """Check if the model attribute is set and is a subclass of `django.db.models.Model`."""
        if not issubclass(cls.model, models.Model):
            raise ValueError(
                "`model` attribute must be a subclass of `django.db.models.Model`"
            )
        return

    @staticmethod
    def check_exclude(cls) -> None:
        """Check if the exclude attribute is set and is a list of strings."""
        if not isinstance(cls.exclude, List):
            raise ValueError("`exclude` attribute must be a list of strings")
        for field in cls.exclude:
            if not isinstance(field, str):
                raise ValueError("`exclude` attribute must be a list of strings")

        model_field_names = [field.name for field in cls.model._meta.get_fields()]
        for field in cls.exclude:
            if field not in model_field_names:
                raise ValueError(
                    f"Field `{field}` not found in model `{cls.model.__name__}` fields"
                )
        return

    @staticmethod
    def check_key_mappings(cls) -> None:
        """Check if the key_mappings attribute is set and is a dictionary of strings."""
        if not isinstance(cls.key_mappings, Dict):
            raise ValueError("`key_mappings` attribute must be a dictionary")
        for field, key in cls.key_mappings.items():
            if not isinstance(field, str) or not isinstance(key, str):
                raise ValueError(
                    "`key_mappings` attribute must be a dictionary of strings"
                )
        return

    @staticmethod
    def check_parsers(cls) -> None:
        """Check if the parsers attribute is set and is a dictionary of iterables of callables."""
        if not isinstance(cls.parsers, Dict):
            raise ValueError("`parsers` attribute must be a dictionary")
        for field, parsers in cls.parsers.items():
            if not isinstance(field, str) or not isinstance(parsers, Iterable):
                raise ValueError(
                    "`parsers` attribute must be a dictionary of iterables"
                )
            for parser in parsers:
                if not callable(parser):
                    raise ValueError("Parsers must be callable")
        return

    @staticmethod
    def check_clean_strings(cls) -> None:
        """Check if the clean_strings attribute is set and is a boolean."""
        if not isinstance(cls.clean_strings, bool):
            raise ValueError("`clean_strings` attribute must be a boolean")
        return


class ModelDataCleaner(Generic[_Model], metaclass=ModelDataCleanerMeta):
    """
    Helper class for cleaning data from Prembly API.

    This helps to clean the raw data fetched and
    prepare it for creating a new instance of a model.
    """

    model: type[_Model] = None
    """The model to which the data will be cleaned for."""
    exclude: List[str] = []
    """Names of model fields to exclude from the cleaning process."""
    key_mappings: Dict[str, str] = {}
    """
    A mapping of model field names to the actual keys in the raw data.

    This is useful when the key in the raw data is different from the model field name.
    """
    parsers: Dict[str, Iterable[Callable[..., Any]]] = {}
    clean_strings: bool = True

    def __init__(self, rawdata: Dict[str, Any]) -> None:
        if not self.model:
            raise ValueError(
                "Create a subclass of ModelDataCleaner and set the `model` attribute"
            )
        if not rawdata:
            raise ValueError("`rawdata` cannot be empty")
        self.rawdata = rawdata
        self._cleaned = None

    @property
    def fields(self) -> List[str]:
        """
        Return a list of model field names to be cleaned.

        This excludes fields specified in the `exclude` attribute.

        Excludes the models primary key field by default
        """
        model_fields = self.model._meta.get_fields()
        field_names = []
        for field in model_fields:
            # Exclude relation-type fields
            if field.related_model or field.primary_key:
                continue
            if field.name not in self.exclude:
                field_names.append(field.name)
        return field_names

    @property
    def cleaned_data(self) -> Dict[str, Any]:
        """Return the cleaned data. If the data has not been cleaned, an error is raised"""
        if not self._cleaned:
            raise ValueError("rawdata has not been cleaned yet.")
        return self._cleaned

    def to_key(self, field_name: str) -> str:
        """
        Converts model field name to key to be used to
        fetch the value of the field from the raw data provided.

        This method also uses the key specified in `key_mappings`
        in place of the field name.

        :param field_name: The field name to convert to a key.
        :return: The key to be used to fetch the value from the raw data

        #### Override this method in a subclass to customize

        Example:
        ```python
        class MyDataCleaner(ModelDataCleaner):
            def to_key(self, field_name: str) -> str:
                field_name = super().to_key(field_name)
                return field_name.title()
        ```
        """
        if field_name in self.key_mappings:
            field_name = self.key_mappings[field_name]
        return field_name

    def clean(self) -> None:
        """Clean the raw data. Apply parsers."""
        self._cleaned = {}
        for name in self.fields:
            key = self.to_key(name)
            value = get_value_by_traversal_path(self.rawdata, key)

            if isinstance(value, str) and self.clean_strings is True:
                value = cleanString(value)

            parsers: Iterable[Callable] = self.parsers.get(name, None)
            if parsers:
                for parser in parsers:
                    value = parser(value)
            self._cleaned[name] = value
        return

    def new_instance(self, **extra_fields):
        """
        Return a new instance of the model with the cleaned data
        created using the cleaned data and any extra fields provided.

        The instance returned is not saved to the database.
        """
        if not self._cleaned:
            self.clean()
        return self.model(**self.cleaned_data, **extra_fields)


def model_data_cleaner_factory(
    m: type[_Model], configs: Dict[str, Any]
) -> ModelDataCleaner[_Model]:
    """
    Helper function to create a new ModelDataCleaner subclass at runtime.

    :param model: The model to clean data for.
    :param configs: The configurations for the ModelDataCleaner.
    :return: A new instance of a ModelDataCleaner.
    """
    data_cleaner_cls = type(
        f"{m.__name__}DataCleaner", (ModelDataCleaner,), {"model": m, **configs}
    )
    return data_cleaner_cls[m]
