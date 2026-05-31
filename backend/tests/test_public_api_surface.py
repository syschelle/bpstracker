from app.main import app


def test_sensitive_public_endpoints_are_not_registered() -> None:
    paths = {route.path for route in app.routes}

    assert '/api/devices/public/status' not in paths
    assert '/api/measurements/public/latest' not in paths
    assert '/api/measurements/public/summary' in paths
