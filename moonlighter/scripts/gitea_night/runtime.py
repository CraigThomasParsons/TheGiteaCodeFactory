"""Keep the worker lease alive while any validation or agent child is alive."""
import os


def inherited_locks():
    """Pass the open OS lock into children so a parent crash cannot free it early."""
    value = os.environ.get('GITEA_NIGHT_LOCK_FD')
    return () if value is None else (int(value),)
