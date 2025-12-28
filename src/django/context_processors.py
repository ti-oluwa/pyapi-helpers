from django.conf import settings
from django.utils import timezone


def application(_):
    """
    Adds the project/application details to the context.
    """
    app_name = getattr(settings, "APPLICATION_NAME", "Django app")
    app_alias = getattr(settings, "APPLICATION_ALIAS", "Django app")
    return {
        "app_name": app_name,
        "app_alias": app_alias,
        "current_year": timezone.now().year,
        "settings": settings,
    }
