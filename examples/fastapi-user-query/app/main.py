"""Baseline application; the M1 workflow will add user lookup by ID."""

from typing import Annotated

from fastapi import FastAPI, HTTPException, Path

from .users import User, find_user, list_users

app = FastAPI(title="User Query Example")


@app.get("/users", response_model=list[User])
def get_users() -> list[User]:
    """Return all users currently available in the example store."""

    return list_users()


@app.get("/users/{user_id}", response_model=User)
def get_user(user_id: Annotated[int, Path(gt=0)]) -> User:
    """Return one user or report that the requested user does not exist."""

    user = find_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user
