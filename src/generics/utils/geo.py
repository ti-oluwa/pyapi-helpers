from src.dependencies import deps_required

deps_required({"geopy": "geopy"})

from geopy.distance import geodesic, great_circle  # type: ignore[import]
from .choice import ExtendedEnum


class GeoMethod(ExtendedEnum):
    """
    Enumeration of methods for calculating the distance between two points.
    """

    GEODESIC = "geodesic"
    GREAT_CIRCLE = "great_circle"


def get_distance_between_points(
    point1: tuple,
    point2: tuple,
    *,
    unit: str = "km",
    method: GeoMethod = GeoMethod.GEODESIC,
) -> float:
    """
    Uses `geopy.geodesics` or `geopy.great_circle` to calculate the
    distance between two points on the earth's surface.

    :param point1: The first point as a tuple of latitude and longitude.
    :param point2: The second point as a tuple of latitude and longitude.
    :param unit: The unit of distance to return.
        Possible values are: "km", "miles", "m", "ft", "nautical".
        Default is "km".
    :return: The distance between the two points in the specified unit.
    """
    method = GeoMethod(method)

    if method == GeoMethod.GREAT_CIRCLE:
        return getattr(great_circle(point1, point2), unit)
    return getattr(geodesic(point1, point2), unit)


def check_point_within_radius(
    point: tuple,
    center: tuple,
    radius: float,
    *,
    unit: str = "km",
    method: GeoMethod = GeoMethod.GEODESIC,
) -> bool:
    """
    Check if a point is within a given radius of a center point.

    :param point: The point to check as a tuple of latitude and longitude.
    :param center: The center point as a tuple of latitude and longitude.
    :param radius: The radius (in unit) to check within.
    :param unit: The unit of distance to use.
        Possible values are: "km", "miles", "m", "ft", "nautical".
        Default is "km".
    :return: True if the point is within the radius, otherwise False.
    """
    return (
        get_distance_between_points(point, center, unit=unit, method=method) <= radius
    )
