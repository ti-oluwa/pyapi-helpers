import typing
import random

T = typing.TypeVar("T")


def shuffle(items: typing.List[T]) -> typing.Iterable[T]:
    """
    Shuffle a list of items using the Fisher-Yates algorithm (In-place).

    :param items: The list of items to shuffle.
    :return: The shuffled list.
    """
    n = len(items)
    for i in range(n - 1, 0, -1):
        j = random.randint(0, i)  # Random index between 0 and i
        items[i], items[j] = items[j], items[i]  # Swap items
    return items


def shuffle_dict(d: typing.Dict[T, T]) -> typing.Dict[T, T]:
    """
    Shuffle a dictionary by converting it to a list of tuples, shuffling the list, and converting it back to a dictionary.

    :param d: The dictionary to shuffle.
    :return: The shuffled dictionary.
    """
    return dict(shuffle(list(d.items())))
