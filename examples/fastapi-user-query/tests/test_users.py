import pytest
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


def test_get_user_returns_existing_user() -> None:
    response = client.get("/users/1")

    assert response.status_code == 200
    assert response.json() == {
        "id": 1,
        "username": "alice",
        "email": "alice@example.com",
    }


def test_get_user_returns_404_for_missing_user() -> None:
    response = client.get("/users/999")

    assert response.status_code == 404


@pytest.mark.parametrize("user_id", ["0", "-1", "not-an-int"])
def test_get_user_rejects_invalid_id(user_id: str) -> None:
    assert client.get(f"/users/{user_id}").status_code == 422
