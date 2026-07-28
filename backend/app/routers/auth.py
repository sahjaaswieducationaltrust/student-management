from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pymongo.errors import DuplicateKeyError

from ..deps import CurrentUser, DbDep, require_roles
from ..schemas import LoginRequest, TokenResponse, UserCreate, UserOut, UserUpdate
from ..security import create_access_token, hash_password, verify_password
from ..utils import now_utc, serialize, to_object_id

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _public(user: dict) -> dict:
    user.pop("password_hash", None)
    return user


async def _authenticate(db, email: str, password: str) -> dict:
    user = await db.users.find_one({"email": email.lower().strip()})
    if user is None or not verify_password(password, user.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password"
        )
    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="This account has been disabled"
        )
    return user


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: DbDep):
    user = await _authenticate(db, payload.email, payload.password)
    public = _public(serialize(user))
    token = create_access_token(public["id"], public["email"], public["role"])
    return {"access_token": token, "token_type": "bearer", "user": public}


@router.post("/token", response_model=TokenResponse, include_in_schema=False)
async def login_form(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbDep):
    """OAuth2 password flow — lets the Swagger UI "Authorize" button work."""
    user = await _authenticate(db, form.username, form.password)
    public = _public(serialize(user))
    token = create_access_token(public["id"], public["email"], public["role"])
    return {"access_token": token, "token_type": "bearer", "user": public}


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser):
    return _public(user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    user: CurrentUser,
    db: DbDep,
    current_password: Annotated[str, Body(embed=True)],
    new_password: Annotated[str, Body(embed=True, min_length=6)],
):
    stored = await db.users.find_one({"_id": to_object_id(user["id"])})
    if not verify_password(current_password, stored.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect"
        )
    await db.users.update_one(
        {"_id": stored["_id"]},
        {"$set": {"password_hash": hash_password(new_password), "updated_at": now_utc()}},
    )


# --------------------------------------------------------------------------- #
# User management (admin only)
# --------------------------------------------------------------------------- #
users_router = APIRouter(
    prefix="/api/users", tags=["users"], dependencies=[Depends(require_roles("admin"))]
)


@users_router.get("", response_model=list[UserOut])
async def list_users(db: DbDep):
    docs = await db.users.find({}, {"password_hash": 0}).sort("created_at", -1).to_list(500)
    return [serialize(d) for d in docs]


@users_router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, db: DbDep):
    doc = payload.model_dump(exclude={"password"})
    doc["email"] = doc["email"].lower().strip()
    doc["role"] = payload.role.value
    doc["password_hash"] = hash_password(payload.password)
    doc["created_at"] = now_utc()
    try:
        result = await db.users.insert_one(doc)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="A user with this email already exists"
        )
    doc["_id"] = result.inserted_id
    return _public(serialize(doc))


@users_router.patch("/{user_id}", response_model=UserOut)
async def update_user(user_id: str, payload: UserUpdate, db: DbDep):
    updates = payload.model_dump(exclude_none=True, exclude={"password"})
    if payload.role is not None:
        updates["role"] = payload.role.value
    if payload.password:
        updates["password_hash"] = hash_password(payload.password)
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update")
    updates["updated_at"] = now_utc()

    doc = await db.users.find_one_and_update(
        {"_id": to_object_id(user_id, "user id")},
        {"$set": updates},
        projection={"password_hash": 0},
        return_document=True,
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="User not found")
    return serialize(doc)


@users_router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: str, db: DbDep, current: CurrentUser):
    if user_id == current["id"]:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    result = await db.users.delete_one({"_id": to_object_id(user_id, "user id")})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
