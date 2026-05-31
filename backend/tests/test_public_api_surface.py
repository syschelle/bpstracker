from fastapi.routing import APIRoute

from app.main import app
from app.security import require_admin


def test_sensitive_public_endpoints_are_not_registered() -> None:
    paths = {route.path for route in app.routes}

    assert '/api/devices/public/status' not in paths
    assert '/api/measurements/public/latest' not in paths
    assert '/api/measurements/public/summary' in paths


def _route(path: str, method: str) -> APIRoute:
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path == path and method in route.methods:
            return route
    raise AssertionError(f'route not found: {method} {path}')


def test_kindle_control_endpoints_are_admin_only() -> None:
    for path, method in [('/api/kindle/refresh', 'POST'), ('/api/kindle/meta', 'GET')]:
        route = _route(path, method)
        assert any(dependency.call is require_admin for dependency in route.dependant.dependencies)


def test_kindle_display_png_remains_public_cache_only_endpoint() -> None:
    route = _route('/api/kindle/display.png', 'GET')
        
    assert not any(dependency.call is require_admin for dependency in route.dependant.dependencies)
