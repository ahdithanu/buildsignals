"""Browser-family issuance/revocation. Never authenticate using browser IDs alone."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, Request, Response
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import (
    REFRESH_COOKIE_NAME,
    REFRESH_COOKIE_PATH,
    REFRESH_COOKIE_SAMESITE,
    REFRESH_COOKIE_SECURE,
    REFRESH_TOKEN_EXPIRE_DAYS,
)
from app.models.browser_session import BrowserSession
from app.models.user import User
from app.schemas.auth import TokenResponse
from app.services.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
)


def browser_request(request: Request) -> tuple[str, int]:
    try:
        browser_id = str(UUID(request.headers.get("x-browser-id", "")))
        raw_epoch = request.headers.get("x-browser-epoch", "")
        epoch = int(raw_epoch)
        if request.headers.get("x-browser-protocol") != "1" or not raw_epoch.isdecimal() or not 0 <= epoch <= 9007199254740991:
            raise ValueError
        return browser_id, epoch
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=426, detail="Browser session protocol required; update this page and sign in again")


def _locked(db: Session, browser_id: str) -> BrowserSession | None:
    if db.get_bind().dialect.name == "sqlite":
        db.execute(update(BrowserSession).where(BrowserSession.browser_id == browser_id)
                   .values(updated_at=BrowserSession.updated_at))
    return db.query(BrowserSession).filter_by(browser_id=browser_id).with_for_update().populate_existing().first()


def _claims(row: BrowserSession) -> dict:
    return {"sid": row.id, "sg": row.generation, "bid": row.browser_id, "be": row.client_epoch}


def validate_browser_claims(db: Session, claims: dict, *, allow_legacy_access: bool = False) -> BrowserSession | None:
    fields = ("sid", "sg", "bid", "be")
    if allow_legacy_access and not any(key in claims for key in fields):
        # No public route issues legacy tokens after this release. Existing
        # signed access tokens survive only their remaining <=15 minute TTL;
        # legacy refresh tokens are never exchanged for a new access token.
        expires = claims.get("exp")
        if type(expires) in (int, float) and expires <= datetime.now(timezone.utc).timestamp() + 900:
            return None
    if (not all(key in claims for key in fields) or type(claims.get("sg")) is not int
            or type(claims.get("be")) is not int
            or any(not isinstance(claims.get(key), str) or not claims[key] for key in ("sid", "bid"))):
        raise HTTPException(status_code=401, detail="Browser session missing; sign in again")
    row = db.query(BrowserSession).filter_by(id=claims["sid"]).populate_existing().first()
    expiry = None if row is None else (row.expires_at.replace(tzinfo=timezone.utc)
                                      if row.expires_at.tzinfo is None else row.expires_at.astimezone(timezone.utc))
    if (not row or row.revoked or row.user_id != claims.get("sub")
            or row.organization_id != claims.get("org_id") or row.generation != claims["sg"]
            or row.browser_id != claims["bid"] or row.client_epoch != claims["be"]
            or expiry <= datetime.now(timezone.utc)):
        raise HTTPException(status_code=401, detail="Browser session superseded or revoked; sign in again")
    return row


def issue_browser_session(db: Session, request: Request, response: Response, *, user: User,
                          org_id: str, role: str, principal_claims: dict | None = None) -> TokenResponse:
    """Caller commits; switch-org must pass its verified access claims."""
    browser_id, epoch = browser_request(request)
    row = _locked(db, browser_id)
    cookie = decode_refresh_token(request.cookies.get(REFRESH_COOKIE_NAME, ""), verify_exp=False)
    if row:
        if epoch <= row.client_epoch:
            raise HTTPException(status_code=409, detail="Browser operation superseded; reload and try again")
        if principal_claims is not None:
            validate_browser_claims(db, principal_claims)
            if principal_claims.get("sid") != row.id:
                raise HTTPException(status_code=401, detail="Browser identity changed; sign in again")
        elif row.user_id != user.id and (not cookie or cookie.get("sid") != row.id or cookie.get("bid") != browser_id):
            # Password authentication can recover the same account after cookie
            # loss. Switching accounts also requires possession of this family's
            # signed cookie; knowing its public browser ID is insufficient.
            raise HTTPException(status_code=409, detail="Browser cookie missing; clear this site's session storage and sign in again")
    else:
        if principal_claims is not None:
            raise HTTPException(status_code=401, detail="Browser session missing; sign in again")
        row = BrowserSession(browser_id=browser_id, generation=0)
        db.add(row)
    row.user_id, row.organization_id = user.id, org_id
    row.generation += 1
    row.client_epoch, row.revoked = epoch, False
    row.updated_at = datetime.now(timezone.utc)
    row.expires_at = row.updated_at + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Concurrent browser session creation; reload and sign in again")
    binding = _claims(row)
    access = create_access_token(user_id=user.id, org_id=org_id, token_version=user.token_version, browser_session=binding)
    cookie_token = create_refresh_token(user_id=user.id, org_id=org_id, token_version=user.token_version, browser_session=binding)
    response.set_cookie(REFRESH_COOKIE_NAME, cookie_token, max_age=REFRESH_TOKEN_EXPIRE_DAYS * 86400,
                        path=REFRESH_COOKIE_PATH, httponly=True, secure=REFRESH_COOKIE_SECURE,
                        samesite=REFRESH_COOKIE_SAMESITE)
    response.headers["Cache-Control"] = "no-store"
    return TokenResponse(access_token=access, user_id=user.id, organization_id=org_id, role=role)


def refresh_binding(db: Session, request: Request, claims: dict) -> dict:
    browser_id, epoch = browser_request(request)
    if claims.get("bid") != browser_id or claims.get("be") != epoch:
        raise HTTPException(status_code=401, detail="Browser identity changed; sign in again")
    row = validate_browser_claims(db, claims)
    return _claims(row)


def revoke_browser_session(db: Session, request: Request) -> None:
    browser_id, epoch = browser_request(request)
    row = _locked(db, browser_id)
    cookie = decode_refresh_token(request.cookies.get(REFRESH_COOKIE_NAME, ""))
    if not row:
        return
    authorization = request.headers.get("authorization", "")
    expected = decode_access_token(authorization[7:], verify_exp=False) if authorization.lower().startswith("bearer ") else None
    if not expected or (cookie and any(expected.get(key) != cookie.get(key) for key in ("sid", "sg", "bid", "be", "sub", "org_id"))):
        raise HTTPException(status_code=409, detail="Logout identity changed; the newer session was not changed")
    # A lost cookie must not turn an authenticated logout into a successful
    # no-op: an older response could still deliver that cookie afterward.
    binding = {**_claims(row), "sub": row.user_id, "org_id": row.organization_id}
    if any(expected.get(key) != value for key, value in binding.items()) or epoch <= row.client_epoch:
        raise HTTPException(status_code=409, detail="Logout superseded; the newer session was not changed")
    row.revoked, row.client_epoch = True, epoch
    row.generation += 1
    row.updated_at = datetime.now(timezone.utc)
    db.flush()
