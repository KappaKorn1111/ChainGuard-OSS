from __future__ import annotations

import hashlib
import re
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .audit import write_audit_log
from .config import Settings
from .errors import APIError
from .models import OrganizationMembership, RefreshToken, User

password_hasher = PasswordHasher()
_UPPER = re.compile(r"[A-Z]")
_LOWER = re.compile(r"[a-z]")
_NUMBER = re.compile(r"\d")


class TokenPair(BaseModel):
    model_config = ConfigDict(extra="forbid")

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


def validate_password(password: str, settings: Settings) -> None:
    if len(password) < settings.password_min_length:
        raise APIError(
            422,
            "weak_password",
            f"password must contain at least {settings.password_min_length} characters",
        )
    if not (_UPPER.search(password) and _LOWER.search(password) and _NUMBER.search(password)):
        raise APIError(
            422,
            "weak_password",
            "password must include uppercase, lowercase, and numeric characters",
        )


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _encode(claims: dict, settings: Settings) -> str:
    assert settings.jwt_secret is not None
    return jwt.encode(
        claims,
        settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )


def decode_token(token: str, settings: Settings, expected_type: str) -> dict:
    assert settings.jwt_secret is not None
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "iss", "sub", "jti", "type"]},
        )
    except jwt.PyJWTError as exc:
        raise APIError(401, "invalid_token", "authentication credentials are invalid") from exc
    if claims.get("type") != expected_type:
        raise APIError(401, "invalid_token", "authentication credentials are invalid")
    return claims


def issue_token_pair(
    db: Session,
    user: User,
    organization_id: uuid.UUID,
    settings: Settings,
    *,
    family_id: uuid.UUID | None = None,
) -> tuple[TokenPair, RefreshToken]:
    now = datetime.now(UTC)
    family = family_id or uuid.uuid4()
    access_expiry = now + timedelta(minutes=settings.access_token_minutes)
    refresh_expiry = now + timedelta(days=settings.refresh_token_days)
    common = {
        "iss": settings.jwt_issuer,
        "sub": str(user.id),
        "org": str(organization_id),
        "iat": now,
    }
    access = _encode(
        {
            **common,
            "type": "access",
            "jti": str(uuid.uuid4()),
            "exp": access_expiry,
        },
        settings,
    )
    refresh = _encode(
        {
            **common,
            "type": "refresh",
            "jti": str(uuid.uuid4()),
            "family": str(family),
            "exp": refresh_expiry,
        },
        settings,
    )
    record = RefreshToken(
        user_id=user.id,
        organization_id=organization_id,
        family_id=family,
        token_hash=token_hash(refresh),
        expires_at=refresh_expiry,
    )
    db.add(record)
    db.flush()
    return (
        TokenPair(
            access_token=access,
            refresh_token=refresh,
            expires_in=settings.access_token_minutes * 60,
        ),
        record,
    )


def rotate_refresh_token(
    db: Session,
    token: str,
    settings: Settings,
    *,
    correlation_id: str,
) -> tuple[TokenPair, RefreshToken]:
    claims = decode_token(token, settings, "refresh")
    record = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash(token)))
    family_id = uuid.UUID(claims["family"])
    now = datetime.now(UTC)
    if (
        record is None
        or record.family_id != family_id
        or record.user_id != uuid.UUID(claims["sub"])
        or record.expires_at <= now
    ):
        raise APIError(401, "invalid_refresh_token", "refresh token is invalid")
    if record.used_at is not None or record.revoked_at is not None:
        db.execute(
            update(RefreshToken)
            .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        write_audit_log(
            db,
            action="auth.refresh_reuse",
            target_type="refresh_token_family",
            target_id=str(family_id),
            actor_user_id=record.user_id,
            organization_id=record.organization_id,
            correlation_id=correlation_id,
        )
        db.commit()
        raise APIError(401, "refresh_token_reuse", "refresh token reuse detected")
    user = db.get(User, record.user_id)
    membership = db.scalar(
        select(OrganizationMembership).where(
            OrganizationMembership.user_id == record.user_id,
            OrganizationMembership.organization_id == record.organization_id,
        )
    )
    if user is None or not user.is_active or membership is None:
        raise APIError(401, "invalid_refresh_token", "refresh token is invalid")
    record.used_at = now
    record.revoked_at = now
    pair, replacement = issue_token_pair(
        db,
        user,
        record.organization_id,
        settings,
        family_id=family_id,
    )
    record.replaced_by_id = replacement.id
    return pair, replacement


def revoke_refresh_token(db: Session, token: str, settings: Settings) -> None:
    claims = decode_token(token, settings, "refresh")
    record = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash(token)))
    if record is None:
        return
    now = datetime.now(UTC)
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == uuid.UUID(claims["family"]))
        .values(revoked_at=now)
    )
