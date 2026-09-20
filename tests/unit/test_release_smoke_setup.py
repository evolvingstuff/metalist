"""Release harness setup must remain unattended and preserve TLS verification."""
import hashlib
import importlib.util
import json
from pathlib import Path
import ssl
import subprocess
from types import SimpleNamespace

import pytest


_spec = importlib.util.spec_from_file_location('release_smoke_setup', Path(__file__).resolve().parents[2] / 'scripts/smoke_installed_package.py')
assert _spec is not None and _spec.loader is not None
smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoke)


@pytest.fixture
def edge_setup(tmp_path, monkeypatch):
    executable = tmp_path / 'programs/Microsoft/Edge/Application/msedge.exe'
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b'fixture')
    certificate = tmp_path / 'certificate.pem'
    certificate.write_text(ssl.DER_cert_to_PEM_cert(b'fixture certificate'))
    environment = {'RUNNER_ENVIRONMENT': 'github-hosted', 'RUNNER_TEMP': str(tmp_path),
                   'ProgramFiles': str(tmp_path / 'programs')}
    monkeypatch.setattr(smoke, 'os', SimpleNamespace(name='nt', environ=environment))
    monkeypatch.setattr(smoke.shutil, 'which', lambda name: '/fixture/node')
    return {'directory': tmp_path, 'certificate': certificate, 'host': '10.0.0.5',
            'profiles': [('first', 8000, 8443), ('second', 8001, 8444)],
            'browser_name': 'edge', 'use_https': True}


def test_edge_uses_unattended_machine_trust_and_removes_only_its_certificate(edge_setup, monkeypatch):
    commands = []
    def run(command, **options):
        if '-user' in command:
            raise subprocess.TimeoutExpired(command, 30)
        commands.append(command)
    monkeypatch.setattr(smoke.subprocess, 'run', run)
    smoke._verify_browser_startup(**edge_setup)
    assert commands[0] == ['certutil', '-addstore', 'Root', str(edge_setup['certificate'])]
    assert commands[1][2] == 'edge'
    assert commands[1][-2:] == ['https://10.0.0.5:8443', 'https://10.0.0.5:8444']
    thumbprint = hashlib.sha1(b'fixture certificate', usedforsecurity=False).hexdigest()
    assert commands[2] == ['certutil', '-delstore', 'Root', thumbprint]
    diagnostics = json.loads((edge_setup['directory'] / 'metalist-browser-results/edge/setup-results.json').read_text())
    assert diagnostics['passed'] is True


def test_edge_failure_still_removes_trust_and_keeps_diagnostics(edge_setup, monkeypatch):
    commands = []
    def run(command, **options):
        commands.append(command)
        if command[0] != 'certutil':
            raise subprocess.CalledProcessError(1, command)
    monkeypatch.setattr(smoke.subprocess, 'run', run)
    with pytest.raises(subprocess.CalledProcessError):
        smoke._verify_browser_startup(**edge_setup)
    assert commands[-1][:3] == ['certutil', '-delstore', 'Root']
    diagnostics = json.loads((edge_setup['directory'] / 'metalist-browser-results/edge/setup-results.json').read_text())
    assert diagnostics == {
        'browser': 'edge', 'transport': 'https',
        'stage': 'running edge startup checks', 'passed': False,
    }


def test_trust_setup_failure_produces_artifact_before_browser_launch(edge_setup, monkeypatch):
    def fail(command, **options):
        raise subprocess.TimeoutExpired(command, 30)
    monkeypatch.setattr(smoke.subprocess, 'run', fail)
    with pytest.raises(subprocess.TimeoutExpired):
        smoke._verify_browser_startup(**edge_setup)
    diagnostics = json.loads((edge_setup['directory'] / 'metalist-browser-results/edge/setup-results.json').read_text())
    assert diagnostics == {
        'browser': 'edge', 'transport': 'https',
        'stage': 'trusting generated certificate', 'passed': False,
    }


@pytest.mark.parametrize(
    ('browser_name', 'relative_path'),
    [
        ('chrome', 'Google/Chrome/Application/chrome.exe'),
        ('firefox', 'Mozilla Firefox/firefox.exe'),
    ],
)
def test_windows_release_browsers_exercise_loopback_http_without_certificate_bypass(
    tmp_path,
    monkeypatch,
    browser_name,
    relative_path,
):
    executable = tmp_path / 'programs' / relative_path
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b'fixture')
    certificate = tmp_path / 'certificate.pem'
    certificate.write_text(ssl.DER_cert_to_PEM_cert(b'fixture certificate'))
    environment = {
        'RUNNER_ENVIRONMENT': 'github-hosted',
        'RUNNER_TEMP': str(tmp_path),
        'ProgramFiles': str(tmp_path / 'programs'),
    }
    monkeypatch.setattr(smoke, 'os', SimpleNamespace(name='nt', environ=environment))
    monkeypatch.setattr(smoke.shutil, 'which', lambda name: '/fixture/node')
    commands = []
    monkeypatch.setattr(smoke.subprocess, 'run', lambda command, **options: commands.append(command))

    smoke._verify_browser_startup(
        directory=tmp_path,
        certificate=certificate,
        host='127.0.0.1',
        profiles=[('first', 8000, 8443), ('second', 8001, 8444)],
        browser_name=browser_name,
        use_https=False,
    )

    assert len(commands) == 1
    assert commands[0][2:5] == [browser_name, str(executable), str(tmp_path / 'metalist-browser-results' / browser_name)]
    assert commands[0][-2:] == ['http://127.0.0.1:8000', 'http://127.0.0.1:8001']
    diagnostics = json.loads(
        (tmp_path / 'metalist-browser-results' / browser_name / 'setup-results.json').read_text()
    )
    assert diagnostics['passed'] is True
