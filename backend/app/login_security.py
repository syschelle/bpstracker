from __future__ import annotations

from dataclasses import dataclass
from ipaddress import ip_address, ip_network
from threading import Lock
import time

from fastapi import Request
from sqlalchemy.orm import Session

from .config import get_settings
from .models import AppSetting
from .schemas import LoginSecuritySettings, LoginSecurityUpdate

LOGIN_SECURITY_SETTINGS_KEY = 'login_security'


def _clean_trusted_proxies(values: list[str] | None) -> list[str]:
    cleaned: list[str] = []
    for raw in values or []:
        text = str(raw or '').strip()
        if not text:
            continue
        try:
            if '/' in text:
                network = ip_network(text, strict=False)
            else:
                ip = ip_address(text)
                network = ip_network(f'{ip}/{32 if ip.version == 4 else 128}', strict=False)
        except ValueError as exc:
            raise ValueError(f'Invalid trusted proxy IP/CIDR: {text}') from exc
        normalized = str(network)
        if normalized not in cleaned:
            cleaned.append(normalized)
    return cleaned[:32]


def _trusted_proxies_from_env() -> list[str]:
    raw = get_settings().bpstracker_trusted_proxies
    values = [part.strip() for part in raw.replace(';', ',').split(',') if part.strip()]
    return _clean_trusted_proxies(values)


def normalize_login_security_settings(value: dict | None) -> LoginSecuritySettings:
    value = value or {}
    try:
        max_attempts = int(value.get('max_failed_attempts') or 5)
    except (TypeError, ValueError):
        max_attempts = 5
    try:
        block_minutes = int(value.get('block_minutes') or 15)
    except (TypeError, ValueError):
        block_minutes = 15
    trusted = _trusted_proxies_from_env()
    return LoginSecuritySettings(
        enabled=bool(value.get('enabled', False)),
        max_failed_attempts=max(3, min(20, max_attempts)),
        block_minutes=max(1, min(1440, block_minutes)),
        notify_on_block=bool(value.get('notify_on_block', False)),
        trusted_proxies=trusted,
    )


def get_login_security_settings(db: Session) -> LoginSecuritySettings:
    row = db.get(AppSetting, LOGIN_SECURITY_SETTINGS_KEY)
    return normalize_login_security_settings(row.value if row else None)


def save_login_security_settings(db: Session, settings: LoginSecurityUpdate) -> LoginSecuritySettings:
    normalized = normalize_login_security_settings(settings.model_dump())
    row = db.get(AppSetting, LOGIN_SECURITY_SETTINGS_KEY)
    # Trusted proxies are deliberately excluded from database/web-managed settings.
    # They define which upstream may assert a client address and therefore belong
    # exclusively to the protected deployment environment (.env).
    value = {
        'enabled': normalized.enabled,
        'max_failed_attempts': normalized.max_failed_attempts,
        'block_minutes': normalized.block_minutes,
        'notify_on_block': normalized.notify_on_block,
    }
    if row is None:
        row = AppSetting(key=LOGIN_SECURITY_SETTINGS_KEY, value=value)
        db.add(row)
    else:
        row.value = value
    return normalized


def _parse_ip(value: str | None) -> str | None:
    text = str(value or '').strip()
    if not text:
        return None
    # X-Forwarded-For values should contain bare IP addresses, but tolerate an
    # accidental IPv4 host:port suffix without accepting arbitrary hostnames.
    try:
        return str(ip_address(text))
    except ValueError:
        if text.count(':') == 1 and '.' in text:
            host, port = text.rsplit(':', 1)
            if port.isdigit():
                try:
                    return str(ip_address(host))
                except ValueError:
                    return None
        return None


def _trusted(ip_text: str, trusted_networks: list[str]) -> bool:
    try:
        ip = ip_address(ip_text)
    except ValueError:
        return False
    for network_text in trusted_networks:
        try:
            if ip in ip_network(network_text, strict=False):
                return True
        except ValueError:
            continue
    return False


@dataclass(frozen=True)
class ClientIpInfo:
    direct_ip: str
    x_real_ip: str | None
    x_forwarded_for: str | None
    forwarded_chain: list[str]
    resolved_client_ip: str
    trusted_proxies: list[str]
    immediate_proxy_accepted: bool

    def as_dict(self) -> dict:
        return {
            'direct_ip': self.direct_ip,
            'x_real_ip': self.x_real_ip,
            'x_forwarded_for': self.x_forwarded_for,
            'forwarded_chain': self.forwarded_chain,
            'resolved_client_ip': self.resolved_client_ip,
            'trusted_proxies': self.trusted_proxies,
            'immediate_proxy_accepted': self.immediate_proxy_accepted,
        }


def resolve_client_ip(request: Request, trusted_proxies: list[str] | None = None) -> ClientIpInfo:
    trusted = _clean_trusted_proxies(trusted_proxies)
    direct_ip = _parse_ip(request.client.host if request.client else None) or 'unknown'
    raw_xff = request.headers.get('x-forwarded-for')
    x_real = _parse_ip(request.headers.get('x-real-ip'))
    forwarded: list[str] = []
    if raw_xff:
        for part in raw_xff.split(','):
            parsed = _parse_ip(part)
            if parsed:
                forwarded.append(parsed)

    # The backend port is only exposed inside the Compose network. Therefore the
    # immediate ASGI peer is the bundled frontend nginx and may be accepted as the
    # transport proxy. We still do NOT trust addresses further left unless the admin
    # explicitly configures them below (typically the Traefik host IP/CIDR).
    immediate_proxy_accepted = bool(forwarded and direct_ip != 'unknown')
    resolved = direct_ip
    if forwarded:
        for candidate in reversed(forwarded):
            if _trusted(candidate, trusted):
                continue
            resolved = candidate
            break
        else:
            resolved = forwarded[0]

    return ClientIpInfo(
        direct_ip=direct_ip,
        x_real_ip=x_real,
        x_forwarded_for=raw_xff,
        forwarded_chain=forwarded,
        resolved_client_ip=resolved,
        trusted_proxies=trusted,
        immediate_proxy_accepted=immediate_proxy_accepted,
    )


@dataclass
class _FailureState:
    count: int
    first_failure_at: float
    blocked_until: float = 0.0


class LoginFailureGuard:
    def __init__(self) -> None:
        self._states: dict[str, _FailureState] = {}
        self._lock = Lock()

    def blocked_for(self, source_ip: str) -> int | None:
        now = time.time()
        with self._lock:
            state = self._states.get(source_ip)
            if not state:
                return None
            if state.blocked_until > now:
                return max(1, int(state.blocked_until - now))
            if state.blocked_until:
                self._states.pop(source_ip, None)
            return None

    def record_failure(self, source_ip: str, settings: LoginSecuritySettings) -> tuple[int, bool, int | None]:
        now = time.time()
        reset_seconds = max(60, settings.block_minutes * 60)
        with self._lock:
            state = self._states.get(source_ip)
            if state is None or (not state.blocked_until and now - state.first_failure_at > reset_seconds):
                state = _FailureState(count=0, first_failure_at=now)
                self._states[source_ip] = state
            if state.blocked_until > now:
                return state.count, False, max(1, int(state.blocked_until - now))
            state.count += 1
            newly_blocked = state.count >= settings.max_failed_attempts
            if newly_blocked:
                state.blocked_until = now + settings.block_minutes * 60
                return state.count, True, settings.block_minutes * 60
            return state.count, False, None

    def clear(self, source_ip: str) -> None:
        with self._lock:
            self._states.pop(source_ip, None)

    def reset(self) -> None:
        with self._lock:
            self._states.clear()


login_failure_guard = LoginFailureGuard()
