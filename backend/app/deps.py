from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from pymongo.asynchronous.database import AsyncDatabase

from .db import get_db
from .security import decode_access_token
from .utils import serialize, to_object_id

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

DbDep = Annotated[AsyncDatabase, Depends(get_db)]

_CREDENTIALS_ERROR = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], db: DbDep
) -> dict:
    try:
        payload = decode_access_token(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired, please sign in again",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise _CREDENTIALS_ERROR

    user_id = payload.get("sub")
    if not user_id:
        raise _CREDENTIALS_ERROR

    user = await db.users.find_one({"_id": to_object_id(user_id, "user id")})
    if user is None or not user.get("is_active", True):
        raise _CREDENTIALS_ERROR
    return serialize(user)


CurrentUser = Annotated[dict, Depends(get_current_user)]


def require_roles(*roles: str):
    """Dependency factory restricting an endpoint to the given roles."""

    async def checker(user: CurrentUser) -> dict:
        if roles and user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return user

    return checker


AdminOnly = Annotated[dict, Depends(require_roles("admin"))]
AdminOrStaff = Annotated[dict, Depends(require_roles("admin", "staff"))]
