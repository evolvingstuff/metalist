"""Small, data-free diagnostics for unexpected HTTP failures."""

from pathlib import Path
import traceback


_APP_DIRECTORY = Path(__file__).resolve().parents[1]
_REPOSITORY_DIRECTORY = _APP_DIRECTORY.parent


def describe_server_exception(error: Exception) -> dict[str, str]:
    """Expose the exception class and last application frame, never its message."""
    location = "external"
    for frame in reversed(traceback.extract_tb(error.__traceback__)):
        path = Path(frame.filename).resolve()
        if path.is_relative_to(_APP_DIRECTORY):
            location = f"{path.relative_to(_REPOSITORY_DIRECTORY).as_posix()}:{frame.lineno}"
            break
    return {"errorType": type(error).__name__, "codeLocation": location}
