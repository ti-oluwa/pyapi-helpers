from src.dependencies import deps_required

deps_required(
    {
        "channels": "https://channels.readthedocs.io/en/stable/",
    }
)

from src.django.config import settings


channels_settings = settings.CHANNELS
