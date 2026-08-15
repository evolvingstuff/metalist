from __future__ import annotations

import pytest

from app.usecases.rename_tag import apply_rename_tag_everywhere


def test_rename_tag_rejects_reserved_or_before_loading_store() -> None:
    with pytest.raises(ValueError, match="reserved for search"):
        apply_rename_tag_everywhere(old="alpha", new="OR", token="")
