"""Contains helper and utility modules that aid faster development of api application(s)."""

from pathlib import Path
import sys

from .dependencies import deps_required

__author__ = "Daniel T. Afolayan (ti-oluwa@github)"


PYTHON_VERSION = float(f"{sys.version_info.major}.{sys.version_info.minor}")

RESOURCES_PATH = Path(__file__).resolve().parent / "resources"

deps_required(
    {
        "typing_extensions": "typing-extensions",
    }
)
