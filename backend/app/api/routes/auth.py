import uuid

from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status
from jose import JWTError, jwt
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from app.api.deps import ADMIN_ROLES, CurrentUser, SessionDep, audit, require
from app.core import security
from app.core.config import settings
from app.core.rate_limit import check_rate_limit
from app.models.entities import Role, User
from fastapi import Depends

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)
    role: Role = Role.VIEWER
    organisation: str | None = None


def _user_out(u: User) -> dict:
    return {"id": str(u.id), "name": u.name, "email": u.email, "role": u.role.value, "organisation": u.organisation}


def _issue(user: User, response: Response) -> dict:
    access = security.create_access_token(user.id, user.email, user.role.value)
    refresh = security.create_refresh_token(user.id)
    response.set_cookie("refresh_token", refresh, httponly=True, samesite="lax", secure=settings.COOKIE_SECURE,
                        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400, path=f"{settings.API_V1_STR}/auth")
    return {"accessToken": access, "user": _user_out(user)}


@router.post("/login")
async def login(body: LoginIn, request: Request, response: Response, db: SessionDep):
    await check_rate_limit(request, "login", settings.RATE_LIMIT_LOGIN_PER_MIN, 60)
    user = (await db.execute(select(User).where(User.email == body.email.lower()))).scalars().first()
    # constant-ish behaviour: same message for unknown user / bad password
    if user is None or not user.is_active or not security.verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    await audit(db, user, "LOGIN", "user", user.id)
    await db.commit()
    return _issue(user, response)


@router.post("/refresh")
async def refresh(response: Response, db: SessionDep, refresh_token: str | None = Cookie(default=None)):
    if not refresh_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No refresh token")
    try:
        payload = jwt.decode(refresh_token, settings.REFRESH_SECRET_KEY, algorithms=[security.ALGORITHM])
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    if payload.get("type") != "refresh":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid refresh token")
    user = (await db.execute(select(User).where(User.id == uuid.UUID(payload["sub"])))).scalars().first()
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return _issue(user, response)


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("refresh_token", path=f"{settings.API_V1_STR}/auth")
    return {"ok": True}


@router.get("/me")
async def me(user: CurrentUser):
    return _user_out(user)


@router.post("/users", status_code=201)
async def create_user(body: UserCreate, db: SessionDep, admin: User = Depends(require(*ADMIN_ROLES))):
    if body.role == Role.SUPER_ADMIN and admin.role != Role.SUPER_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only a SUPER_ADMIN can create SUPER_ADMIN users")
    if (await db.execute(select(User).where(User.email == body.email.lower()))).scalars().first():
        raise HTTPException(status.HTTP_409_CONFLICT, "A user with this email already exists")
    u = User(name=body.name, email=body.email.lower(), password_hash=security.get_password_hash(body.password),
             role=body.role, organisation=body.organisation)
    db.add(u)
    await audit(db, admin, "CREATE_USER", "user", u.id, {"role": body.role.value})
    await db.commit()
    return _user_out(u)
