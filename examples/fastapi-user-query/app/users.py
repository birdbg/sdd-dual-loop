"""Small in-memory user store for the existing example application."""

from pydantic import BaseModel


class User(BaseModel):
    id: int
    username: str
    email: str


_USERS = (
    User(id=1, username="alice", email="alice@example.com"),
    User(id=2, username="bob", email="bob@example.com"),
)


def list_users() -> list[User]:
    return list(_USERS)
