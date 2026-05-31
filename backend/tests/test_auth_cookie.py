from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models import User, UserRole
from app.routers import auth
from app.security import password_hash


@pytest.fixture()
def client() -> TestClient:
    engine = create_engine('sqlite+pysqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)

    with SessionLocal() as db:
        db.add(
            User(
                username='admin',
                password_hash=password_hash('SehrSicher123!'),
                role=UserRole.admin,
                is_active=True,
                totp_enabled=False,
            )
        )
        db.commit()

    def override_get_db():
        with SessionLocal() as db:
            yield db

    app = FastAPI()
    app.dependency_overrides[get_db] = override_get_db
    app.include_router(auth.router)
    return TestClient(app)


def test_login_sets_httponly_cookie_without_returning_access_token(client: TestClient) -> None:
    response = client.post('/api/auth/login', json={'username': 'admin', 'password': 'SehrSicher123!'})

    assert response.status_code == 200
    assert response.json() == {'access_token': None, 'token_type': 'cookie', 'requires_2fa': False, 'challenge_token': None}
    cookie_header = response.headers['set-cookie']
    assert 'bpstracker_access_token=' in cookie_header
    assert 'HttpOnly' in cookie_header
    assert 'SameSite=lax' in cookie_header

    me = client.get('/api/auth/me')
    assert me.status_code == 200
    assert me.json()['username'] == 'admin'


def test_logout_clears_auth_cookie(client: TestClient) -> None:
    assert client.post('/api/auth/login', json={'username': 'admin', 'password': 'SehrSicher123!'}).status_code == 200

    response = client.post('/api/auth/logout')

    assert response.status_code == 204
    assert 'bpstracker_access_token=' in response.headers['set-cookie']
    assert 'Max-Age=0' in response.headers['set-cookie']
