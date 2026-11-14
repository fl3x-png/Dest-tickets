import os
from pathlib import Path
import tempfile
import pytest
from fastapi.testclient import TestClient

tmp = tempfile.TemporaryDirectory()
os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(tmp.name) / 'test.db').replace('\\','/')
from backend.db import Base, engine, Session
from backend.models import User
from backend.app import app, hash_password

def pytest_sessionfinish(session, exitstatus):
    engine.dispose()
    tmp.cleanup()

@pytest.fixture(autouse=True)
def database():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    with Session() as db:
        db.add_all([User(username='admin', name='Тестовый администратор', password_hash=hash_password('Test-password-123!'), role='admin'),User(username='manager', name='Тестовый менеджер', password_hash=hash_password('Test-password-123!'), role='manager')]); db.commit()
    yield

def client_for(username):
    client = TestClient(app)
    result = client.post('/api/login',json={'username':username,'password':'Test-password-123!'},headers={'X-Requested-With':'Destination'})
    assert result.status_code == 200, result.text
    client.headers['X-CSRF-Token'] = result.json()['csrf']
    return client

@pytest.fixture
def admin():
    return client_for('admin')

@pytest.fixture
def manager():
    return client_for('manager')
