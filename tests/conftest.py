from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from studio.server import create_app
from fake_engine import DemoEngine

@pytest.fixture
def client(tmp_path):
    app=create_app(Path(__file__).resolve().parents[1],tmp_path,demo=True,engine=DemoEngine())
    with TestClient(app) as c:
        c.headers['x-studio-token']=c.get('/api/bootstrap').json()['token']
        yield c
