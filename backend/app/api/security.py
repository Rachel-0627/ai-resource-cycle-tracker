import secrets

from fastapi import Header, HTTPException, status

from ..config import settings


def require_admin_access(
    authorization: str | None = Header(default=None),
    x_admin_token: str | None = Header(default=None),
) -> None:
    """Protect mutable/admin APIs with a bearer token or X-Admin-Token."""

    configured_token = settings.admin_api_token.strip()
    if not configured_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_API_TOKEN is not configured",
        )

    supplied_token = _extract_token(authorization, x_admin_token)
    if supplied_token and secrets.compare_digest(supplied_token, configured_token):
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="admin token required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _extract_token(authorization: str | None, x_admin_token: str | None) -> str | None:
    if x_admin_token:
        return x_admin_token.strip()
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token.strip()
