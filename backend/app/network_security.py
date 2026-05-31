from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit


class OutboundHostError(ValueError):
    """Raised when a configured outbound device host is not safe to call."""


@dataclass(frozen=True)
class LanHttpTarget:
    original_host: str
    hostname: str
    port: int | None
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address

    @property
    def url_authority(self) -> str:
        host = f'[{self.ip.compressed}]' if self.ip.version == 6 else self.ip.compressed
        return f'{host}:{self.port}' if self.port else host

    @property
    def host_header(self) -> str:
        host = f'[{self.hostname}]' if ':' in self.hostname and not self.hostname.startswith('[') else self.hostname
        return f'{host}:{self.port}' if self.port else host


def normalize_outbound_http_host(value: str | None) -> str | None:
    """Normalize a user-entered device host without accepting arbitrary URLs.

    Shelly and Luftdaten devices are configured as a host/IP plus optional port.
    For backwards compatibility, plain ``http://host`` input is accepted, but
    credentials, paths, queries and fragments are rejected instead of being
    silently stripped.
    """
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None

    if '://' in raw:
        parsed = urlsplit(raw)
        if parsed.scheme.lower() not in {'http', 'https'}:
            raise OutboundHostError('Nur HTTP(S)-Hostnamen sind erlaubt.')
        if parsed.username or parsed.password:
            raise OutboundHostError('Host darf keine Zugangsdaten enthalten.')
        if parsed.path not in {'', '/'} or parsed.query or parsed.fragment:
            raise OutboundHostError('Host darf keinen Pfad, Query-String oder Fragment enthalten.')
        host = parsed.hostname or ''
        port = parsed.port
    else:
        parsed = urlsplit(f'//{raw}')
        if parsed.username or parsed.password:
            raise OutboundHostError('Host darf keine Zugangsdaten enthalten.')
        if parsed.path not in {'', '/'} or parsed.query or parsed.fragment:
            raise OutboundHostError('Host darf keinen Pfad, Query-String oder Fragment enthalten.')
        host = parsed.hostname or ''
        port = parsed.port

    host = host.strip().rstrip('.')
    if not host:
        raise OutboundHostError('Host darf nicht leer sein.')
    if len(host) > 255:
        raise OutboundHostError('Host ist zu lang.')
    if any(char.isspace() for char in host):
        raise OutboundHostError('Host darf keine Leerzeichen enthalten.')
    if port is not None and not (1 <= port <= 65535):
        raise OutboundHostError('Port liegt außerhalb des erlaubten Bereichs.')

    # Keep IPv6 addresses bracketed when a port is present so later parsing is unambiguous.
    if ':' in host and port is not None:
        host_part = f'[{host}]'
    else:
        host_part = host
    return f'{host_part}:{port}' if port is not None else host_part


def _parse_host_port(host: str) -> tuple[str, int | None]:
    parsed = urlsplit(f'//{host}')
    if parsed.username or parsed.password or parsed.path not in {'', '/'} or parsed.query or parsed.fragment:
        raise OutboundHostError('Ungültiger Host.')
    hostname = (parsed.hostname or '').strip().rstrip('.')
    if not hostname:
        raise OutboundHostError('Host darf nicht leer sein.')
    try:
        port = parsed.port
    except ValueError as exc:
        raise OutboundHostError('Ungültiger Port.') from exc
    return hostname, port


def _is_allowed_lan_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    # Block localhost, unspecified, multicast and link-local. Link-local IPv4 includes
    # cloud metadata addresses such as 169.254.169.254 and should never be reachable
    # through device polling.
    if ip.is_loopback or ip.is_unspecified or ip.is_multicast or ip.is_link_local:
        return False
    if ip.version == 4:
        return ip in ipaddress.ip_network('10.0.0.0/8') or ip in ipaddress.ip_network('172.16.0.0/12') or ip in ipaddress.ip_network('192.168.0.0/16')
    # IPv6 Unique Local Addresses (fc00::/7) are the private IPv6 LAN range.
    return ip in ipaddress.ip_network('fc00::/7')


def resolve_lan_http_target(host: str) -> LanHttpTarget:
    normalized = normalize_outbound_http_host(host)
    if not normalized:
        raise OutboundHostError('Host darf nicht leer sein.')
    hostname, port = _parse_host_port(normalized)

    try:
        literal_ip = ipaddress.ip_address(hostname)
        addresses = [literal_ip]
    except ValueError:
        try:
            addrinfos = socket.getaddrinfo(hostname, port or 80, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise OutboundHostError(f'Host konnte nicht aufgelöst werden: {hostname}') from exc
        addresses = []
        for family, *_rest, sockaddr in addrinfos:
            if family not in {socket.AF_INET, socket.AF_INET6}:
                continue
            try:
                addresses.append(ipaddress.ip_address(sockaddr[0]))
            except ValueError:
                continue
        # Deduplicate while preserving order.
        addresses = list(dict.fromkeys(addresses))

    if not addresses:
        raise OutboundHostError(f'Host konnte nicht aufgelöst werden: {hostname}')

    blocked = [ip for ip in addresses if not _is_allowed_lan_ip(ip)]
    if blocked:
        blocked_text = ', '.join(ip.compressed for ip in blocked)
        raise OutboundHostError(f'Host zeigt nicht ausschließlich auf erlaubte LAN-Adressen: {blocked_text}')

    return LanHttpTarget(original_host=normalized, hostname=hostname, port=port, ip=addresses[0])


def lan_http_url(target: LanHttpTarget, path: str) -> str:
    if not path.startswith('/'):
        raise ValueError('path must start with /')
    return f'http://{target.url_authority}{path}'
