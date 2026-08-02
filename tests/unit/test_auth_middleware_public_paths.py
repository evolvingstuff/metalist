from __future__ import annotations

import pytest

from app.api.middleware.auth import AuthMiddleware


@pytest.mark.parametrize(
    "path",
    (
        "/namespace-renamed?job=11111111-1111-1111-1111-111111111111",
        "/namespace-renamed/open?job=11111111-1111-1111-1111-111111111111",
        "/api2/auth/namespaces/rename-jobs/11111111-1111-1111-1111-111111111111",
    ),
)
def test_namespace_rename_restart_routes_do_not_require_tab_auth(path: str) -> None:
    request_path = path.partition("?")[0]

    assert any(request_path.startswith(public_path) for public_path in AuthMiddleware.PUBLIC_PATHS)
