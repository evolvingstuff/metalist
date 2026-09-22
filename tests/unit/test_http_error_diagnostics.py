from pathlib import Path
import os
import subprocess
import sys

import pytest

from app.security.http_error_diagnostics import describe_server_exception


def test_server_exception_diagnostic_omits_message_and_absolute_path():
    repository = Path(__file__).resolve().parents[2]
    source = compile(
        "raise ValueError('PRIVATE_NOTE_CONTENT')",
        str(repository / "app" / "api" / "routes" / "notes.py"),
        "exec",
    )
    with pytest.raises(ValueError) as captured:
        exec(source)
    diagnostic = describe_server_exception(captured.value)

    assert diagnostic == {
        "errorType": "ValueError",
        "codeLocation": "app/api/routes/notes.py:1",
    }
    assert "PRIVATE_NOTE_CONTENT" not in str(diagnostic)
    assert str(repository) not in str(diagnostic)


def test_server_exception_diagnostic_hides_external_paths():
    source = compile("raise RuntimeError('PRIVATE_NOTE_CONTENT')", "/Users/private/secrets.py", "exec")
    with pytest.raises(RuntimeError) as captured:
        exec(source)
    diagnostic = describe_server_exception(captured.value)

    assert diagnostic == {"errorType": "RuntimeError", "codeLocation": "external"}


def test_real_application_500_contains_data_free_diagnostic(tmp_path):
    script = '''
from fastapi.testclient import TestClient
from app.main import app
from app.config import API_PREFIX
from app.services.tokens import token_service
from app.api.routes import notes as notes_module

exec(compile('def broken_view():\\n    raise ValueError("PRIVATE_NOTE_CONTENT")', notes_module.__file__, 'exec'))

app.add_api_route(API_PREFIX + "/diagnostic-fixture", broken_view)
token = token_service.create_token(client_info="fixture", owner_tab_id="tab", dek=None)
headers = {"Authorization": "Bearer " + token, "X-Metalist-Tab-Id": "tab", "Origin": "http://localhost"}
with TestClient(app, base_url="http://localhost", raise_server_exceptions=False) as client:
    response = client.get(API_PREFIX + "/diagnostic-fixture", headers=headers)
assert response.status_code == 500, (response.status_code, response.text)
assert response.json() == {
    "detail": "Internal server error",
    "diagnostic": {"errorType": "ValueError", "codeLocation": "app/api/routes/notes.py:2"},
}, response.text
assert response.headers["Cache-Control"] == "no-store, private"
assert "PRIVATE_NOTE_CONTENT" not in response.text
'''
    environment = dict(os.environ, METALIST_DATA_DIRECTORY=str(tmp_path), METALIST_ENVIRONMENT="production")
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr[-3000:]
