from starlette.requests import Request

from app.login_security import LoginFailureGuard, resolve_client_ip
from app.schemas import LoginSecuritySettings


def _request(client: str, xff: str | None = None, x_real: str | None = None) -> Request:
    headers = []
    if xff is not None:
        headers.append((b'x-forwarded-for', xff.encode()))
    if x_real is not None:
        headers.append((b'x-real-ip', x_real.encode()))
    return Request({
        'type': 'http',
        'method': 'GET',
        'scheme': 'https',
        'path': '/',
        'raw_path': b'/',
        'query_string': b'',
        'headers': headers,
        'client': (client, 12345),
        'server': ('testserver', 443),
    })


def test_resolve_client_ip_through_explicit_trusted_traefik() -> None:
    request = _request('172.21.0.4', '203.0.113.9, 192.168.178.247', '192.168.178.247')
    info = resolve_client_ip(request, ['192.168.178.247'])
    assert info.direct_ip == '172.21.0.4'
    assert info.resolved_client_ip == '203.0.113.9'


def test_untrusted_proxy_is_not_peeled_from_forwarded_chain() -> None:
    request = _request('172.21.0.4', '203.0.113.9, 192.168.178.247')
    info = resolve_client_ip(request, [])
    assert info.resolved_client_ip == '192.168.178.247'


def test_direct_frontend_access_does_not_trust_spoofed_leftmost_xff() -> None:
    request = _request('172.21.0.4', '198.51.100.77, 192.168.178.50')
    info = resolve_client_ip(request, ['192.168.178.247'])
    assert info.resolved_client_ip == '192.168.178.50'


def test_login_failure_guard_blocks_and_clears() -> None:
    guard = LoginFailureGuard()
    settings = LoginSecuritySettings(enabled=True, max_failed_attempts=3, block_minutes=15)
    assert guard.record_failure('203.0.113.9', settings)[:2] == (1, False)
    assert guard.record_failure('203.0.113.9', settings)[:2] == (2, False)
    count, newly_blocked, retry_after = guard.record_failure('203.0.113.9', settings)
    assert count == 3
    assert newly_blocked is True
    assert retry_after == 900
    assert guard.blocked_for('203.0.113.9') is not None
    guard.clear('203.0.113.9')
    assert guard.blocked_for('203.0.113.9') is None
