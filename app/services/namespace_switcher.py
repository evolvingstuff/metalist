from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from http.client import HTTPConnection
from pathlib import Path
import json
import socket
import subprocess
import sys
import time

import app.server_runtime as server_runtime
from app.server_runtime import NamespaceLaunchProfile
from app.server_runtime import load_all_namespace_launch_profiles
from app.server_runtime import resolve_api_prefix
from app.server_runtime import resolve_backend_connect_host
from app.server_runtime import resolve_local_browser_host
from app.server_runtime import resolve_main_server_config
from app.server_runtime import resolve_namespaced_database_path
from app.server_runtime import resolve_namespaces_directory
from app.server_runtime import resolve_namespace_launch_defaults
from app.server_runtime import save_namespace_launch_profile
from app.server_runtime import validate_namespace


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PLACEHOLDER_NEW_NAMESPACE = "new-namespace"
_LAUNCH_READY_TIMEOUT_SECONDS = 12.0
_PORT_PROBE_TIMEOUT_SECONDS = 0.75
_READY_POLL_INTERVAL_SECONDS = 0.25
_PROBE_TAB_ID = "namespace-switcher-probe"


@dataclass(frozen=True)
class NamespacePortReservation:
    namespace: str
    service: str
    port: int
    source: str


@dataclass(frozen=True)
class NamespaceCatalogEntry:
    namespace: str
    is_current: bool
    database_exists: bool
    has_launch_profile: bool
    saved_profile: NamespaceLaunchProfile | None
    default_profile: NamespaceLaunchProfile


@dataclass(frozen=True)
class NamespaceOpenResult:
    namespace: str
    action: str
    url: str
    saved_profile: NamespaceLaunchProfile
    saved_for_next_launch: bool
    message: str


def build_namespace_catalog(
    *,
    environ: Mapping[str, str],
    current_namespace: str | None,
) -> dict[str, object]:
    current_profile = _build_current_profile(
        environ=environ,
        current_namespace=current_namespace,
    )
    saved_profiles = _load_saved_profiles_by_namespace()
    known_namespaces = _discover_namespaces(
        saved_profiles=saved_profiles,
        current_namespace=current_namespace,
    )
    supports_https = _supports_https(environ=environ)
    entries: list[dict[str, object]] = []
    for namespace in known_namespaces:
        occupied_ports = _occupied_ports(
            saved_profiles=saved_profiles,
            current_profile=current_profile,
            ignore_namespace=namespace,
        )
        saved_profile = saved_profiles.get(namespace)
        default_profile = _build_default_profile(
            namespace=namespace,
            saved_profile=saved_profile,
            current_profile=current_profile,
            occupied_ports=occupied_ports,
            supports_https=supports_https,
        )
        entry = NamespaceCatalogEntry(
            namespace=namespace,
            is_current=namespace == current_namespace,
            database_exists=resolve_namespaced_database_path(namespace=namespace).is_file(),
            has_launch_profile=saved_profile is not None,
            saved_profile=saved_profile,
            default_profile=default_profile,
        )
        entries.append(_serialize_catalog_entry(entry=entry))
    current_url = _build_browser_url(
        environ=environ,
        port=None if current_profile is None else current_profile.port,
    )
    new_namespace_profile = _suggest_profile(
        namespace=_PLACEHOLDER_NEW_NAMESPACE,
        occupied_ports=_occupied_ports(
            saved_profiles=saved_profiles,
            current_profile=current_profile,
            ignore_namespace=None,
        ),
        supports_https=supports_https,
    )
    return {
        "current_namespace": current_namespace,
        "current_profile": None if current_profile is None else _serialize_profile(profile=current_profile),
        "current_url": current_url,
        "supports_https": supports_https,
        "reserved_ports": [
            _serialize_reservation(reservation=reservation)
            for reservation in _reserved_ports(
                saved_profiles=saved_profiles,
                current_profile=current_profile,
                ignore_namespace=None,
            )
        ],
        "new_namespace_profile": _serialize_profile(profile=new_namespace_profile),
        "namespaces": entries,
    }


def open_or_launch_namespace(
    *,
    environ: Mapping[str, str],
    current_namespace: str | None,
    namespace: str,
    port: int,
    https_port: int | None,
    mcp_port: int,
) -> NamespaceOpenResult:
    normalized_namespace = validate_namespace(namespace=namespace)
    current_profile = _build_current_profile(
        environ=environ,
        current_namespace=current_namespace,
    )
    supports_https = _supports_https(environ=environ)
    chosen_profile = _build_requested_profile(
        namespace=normalized_namespace,
        port=port,
        https_port=https_port,
        mcp_port=mcp_port,
        supports_https=supports_https,
    )
    saved_profiles = _load_saved_profiles_by_namespace()
    saved_profile = saved_profiles.get(normalized_namespace)
    _assert_profile_is_conflict_free(
        chosen_profile=chosen_profile,
        saved_profiles=saved_profiles,
        current_profile=current_profile,
    )
    running_port = _find_running_namespace_port(
        environ=environ,
        namespace=normalized_namespace,
        chosen_profile=chosen_profile,
        saved_profile=saved_profile,
        current_profile=current_profile,
    )
    saved_for_next_launch = _save_profile_if_needed(
        chosen_profile=chosen_profile,
        saved_profile=saved_profile,
    )
    if running_port is not None:
        running_url = _build_browser_url(environ=environ, port=running_port)
        assert running_url is not None
        if saved_for_next_launch:
            message = (
                f"Namespace {normalized_namespace} is already running. "
                "Saved the new ports for the next launch."
            )
        else:
            message = f"Namespace {normalized_namespace} is already running."
        return NamespaceOpenResult(
            namespace=normalized_namespace,
            action="opened-running",
            url=running_url,
            saved_profile=chosen_profile,
            saved_for_next_launch=saved_for_next_launch,
            message=message,
        )
    _assert_ports_are_available_for_launch(
        environ=environ,
        namespace=normalized_namespace,
        chosen_profile=chosen_profile,
    )
    _launch_namespace_process(
        environ=environ,
        chosen_profile=chosen_profile,
    )
    _wait_for_namespace_ready(
        environ=environ,
        namespace=normalized_namespace,
        port=chosen_profile.port,
    )
    launched_url = _build_browser_url(environ=environ, port=chosen_profile.port)
    assert launched_url is not None
    return NamespaceOpenResult(
        namespace=normalized_namespace,
        action="launched",
        url=launched_url,
        saved_profile=chosen_profile,
        saved_for_next_launch=saved_for_next_launch,
        message=f"Started namespace {normalized_namespace}.",
    )


def _serialize_catalog_entry(*, entry: NamespaceCatalogEntry) -> dict[str, object]:
    return {
        "namespace": entry.namespace,
        "is_current": entry.is_current,
        "database_exists": entry.database_exists,
        "has_launch_profile": entry.has_launch_profile,
        "saved_profile": None if entry.saved_profile is None else _serialize_profile(profile=entry.saved_profile),
        "default_profile": _serialize_profile(profile=entry.default_profile),
    }


def _serialize_reservation(*, reservation: NamespacePortReservation) -> dict[str, object]:
    return {
        "namespace": reservation.namespace,
        "service": reservation.service,
        "port": reservation.port,
        "source": reservation.source,
    }


def _serialize_profile(*, profile: NamespaceLaunchProfile) -> dict[str, object]:
    return {
        "namespace": profile.namespace,
        "port": profile.port,
        "https_port": profile.https_port,
        "mcp_port": profile.mcp_port,
    }


def _load_saved_profiles_by_namespace() -> dict[str, NamespaceLaunchProfile]:
    profiles = load_all_namespace_launch_profiles()
    profiles_by_namespace: dict[str, NamespaceLaunchProfile] = {}
    for profile in profiles:
        profiles_by_namespace[profile.namespace] = profile
    return profiles_by_namespace


def _discover_namespaces(
    *,
    saved_profiles: Mapping[str, NamespaceLaunchProfile],
    current_namespace: str | None,
) -> list[str]:
    discovered = {server_runtime._DEFAULT_NAMESPACE}
    for namespace in saved_profiles:
        discovered.add(namespace)
    if current_namespace is not None:
        discovered.add(validate_namespace(namespace=current_namespace))
    namespaces_directory = resolve_namespaces_directory()
    if namespaces_directory.is_dir():
        for child in namespaces_directory.iterdir():
            if not child.is_dir():
                continue
            try:
                discovered.add(validate_namespace(namespace=child.name))
            except RuntimeError:
                continue
    ordered_namespaces = sorted(discovered)
    if server_runtime._DEFAULT_NAMESPACE in ordered_namespaces:
        ordered_namespaces.remove(server_runtime._DEFAULT_NAMESPACE)
        ordered_namespaces.insert(0, server_runtime._DEFAULT_NAMESPACE)
    return ordered_namespaces


def _supports_https(*, environ: Mapping[str, str]) -> bool:
    main_server_config = resolve_main_server_config(environ=environ)
    return main_server_config.https_port is not None


def _build_current_profile(
    *,
    environ: Mapping[str, str],
    current_namespace: str | None,
) -> NamespaceLaunchProfile | None:
    if current_namespace is None:
        return None
    normalized_namespace = validate_namespace(namespace=current_namespace)
    main_server_config = resolve_main_server_config(environ=environ)
    launch_defaults = resolve_namespace_launch_defaults(
        namespace=normalized_namespace,
        environ=environ,
    )
    return NamespaceLaunchProfile(
        namespace=normalized_namespace,
        port=main_server_config.port,
        https_port=main_server_config.https_port,
        mcp_port=launch_defaults.mcp_port,
    )


def _build_default_profile(
    *,
    namespace: str,
    saved_profile: NamespaceLaunchProfile | None,
    current_profile: NamespaceLaunchProfile | None,
    occupied_ports: set[int],
    supports_https: bool,
) -> NamespaceLaunchProfile:
    if current_profile is not None and current_profile.namespace == namespace:
        return current_profile
    if saved_profile is None:
        return _suggest_profile(
            namespace=namespace,
            occupied_ports=occupied_ports,
            supports_https=supports_https,
        )
    working_ports = set(occupied_ports)
    http_port = saved_profile.port
    if http_port is None:
        http_port = _next_free_port(
            start_port=server_runtime._DEFAULT_HTTP_PORT,
            occupied_ports=working_ports,
        )
    working_ports.add(http_port)
    if supports_https:
        https_port = saved_profile.https_port
        if https_port is None:
            https_port = _next_free_port(
                start_port=server_runtime._DEFAULT_HTTPS_PORT,
                occupied_ports=working_ports,
            )
        working_ports.add(https_port)
    else:
        https_port = None
    mcp_port = saved_profile.mcp_port
    if mcp_port is None:
        mcp_port = _next_free_port(
            start_port=server_runtime._DEFAULT_MCP_AGENT_WEB_PORT,
            occupied_ports=working_ports,
        )
    return NamespaceLaunchProfile(
        namespace=namespace,
        port=http_port,
        https_port=https_port,
        mcp_port=mcp_port,
    )


def _suggest_profile(
    *,
    namespace: str,
    occupied_ports: set[int],
    supports_https: bool,
) -> NamespaceLaunchProfile:
    working_ports = set(occupied_ports)
    http_port = _next_free_port(
        start_port=server_runtime._DEFAULT_HTTP_PORT,
        occupied_ports=working_ports,
    )
    working_ports.add(http_port)
    if supports_https:
        https_port = _next_free_port(
            start_port=server_runtime._DEFAULT_HTTPS_PORT,
            occupied_ports=working_ports,
        )
        working_ports.add(https_port)
    else:
        https_port = None
    mcp_port = _next_free_port(
        start_port=server_runtime._DEFAULT_MCP_AGENT_WEB_PORT,
        occupied_ports=working_ports,
    )
    return NamespaceLaunchProfile(
        namespace=namespace,
        port=http_port,
        https_port=https_port,
        mcp_port=mcp_port,
    )


def _next_free_port(*, start_port: int, occupied_ports: set[int]) -> int:
    port = start_port
    while port in occupied_ports:
        port += 1
    return port


def _reserved_ports(
    *,
    saved_profiles: Mapping[str, NamespaceLaunchProfile],
    current_profile: NamespaceLaunchProfile | None,
    ignore_namespace: str | None,
) -> list[NamespacePortReservation]:
    reservations: list[NamespacePortReservation] = []
    seen: set[tuple[str, str, int, str]] = set()
    for profile in saved_profiles.values():
        if ignore_namespace is not None and profile.namespace == ignore_namespace:
            continue
        _append_profile_reservations(
            reservations=reservations,
            seen=seen,
            profile=profile,
            source="saved_profile",
        )
    if current_profile is not None:
        if ignore_namespace is None or current_profile.namespace != ignore_namespace:
            _append_profile_reservations(
                reservations=reservations,
                seen=seen,
                profile=current_profile,
                source="current_runtime",
            )
    reservations.sort(key=lambda reservation: (reservation.port, reservation.namespace, reservation.service))
    return reservations


def _append_profile_reservations(
    *,
    reservations: list[NamespacePortReservation],
    seen: set[tuple[str, str, int, str]],
    profile: NamespaceLaunchProfile,
    source: str,
) -> None:
    port_pairs = [
        ("http", profile.port),
        ("https", profile.https_port),
        ("mcp", profile.mcp_port),
    ]
    for service, port in port_pairs:
        if port is None:
            continue
        key = (profile.namespace, service, port, source)
        if key in seen:
            continue
        seen.add(key)
        reservations.append(
            NamespacePortReservation(
                namespace=profile.namespace,
                service=service,
                port=port,
                source=source,
            )
        )


def _occupied_ports(
    *,
    saved_profiles: Mapping[str, NamespaceLaunchProfile],
    current_profile: NamespaceLaunchProfile | None,
    ignore_namespace: str | None,
) -> set[int]:
    occupied: set[int] = set()
    for reservation in _reserved_ports(
        saved_profiles=saved_profiles,
        current_profile=current_profile,
        ignore_namespace=ignore_namespace,
    ):
        occupied.add(reservation.port)
    return occupied


def _build_requested_profile(
    *,
    namespace: str,
    port: int,
    https_port: int | None,
    mcp_port: int,
    supports_https: bool,
) -> NamespaceLaunchProfile:
    normalized_port = _validate_required_port(name="port", value=port)
    normalized_mcp_port = _validate_required_port(name="mcp_port", value=mcp_port)
    if supports_https:
        if https_port is None:
            raise RuntimeError("HTTPS port is required because TLS is enabled for this app")
        normalized_https_port = _validate_required_port(name="https_port", value=https_port)
    else:
        if https_port is not None:
            raise RuntimeError("HTTPS port is not available because TLS is not configured")
        normalized_https_port = None
    return NamespaceLaunchProfile(
        namespace=namespace,
        port=normalized_port,
        https_port=normalized_https_port,
        mcp_port=normalized_mcp_port,
    )


def _validate_required_port(*, name: str, value: int) -> int:
    if not isinstance(value, int):
        raise TypeError(f"{name} must be an int, got {type(value)}")
    if not 0 < value < 65536:
        raise RuntimeError(f"{name} must be between 1 and 65535, got: {value}")
    return value


def _assert_profile_is_conflict_free(
    *,
    chosen_profile: NamespaceLaunchProfile,
    saved_profiles: Mapping[str, NamespaceLaunchProfile],
    current_profile: NamespaceLaunchProfile | None,
) -> None:
    service_pairs = [
        ("http", chosen_profile.port),
        ("https", chosen_profile.https_port),
        ("mcp", chosen_profile.mcp_port),
    ]
    seen_ports: dict[int, str] = {}
    for service, port in service_pairs:
        if port is None:
            continue
        if port in seen_ports:
            other_service = seen_ports[port]
            raise RuntimeError(
                f"{service.upper()} port {port} conflicts with {other_service.upper()} port "
                f"for namespace {chosen_profile.namespace}"
            )
        seen_ports[port] = service
    reservations = _reserved_ports(
        saved_profiles=saved_profiles,
        current_profile=current_profile,
        ignore_namespace=chosen_profile.namespace,
    )
    conflicts_by_port = {reservation.port: reservation for reservation in reservations}
    for service, port in service_pairs:
        if port is None:
            continue
        if port not in conflicts_by_port:
            continue
        reservation = conflicts_by_port[port]
        raise RuntimeError(
            f"{service.upper()} port {port} conflicts with "
            f"{reservation.service.upper()} port reserved for namespace {reservation.namespace}"
        )


def _find_running_namespace_port(
    *,
    environ: Mapping[str, str],
    namespace: str,
    chosen_profile: NamespaceLaunchProfile,
    saved_profile: NamespaceLaunchProfile | None,
    current_profile: NamespaceLaunchProfile | None,
) -> int | None:
    main_server_config = resolve_main_server_config(environ=environ)
    connect_host = resolve_backend_connect_host(host=main_server_config.host)
    api_prefix = resolve_api_prefix(environ=environ)
    candidate_ports: list[int] = [chosen_profile.port]
    if saved_profile is not None and saved_profile.port is not None:
        candidate_ports.append(saved_profile.port)
    if current_profile is not None and current_profile.namespace == namespace:
        candidate_ports.append(current_profile.port)
    checked_ports: set[int] = set()
    for candidate_port in candidate_ports:
        if candidate_port in checked_ports:
            continue
        checked_ports.add(candidate_port)
        status_payload = _probe_namespace_status(
            host=connect_host,
            port=candidate_port,
            api_prefix=api_prefix,
        )
        if status_payload is None:
            continue
        payload_namespace = status_payload.get("namespace")
        if payload_namespace == namespace:
            return candidate_port
    return None


def _assert_ports_are_available_for_launch(
    *,
    environ: Mapping[str, str],
    namespace: str,
    chosen_profile: NamespaceLaunchProfile,
) -> None:
    main_server_config = resolve_main_server_config(environ=environ)
    connect_host = resolve_backend_connect_host(host=main_server_config.host)
    api_prefix = resolve_api_prefix(environ=environ)
    http_status = _probe_namespace_status(
        host=connect_host,
        port=chosen_profile.port,
        api_prefix=api_prefix,
    )
    if http_status is not None:
        running_namespace = http_status.get("namespace")
        if running_namespace == namespace:
            return
        if isinstance(running_namespace, str) and running_namespace != "":
            raise RuntimeError(
                f"HTTP port {chosen_profile.port} is already serving namespace {running_namespace}"
            )
        raise RuntimeError(f"HTTP port {chosen_profile.port} is already serving another process")
    if _is_tcp_port_open(host=connect_host, port=chosen_profile.port):
        raise RuntimeError(f"HTTP port {chosen_profile.port} is already in use")
    other_ports = [
        ("HTTPS", chosen_profile.https_port),
        ("MCP", chosen_profile.mcp_port),
    ]
    for service, port in other_ports:
        if port is None:
            continue
        if _is_tcp_port_open(host=connect_host, port=port):
            raise RuntimeError(f"{service} port {port} is already in use")


def _save_profile_if_needed(
    *,
    chosen_profile: NamespaceLaunchProfile,
    saved_profile: NamespaceLaunchProfile | None,
) -> bool:
    if saved_profile is not None:
        if (
            saved_profile.port == chosen_profile.port
            and saved_profile.https_port == chosen_profile.https_port
            and saved_profile.mcp_port == chosen_profile.mcp_port
        ):
            return False
    save_namespace_launch_profile(
        namespace=chosen_profile.namespace,
        port=chosen_profile.port,
        https_port=chosen_profile.https_port,
        mcp_port=chosen_profile.mcp_port,
    )
    return True


def _launch_namespace_process(
    *,
    environ: Mapping[str, str],
    chosen_profile: NamespaceLaunchProfile,
) -> None:
    child_environ = dict(environ)
    for name in (
        "METALIST_NAMESPACE",
        "METALIST_PORT",
        "METALIST_HTTPS_PORT",
        "MCP_AGENT_WEB_PORT",
    ):
        if name in child_environ:
            del child_environ[name]
    command = [
        sys.executable,
        str(_PROJECT_ROOT / "main.py"),
        "--namespace",
        chosen_profile.namespace,
        "--port",
        str(chosen_profile.port),
        "--mcp-port",
        str(chosen_profile.mcp_port),
    ]
    if chosen_profile.https_port is not None:
        command.extend(["--https-port", str(chosen_profile.https_port)])
    logs_directory = _PROJECT_ROOT / "logs"
    logs_directory.mkdir(parents=True, exist_ok=True)
    log_path = logs_directory / f"namespace-{chosen_profile.namespace}.log"
    log_handle = open(log_path, "ab")
    try:
        subprocess.Popen(
            command,
            cwd=str(_PROJECT_ROOT),
            env=child_environ,
            stdout=log_handle,
            stderr=log_handle,
            start_new_session=True,
        )
    finally:
        log_handle.close()


def _wait_for_namespace_ready(
    *,
    environ: Mapping[str, str],
    namespace: str,
    port: int,
) -> None:
    main_server_config = resolve_main_server_config(environ=environ)
    connect_host = resolve_backend_connect_host(host=main_server_config.host)
    api_prefix = resolve_api_prefix(environ=environ)
    deadline = time.monotonic() + _LAUNCH_READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        status_payload = _probe_namespace_status(
            host=connect_host,
            port=port,
            api_prefix=api_prefix,
        )
        if status_payload is not None and status_payload.get("namespace") == namespace:
            return
        time.sleep(_READY_POLL_INTERVAL_SECONDS)
    raise RuntimeError(f"Timed out waiting for namespace {namespace} on port {port}")


def _probe_namespace_status(
    *,
    host: str,
    port: int,
    api_prefix: str,
) -> dict[str, object] | None:
    connection = HTTPConnection(host=host, port=port, timeout=_PORT_PROBE_TIMEOUT_SECONDS)
    try:
        connection.request(
            "GET",
            f"{api_prefix}/auth/status",
            headers={"X-Metalist-Tab-Id": _PROBE_TAB_ID},
        )
        response = connection.getresponse()
        if response.status != 200:
            return None
        payload_bytes = response.read()
    except OSError:
        return None
    finally:
        connection.close()
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _is_tcp_port_open(*, host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=_PORT_PROBE_TIMEOUT_SECONDS):
            return True
    except OSError:
        return False


def _build_browser_url(
    *,
    environ: Mapping[str, str],
    port: int | None,
) -> str | None:
    if port is None:
        return None
    main_server_config = resolve_main_server_config(environ=environ)
    browser_host = resolve_local_browser_host(host=main_server_config.host)
    return f"http://{browser_host}:{port}"
