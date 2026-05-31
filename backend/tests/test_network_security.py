import socket

import pytest

from app.network_security import OutboundHostError, normalize_outbound_http_host, resolve_lan_http_target


def test_normalize_outbound_host_accepts_host_and_optional_port() -> None:
    assert normalize_outbound_http_host(' http://192.168.178.50:8080/ ') == '192.168.178.50:8080'
    assert normalize_outbound_http_host('shelly-keller.local') == 'shelly-keller.local'


@pytest.mark.parametrize('host', [
    'http://192.168.178.50/data.json',
    'http://user:pass@192.168.178.50',
    'ftp://192.168.178.50',
])
def test_normalize_outbound_host_rejects_url_payloads(host: str) -> None:
    with pytest.raises(OutboundHostError):
        normalize_outbound_http_host(host)


@pytest.mark.parametrize('host', [
    '127.0.0.1',
    '169.254.169.254',
    '8.8.8.8',
    '0.0.0.0',
])
def test_resolve_lan_http_target_rejects_non_lan_literals(host: str) -> None:
    with pytest.raises(OutboundHostError):
        resolve_lan_http_target(host)


def test_resolve_lan_http_target_allows_private_lan_literal() -> None:
    target = resolve_lan_http_target('192.168.178.50:8080')

    assert target.url_authority == '192.168.178.50:8080'
    assert target.host_header == '192.168.178.50:8080'


def test_resolve_lan_http_target_rejects_hostnames_with_public_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_getaddrinfo(*_args, **_kwargs):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('192.168.178.50', 80)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('8.8.8.8', 80)),
        ]

    monkeypatch.setattr(socket, 'getaddrinfo', fake_getaddrinfo)

    with pytest.raises(OutboundHostError):
        resolve_lan_http_target('shelly.example')
