"""Thread-safe context for the currently authenticated user.

The node's command execution service sets this before calling command.execute().
JarvisStorage reads it when accessing user-scoped secrets.
"""

from contextvars import ContextVar

_current_user_id: ContextVar[int | None] = ContextVar("current_user_id", default=None)


def get_current_user_id() -> int | None:
    """Get the user_id of the currently executing request."""
    return _current_user_id.get()


def set_current_user_id(user_id: int | None) -> None:
    """Set the user_id for the currently executing request."""
    _current_user_id.set(user_id)
