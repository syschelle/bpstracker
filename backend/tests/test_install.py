import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.models import AppSetting, Base, User, UserRole
from app.routers.install import create_initial_admin, install_required
from app.schemas import InstallAdminRequest
from app.security import verify_password


@pytest.fixture()
def db_session():
    engine = create_engine('sqlite+pysqlite:///:memory:')
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as db:
        yield db


def test_install_required_until_admin_password_exists(db_session):
    assert install_required(db_session) is True

    create_initial_admin(
        InstallAdminRequest(username='solaradmin', password='SehrSicher123!', confirm_password='SehrSicher123!', secret_key=get_settings().secret_key, language='en'),
        db_session,
    )

    admin = db_session.query(User).filter(User.role == UserRole.admin).one()
    assert admin.username == 'solaradmin'
    assert admin.is_active is True
    assert verify_password('SehrSicher123!', admin.password_hash)
    assert install_required(db_session) is False

    ui = db_session.get(AppSetting, 'ui')
    assert ui is not None
    assert ui.value['language'] == 'en'


def test_install_rejects_wrong_secret_key(db_session):
    with pytest.raises(HTTPException) as excinfo:
        create_initial_admin(
            InstallAdminRequest(
                username='solaradmin',
                password='SehrSicher123!',
                confirm_password='SehrSicher123!',
                secret_key='wrong-secret',
                language='de',
            ),
            db_session,
        )

    assert excinfo.value.status_code == 403
    assert install_required(db_session) is True


def test_install_endpoint_disabled_after_admin_exists(db_session):
    create_initial_admin(
        InstallAdminRequest(username='solaradmin', password='SehrSicher123!', confirm_password='SehrSicher123!', secret_key=get_settings().secret_key, language='en'),
        db_session,
    )

    with pytest.raises(HTTPException) as excinfo:
        create_initial_admin(
            InstallAdminRequest(username='other', password='NochSicherer123!', confirm_password='NochSicherer123!', secret_key=get_settings().secret_key, language='de'),
            db_session,
        )

    assert excinfo.value.status_code == 404
