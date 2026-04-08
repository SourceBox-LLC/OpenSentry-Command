import httpx
from fastapi import Depends, HTTPException, Request, status
from app.core.config import settings
from clerk_backend_api.security import AuthenticateRequestOptions
from app.core.clerk import clerk


class AuthUser:
    def __init__(
        self,
        user_id: str,
        org_id: str,
        org_permissions: list,
        email: str = "",
        username: str = "",
    ):
        self.user_id = user_id
        self.sub = user_id
        self.org_id = org_id
        self.org_permissions = org_permissions
        self.email = email
        self.username = username

    def has_permission(self, permission: str) -> bool:
        return permission in self.org_permissions

    @property
    def is_admin(self) -> bool:
        return self.has_permission("org:admin:admin") or self.has_permission(
            "org:cameras:manage_cameras"
        )

    @property
    def can_view_cameras(self) -> bool:
        return self.has_permission("org:cameras:view_cameras") or self.is_admin


def decode_v2_permissions(claims: dict) -> list:
    """
    Decode permissions from Clerk V2 JWT format.
    V2 uses compact o claim with permission bitmap.
    """
    o_claim = claims.get("o", {})
    fea_claim = claims.get("fea", "")

    if not o_claim or not fea_claim:
        return []

    # Get permission names from o.per
    per_str = o_claim.get("per", "")
    if not per_str:
        return []

    permission_names = per_str.split(",")

    # Get features from fea (strip 'o:' prefix)
    features = []
    for f in fea_claim.split(","):
        if f.startswith("o:"):
            features.append(f[2:])
        else:
            features.append(f)

    # Get feature-permission map from o.fpm
    fpm_str = o_claim.get("fpm", "")
    fpm_values = []
    if fpm_str:
        try:
            fpm_values = [int(x) for x in fpm_str.split(",")]
        except (ValueError, TypeError):
            pass

    # Reconstruct full permission keys: org:{feature}:{permission}
    permissions = []
    for i, feature in enumerate(features):
        if i < len(fpm_values):
            fpm_value = fpm_values[i]
            # Check each permission bit
            for j, perm_name in enumerate(permission_names):
                if fpm_value & (1 << j):
                    permissions.append(f"org:{feature}:{perm_name}")

    return permissions


def convert_to_httpx_request(fastapi_request: Request) -> httpx.Request:
    return httpx.Request(
        method=fastapi_request.method,
        url=str(fastapi_request.url),
        headers=dict(fastapi_request.headers),
    )


async def get_current_user(request: Request) -> AuthUser:
    if not settings.is_clerk_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Clerk authentication not configured. Set CLERK_SECRET_KEY and CLERK_PUBLISHABLE_KEY.",
        )

    httpx_request = convert_to_httpx_request(request)

    try:
        request_state = clerk.authenticate_request(
            httpx_request,
            AuthenticateRequestOptions(authorized_parties=[settings.FRONTEND_URL]),
        )

        if not request_state.is_signed_in:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
            )

        claims = request_state.payload

        # Decode permissions: try V1 format first, then V2 format
        org_permissions = claims.get("org_permissions") or claims.get("permissions")
        if not org_permissions:
            org_permissions = decode_v2_permissions(claims)

        user_id = claims.get("sub")
        org_id = claims.get("org_id")
        email = claims.get("email", "")
        username = claims.get("username", "")

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
            )

        if not org_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No organization selected. Please create or join an organization.",
            )

        return AuthUser(
            user_id=user_id,
            org_id=org_id,
            org_permissions=org_permissions,
            email=email,
            username=username,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}",
        )


async def require_view(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    if not user.can_view_cameras:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="View permission required"
        )
    return user


async def require_admin(user: AuthUser = Depends(get_current_user)) -> AuthUser:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin permission required"
        )
    return user
