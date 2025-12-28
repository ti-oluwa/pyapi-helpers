import importlib
import typing


def import_string(dotted_path: str) -> typing.Any:
    """
    Import a dotted module path and return the attribute specified by the
    `name` part of the path.

    :param dotted_path: The dotted module path to import
    :return: The attribute specified by the `name` part of the path
    """
    module_path, _, name = dotted_path.rpartition(".")
    module = importlib.import_module(module_path)
    return getattr(module, name)
