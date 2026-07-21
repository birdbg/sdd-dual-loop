from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_list_users_returns_existing_users() -> None:
    response = client.get("/users")

    assert response.status_code == 200
    assert response.json() == [
        {"id": 1, "username": "alice", "email": "alice@example.com"},
        {"id": 2, "username": "bob", "email": "bob@example.com"},
    ]
