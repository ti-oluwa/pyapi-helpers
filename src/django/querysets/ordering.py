from __future__ import annotations
from typing import Callable, Dict, Generic, Optional, TypeVar, Union
from django.db import models
import warnings


M = TypeVar("M", bound=models.Model)


class QSOrderer(Generic[M]):
    """Custom ordering of querysets using registered keys"""

    model: M = None
    """
    Set this in a subclass just in case you need to explicitly 
    specify the model whose queryset is to be ordered
    """
    class_orderers: Dict[
        str, Dict[str, Callable[[models.QuerySet[M], bool], models.QuerySet[M]]]
    ] = {}
    """Mapping of registered orderers that apply to the class/subclass and its instances"""

    def __init__(
        self, queryset: Union[models.QuerySet[M], models.manager.BaseManager[M]] = None
    ) -> None:
        cls_model = self.model
        if not (cls_model or queryset):
            raise ValueError(f"Pass in a queryset or set {self.__name__}.model")
        if (queryset and cls_model) and (queryset.model != cls_model):
            raise ValueError(
                f"Expected queryset to contain objects of type {cls_model.__name__}"
            )

        self.qs = queryset or cls_model.objects
        # Copy the class' orderers onto the instance
        self.orderers = self.get_class_orderers(type(self))
        return None

    def order_by(
        self, *keys: str
    ) -> models.manager.BaseManager[M] | models.QuerySet[M]:
        """
        This method is used to apply custom ordering to queryset using
        registered keys.

        Unrecognized keys or invalid orderers will not be applied,

        To add a new orderer, use the `register` method.

        :param keys: Registered ordering keys.

        Tip: Use negative keys to reverse the ordering. For instance,
        '-profitability'
        """
        qs = self.qs.all()
        for key in keys:
            reverse = key.startswith("-")
            if reverse:
                key = key[1:]

            orderer = self.orderers.get(key, None)
            if orderer is None:
                continue
            if not callable(orderer):
                warnings.warn(f"Invalid orderer registered for key '{key}'")
                continue

            ordered = orderer(self.qs, reverse)
            if not isinstance(ordered, models.QuerySet):
                raise TypeError(
                    f"Expected orderer for `{key}` to return a queryset not `{type(ordered).__name__}`"
                )
            qs = ordered
        return qs

    @classmethod
    def register(
        cls,
        key: str,
        func: Optional[Callable[[models.QuerySet[M], bool], models.QuerySet[M]]] = None,
    ):
        """
        Register a new orderer. An orderer should take two arguments, a queryset,
        and a boolean that indicates whether to reverse the ordering.

        The orderer should return the newly ordered queryset.

        Example:
        ```python
        @QSOrderer.register("newkey")
        def custom_orderer(qs: models.QuerySet[M], reverse: bool):
            if reverse:
                return qs.order_by("-attribute")
            return qs.order_by("attribute")
        ```

        Calling this class method using an instance, instead of the class,
        registers the orderer on the instance not the class. So you can have
        instance specific orderers.

        :param key: The key to register the orderer with.
        This is the key that will be used to apply the orderer
        when calling the `order_by`.
        """

        def decorator(func: Callable[[models.QuerySet[M], bool], models.QuerySet[M]]):
            # If an instance of the class calls the register method,
            # the orderer is added to the instance's orderers dictionary
            if isinstance(cls, QSOrderer):
                instance = cls
                instance.orderers[key] = func
            else:
                # Else, add it to the class' orderers
                cls.register_class_orderer(cls, key, func)
            return func

        if func:
            return decorator(func)
        return decorator

    @staticmethod
    def get_class_orderers(
        cls: type[QSOrderer],
    ) -> Dict[str, Callable[[models.QuerySet[M], bool], models.QuerySet[M]]]:
        """
        Returns a copy of the class' orderers mapping,
        including that of its parent classes.
        """
        orderers = {}
        for _cls in cls.mro():
            if not issubclass(_cls, QSOrderer):
                continue
            cls_key = str(hash(_cls))
            c_orderers = QSOrderer.class_orderers.get(cls_key, {})
            orderers.update(c_orderers)
        return orderers

    @staticmethod
    def register_class_orderer(
        cls: type[QSOrderer],
        key: str,
        orderer: Callable[[models.QuerySet[M], bool], models.QuerySet[M]],
    ) -> None:
        """Registers an orderer for a `QSOrderer` class/subclass"""
        if not callable(orderer):
            raise TypeError("Invalid type for orderer")

        # Store the orderers mapping againt the class' hash
        cls_key = str(hash(cls))
        if cls_key not in QSOrderer.class_orderers:
            QSOrderer.class_orderers[cls_key] = {}
        QSOrderer.class_orderers[cls_key][key] = orderer
        return None


def reverse_ordering_key(key: str) -> str:
    """Reverse a queryset ordering key"""
    if key.startswith("-"):
        return key[1:]
    return "-" + key
