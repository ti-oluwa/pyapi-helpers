import random
import typing


def _random_color():
    while True:
        yield "#{:06x}".format(random.randint(0, 0xFFFFFF))


def _distinct_color():
    used_colors = set()
    while True:
        hue = random.randint(0, 360)
        saturation = random.randint(50, 100)
        lightness = random.randint(40, 70)
        color = f"hsl({hue}, {saturation}%, {lightness}%)"
        if color not in used_colors:
            used_colors.add(color)
            yield color


def random_colors(distinct: bool = True) -> typing.Generator[str, None, None]:
    """
    Generates an indefinite sequence of random colors.

    :param distinct: bool: If True, generate distinct colors using HSL color space.
                           If False, generate completely random colors in hexadecimal format. Default is True.

    :yield: str: A random color string.

    Example:
    ```python
    colors = random_colors(distinct=True)
    next(colors)  # 'hsl(0.0, 55%, 55%)'
    next(colors)  # 'hsl(36.0, 55%, 45%)'

    colors = random_colors(distinct=False)
    next(colors)  # '#a1c9f1'
    next(colors)  # '#b2a1c5'
    ```
    """
    if not distinct:
        yield from _random_color()
    yield from _distinct_color()
