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
    return {'certificate': certificate, 'host': '10.0.0.5',
            'profiles': [('first', 8000, 8443), ('second', 8001, 8444)],
            'browser_name': 'edge', 'use_https': True,
            'cold_runs': 1, 'reloads': 2, 'validate_encrypted_login': True}


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
    assert commands[1][5:8] == ['1', '2', '1']
    assert commands[1][-2:] == ['https://10.0.0.5:8443', 'https://10.0.0.5:8444']
    thumbprint = hashlib.sha1(b'fixture certificate', usedforsecurity=False).hexdigest()
    assert commands[2] == ['certutil', '-delstore', 'Root', thumbprint]
    diagnostics = json.loads((edge_setup['certificate'].parent / 'metalist-browser-results/edge/setup-results.json').read_text())
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
    diagnostics = json.loads((edge_setup['certificate'].parent / 'metalist-browser-results/edge/setup-results.json').read_text())
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
    diagnostics = json.loads((edge_setup['certificate'].parent / 'metalist-browser-results/edge/setup-results.json').read_text())
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
    invocations = []
    monkeypatch.setattr(
        smoke.subprocess,
        'run',
        lambda command, **options: invocations.append((command, options)),
    )

    smoke._verify_browser_startup(
        certificate=certificate,
        host='127.0.0.1',
        profiles=[('first', 8000, 8443), ('second', 8001, 8444)],
        browser_name=browser_name,
        use_https=False,
        cold_runs=1,
        reloads=2,
        validate_encrypted_login=True,
    )

    assert len(invocations) == 1
    command, options = invocations[0]
    assert command[2:5] == [browser_name, str(executable), str(tmp_path / 'metalist-browser-results' / browser_name)]
    assert command[5:8] == ['1', '2', '1']
    assert command[-2:] == ['http://127.0.0.1:8000', 'http://127.0.0.1:8001']
    assert options['cwd'] == Path(smoke.__file__).resolve().parent / 'browser-validation'
    diagnostics = json.loads(
        (tmp_path / 'metalist-browser-results' / browser_name / 'setup-results.json').read_text()
    )
    assert diagnostics['passed'] is True


def test_browser_artifact_preserves_startup_and_server_logs(tmp_path, monkeypatch):
    monkeypatch.setenv('RUNNER_TEMP', str(tmp_path / 'runner'))
    startup_log = tmp_path / 'startup.log'
    startup_log.write_text('launcher diagnostics', encoding='utf-8')
    data_directory = tmp_path / 'data'
    logs_directory = data_directory / 'logs'
    logs_directory.mkdir(parents=True)
    (logs_directory / 'first-server.log').write_text('proxy diagnostics', encoding='utf-8')

    smoke._preserve_browser_server_diagnostics(
        startup_log=startup_log, data_directory=data_directory,
    )

    preserved = tmp_path / 'runner' / 'metalist-browser-results' / 'server-logs'
    assert (preserved / 'startup.log').read_text(encoding='utf-8') == 'launcher diagnostics'
    assert (preserved / 'first-server.log').read_text(encoding='utf-8') == 'proxy diagnostics'


def test_browser_artifact_records_missing_server_log_directory(tmp_path, monkeypatch):
    monkeypatch.setenv('RUNNER_TEMP', str(tmp_path / 'runner'))
    startup_log = tmp_path / 'startup.log'
    startup_log.write_text('startup failed early', encoding='utf-8')

    smoke._preserve_browser_server_diagnostics(
        startup_log=startup_log, data_directory=tmp_path / 'missing-data',
    )

    preserved = tmp_path / 'runner' / 'metalist-browser-results' / 'server-logs'
    assert (preserved / 'startup.log').read_text(encoding='utf-8') == 'startup failed early'
    unavailable = (preserved / 'server-logs-unavailable.txt').read_text(encoding='utf-8')
    assert 'Backend log directory was not created' in unavailable
