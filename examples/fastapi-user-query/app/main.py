"""Baseline application; the M1 workflow will add user lookup by ID."""

from fastapi import FastAPI

from .users import User, list_users

app = FastAPI(title="User Query Example")


@app.get("/users", response_model=list[User])
def get_users() -> list[User]:
    """Return all users currently available in the example store."""

    return list_users()
