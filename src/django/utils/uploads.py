import typing
from pathlib import Path
from django.conf import settings

from src.generics.utils.misc import get_attr_by_traversal_path


base_dir_str = Path(settings.BASE_DIR).as_posix()


def make_upload_directory_for_user(user: str = "id") -> str:
    """
    Factory function for creating an upload directory function for a user.

    :param user: The user attribute of the instance to use for the directory.
    """

    def upload_dir_for_user(
        instance, filename, parent_dir: typing.Optional[str] = None
    ) -> str:
        """
        Upload directory function for a user.

        :param instance: The instance of the model.a
        :param filename: The name of the file being uploaded.a
        :param parent_dir: The parent directory of the file, if any.
        """
        user_value = get_attr_by_traversal_path(instance, user)
        # Make sure to use relative paths to avoid issues with SuspiciousFileOperation
        # exceptions raised by Django when using absolute paths to save files.
        upload_path = Path(
            f"{base_dir_str}/uploads/{user_value}/{parent_dir or ''}/{filename}"
        ).relative_to(base_dir_str).as_posix()
        return upload_path

    return upload_dir_for_user
