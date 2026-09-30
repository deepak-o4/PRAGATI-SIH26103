import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import ExpiredSignatureError, JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import settings
from app.db.session import get_db
from app.models.entities import AuditLog, Role, User

bearer = HTTPBearer(auto_error=False)
SessionDep = Annotated[AsyncSession, Depends(get_db)]

WRITE_ROLES = {Role.SUPER_ADMIN, Role.ADMIN, Role.PROGRAM_MANAGER, Role.PROJECT_MANAGER}
ANALYSIS_ROLES = WRITE_ROLES | {Role.ANALYST}
ADMIN_ROLES = {Role.SUPER_ADMIN, Role.ADMIN}


def _401(msg: str):
    return HTTPException(status.HTTP_401_UNAUTHORIZED, msg, headers={"WWW-Authenticate": "Bearer"})


async def get_current_user(db: SessionDep, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise _401("Authentication required")
    try:
        payload = jwt.decode(creds.credentials, settings.SECRET_KEY, algorithms=[security.ALGORITHM])
    except ExpiredSignatureError:
        raise _401("Token has expired")
    except JWTError:
        raise _401("Invalid authentication token")
    if payload.get("type") == "refresh" or not payload.get("sub"):
        raise _401("Invalid authentication token")
    try:
        user_id = uuid.UUID(payload["sub"])
    except (AttributeError, TypeError, ValueError):
        raise _401("Invalid authentication token")
    user = (await db.execute(select(User).where(User.id == user_id))).scalars().first()
    if user is None or not user.is_active:
        raise _401("User not found or inactive")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require(*roles: Role):
    allowed = set(roles)

    async def dep(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Your role does not permit this action")
        return user
    return dep


async def audit(db: AsyncSession, user, action: str, entity: str, entity_id=None, detail=None):
    db.add(AuditLog(user_id=getattr(user, "id", None), action=action, entity=entity,
                    entity_id=None if entity_id is None else str(entity_id), detail=detail))
