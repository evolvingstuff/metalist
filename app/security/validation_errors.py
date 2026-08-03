from __future__ import annotations

from collections.abc import Mapping, Sequence


def summarize_validation_errors(
    errors: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    """Return validation diagnostics without rejected input or arbitrary context."""
    summarized: list[dict[str, object]] = []
    for error in errors:
        error_type = error["type"]
        location = error["loc"]
        if not isinstance(error_type, str):
            raise TypeError("validation error type must be a string")
        if not isinstance(location, (list, tuple)):
            raise TypeError("validation error location must be a list or tuple")
        normalized_location: list[str | int] = []
        for part in location:
            if not isinstance(part, (str, int)):
                raise TypeError("validation error location parts must be strings or integers")
            normalized_location.append(part)
        summarized.append(
            {
                "type": error_type,
                "loc": normalized_location,
            }
        )
    return summarized
