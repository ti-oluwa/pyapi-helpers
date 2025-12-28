from __future__ import annotations

import enum
import functools
import inspect
from typing import Any, Optional, TypeVar, Union, List, Generic, Type, Callable
from typing_extensions import ParamSpec
from django.db import models
from django.core.exceptions import ImproperlyConfigured


M = TypeVar("M", bound=models.Model)
P = ParamSpec("P")
QS = TypeVar("QS", bound=models.QuerySet)
BaseManager = TypeVar("BaseManager", bound=models.manager.BaseManager)


class SearchableQuerySet(models.QuerySet[M]):
    """A model queryset that supports search"""

    model: Type[M]

    def search(
        self, query: Union[str, Any], fields: Optional[Union[List[str], str]] = None
    ):
        """
        Search the queryset for the given query in the given fields.

        :param query: The search query.
        :param fields: The names of the model fields to search in. Can be a traversal path.
        :return: A queryset containing the search results.
        """
        if isinstance(fields, str):
            fields = [
                fields,
            ]

        fields = fields or []
        query = query.strip()
        if not query:
            return self.none()

        q = models.Q()
        for field in fields:
            q |= models.Q(**{f"{field.replace('.', '__')}__icontains": query})
        return self.filter(q).distinct()


SQS = TypeVar("SQS", bound=SearchableQuerySet)


class BaseSearchableManager(models.manager.BaseManager, Generic[SQS]):
    """Base model manager that supports search"""

    _queryset_class = SearchableQuerySet

    def __init__(self) -> None:
        super().__init__()
        if not issubclass(self._queryset_class, SearchableQuerySet):
            raise ImproperlyConfigured(
                f"`_queryset_class` must be an instance of {SearchableQuerySet.__name__}"
            )

    def get_queryset(self) -> SQS:
        return super().get_queryset() # type: ignore[return-value]

    def search(
        self, query: Union[str, Any], fields: Optional[Union[List[str], str]] = None
    ) -> SQS:
        """
        Search the model for the given query in the given fields.

        :param query: The search query.
        :param fields: The names of the model fields to search in. Can be a traversal path.
        :return: A queryset containing the search results.
        """
        return self.get_queryset().search(query=query, fields=fields)


class EagerFetchMethod(enum.Enum):
    """Enumeration of eager fetch methods"""

    SELECT_RELATED = "select_related"
    PREFETCH_RELATED = "prefetch_related"


def eager_fetch_decorator(*fields, eager_fetch_method: EagerFetchMethod):
    """
    Automatically applies the defined eager fetch method to the queryset or manager class or method.

    :param fields: The fields to eager fetch.
    :param eager_fetch_method: Name of method for eager fetching model fields.
    :return: The decorated queryset or manager class or method.
    """
    eager_fetch_method = EagerFetchMethod(eager_fetch_method)

    def qs_method_decorator(qs_method: Callable[P, QS]) -> Callable[P, QS]:
        @functools.wraps(qs_method)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> QS:
            return getattr(qs_method(*args, **kwargs), eager_fetch_method.value)(
                *fields
            )

        return wrapper

    def cls_decorator(
        cls: Union[Type[QS], Type[BaseManager]],
    ) -> Union[Type[QS], Type[BaseManager]]:
        if issubclass(cls, models.manager.BaseManager):
            cls.get_queryset = qs_method_decorator(cls.get_queryset)
        else:
            for method_name in ["filter", "exclude", "all", "get"]:
                if hasattr(cls, method_name):
                    method = getattr(cls, method_name)
                    setattr(cls, method_name, qs_method_decorator(method))
        return cls

    def obj_decorator(
        obj: Union[Type[QS], Type[BaseManager], Callable[P, QS]],
    ) -> Union[Type[QS], Type[BaseManager], Callable[P, QS]]:
        if inspect.isclass(obj):
            return cls_decorator(obj)
        return qs_method_decorator(obj)

    return obj_decorator


auto_prefetch = functools.partial(
    eager_fetch_decorator,
    eager_fetch_method=EagerFetchMethod.PREFETCH_RELATED,
)
"""
#### USE WITH CAUTION! ####

Automatically eager prefetch the specified fields for the queryset or manager class or method.

Usage:
```python
@auto_prefetch("field1", "field2")
class MyModelManager(models.Manager):
    pass
    
@auto_prefetch("field1", "field2")
class MyModelQuerySet(models.QuerySet):
    pass
```

Or;
```python
class MyModelManager(models.Manager):

    @auto_prefetch("field1", "field2")
    def queryset_method(self):
        qs = self.exclude(...)
        return qs

class MyModelQuerySet(models.QuerySet):
    
    @auto_prefetch("field1", "field2")
    def method(self):
        qs = self.filter(...)
        return qs
```

"""

auto_select = functools.partial(
    eager_fetch_decorator,
    eager_fetch_method=EagerFetchMethod.SELECT_RELATED,
)
"""
#### USE WITH CAUTION! ####

Automatically eager select the specified fields for the queryset or manager class or method.

Usage:
```python
@auto_select("field1", "field2")
class MyModelManager(models.Manager):
    pass
    
@auto_select("field1", "field2")
class MyModelQuerySet(models.QuerySet):
    pass
```

Or;
```python
class MyModelManager(models.Manager):

    @auto_select("field1", "field2")
    def queryset_method(self):
        qs = self.exclude(...)
        return qs

class MyModelQuerySet(models.QuerySet):

    @auto_select("field1", "field2")
    def method(self):
        qs = self.filter(...)
        return qs
```

"""
