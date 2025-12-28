
from asgiref.sync import SyncToAsync
from django.db import close_old_connections


class DatabaseSyncToAsync(SyncToAsync):
    """
    SyncToAsync version that cleans up old database connections when it exits.
    """

    def thread_handler(self, loop, *args, **kwargs):
        close_old_connections()
        try:
            return super().thread_handler(loop, *args, **kwargs)
        finally:
            close_old_connections()


database_sync_to_async = DatabaseSyncToAsync
# Extract from Django channels
