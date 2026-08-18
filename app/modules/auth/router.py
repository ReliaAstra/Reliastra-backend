from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.exceptions import ResourceNotFoundException
from app.core.rate_limit import ip_limiter, enforce_rate_limit
from app.db.session import get_db
from app.modules.auth.schemas import (
    ForgotPasswordRequest,
    GitHubAuthRequest,
    GitHubAuthResponse,
    GitHubAuthUrlResponse,
    GoogleAuthRequest,
    GoogleAuthResponse,
    GoogleAuthUrlResponse,
    LoginRequest,
    LogoutRequest,
    OAuthAuthResponse,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    ResetPasswordResponse,
    SendVerificationRequest,
    RegisterResponse,
    TokenResponse,
    VerifyEmailRequest,
    VerifyEmailResponse,
)
from app.modules.auth.service import AuthService, auth_service
from app.modules.auth.google_service import (
    GoogleAuthService,
    google_auth_service,
)
from app.modules.auth.github_service import (
    GitHubAuthService,
    github_auth_service,
)
from app.modules.auth.email_service import (
    EmailAuthService,
    email_auth_service,
)
from app.modules.users.repository import UserRepository

router = APIRouter(prefix="/v1/auth", tags=["Authentication"])


def get_auth_service() -> AuthService:
    return auth_service


def get_google_auth_service() -> GoogleAuthService:
    return google_auth_service


def get_github_auth_service() -> GitHubAuthService:
    return github_auth_service


def get_email_auth_service() -> EmailAuthService:
    return email_auth_service


# ── Email Auth ──────────────────────────────────────────────


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: Request,
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    await enforce_rate_limit(request, ip_limiter)
    return await service.register(db, body)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    await enforce_rate_limit(request, ip_limiter)
    return await service.login(db, body)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: Request,
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> TokenResponse:
    await enforce_rate_limit(request, ip_limiter)
    return await service.refresh(db, body.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    body: LogoutRequest,
    db: AsyncSession = Depends(get_db),
    service: AuthService = Depends(get_auth_service),
) -> None:
    await service.logout(db, body.refresh_token)


# ── Google OAuth ──────────────────────────────────────────


@router.get("/google/url", response_model=GoogleAuthUrlResponse)
async def get_google_auth_url(
    service: GoogleAuthService = Depends(get_google_auth_service),
) -> GoogleAuthUrlResponse:
    """
    Return the Google OAuth authorization URL for the frontend to redirect to.

    Generates a CSRF state token, stores it in Redis, and returns it
    with the URL. The frontend must include the state in the callback request.
    """
    import secrets

    state_token = secrets.token_urlsafe(32)
    # Store state in Redis for CSRF validation
    await service._store_state(state_token)
    url = service.get_authorization_url(state_token)
    return GoogleAuthUrlResponse(authorization_url=url, state=state_token)


@router.post("/google", response_model=GoogleAuthResponse)
async def google_auth_callback(
    request: GoogleAuthRequest,
    db: AsyncSession = Depends(get_db),
    service: GoogleAuthService = Depends(get_google_auth_service),
) -> GoogleAuthResponse:
    """
    Exchange Google authorization code for JWT tokens.

    The frontend sends the code (and optionally state) it received from
    Google's redirect. This handles both signup and signin in one endpoint.

    State validation provides CSRF protection when provided.
    """
    tokens, is_new_user = await service.authenticate_with_code(
        db, request.code, state=request.state
    )

    # Decode the token to get user_id and fetch full user details
    import uuid as uuid_mod
    from app.core.security import decode_token

    payload = decode_token(tokens.access_token)
    user_id = uuid_mod.UUID(payload["sub"])
    user = await UserRepository.get_by_id(db, user_id)
    if not user:
        raise ResourceNotFoundException("User not found — account may have been deleted")

    return GoogleAuthResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
        is_new_user=is_new_user,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
    )


# ── GitHub OAuth ──────────────────────────────────────────


@router.get("/github/url", response_model=GitHubAuthUrlResponse)
async def get_github_auth_url(
    service: GitHubAuthService = Depends(get_github_auth_service),
) -> GitHubAuthUrlResponse:
    """
    Return the GitHub OAuth authorization URL for the frontend to redirect to.

    Generates a CSRF state token, stores it in Redis, and returns it
    with the URL. The frontend must include the state in the callback request.
    """
    import secrets

    state_token = secrets.token_urlsafe(32)
    # Store state in Redis for CSRF validation
    await service._store_state(state_token)
    url = service.get_authorization_url(state_token)
    return GitHubAuthUrlResponse(authorization_url=url, state=state_token)


@router.post("/github", response_model=GitHubAuthResponse)
async def github_auth_callback(
    request: GitHubAuthRequest,
    db: AsyncSession = Depends(get_db),
    service: GitHubAuthService = Depends(get_github_auth_service),
) -> GitHubAuthResponse:
    """
    Exchange GitHub authorization code for JWT tokens.

    The frontend sends the code (and optionally state) it received from
    GitHub's redirect. This handles both signup and signin in one endpoint.

    State validation provides CSRF protection when provided.
    """
    tokens, is_new_user = await service.authenticate_with_code(
        db, request.code, state=request.state
    )

    # Decode the token to get user_id and fetch full user details
    import uuid as uuid_mod
    from app.core.security import decode_token

    payload = decode_token(tokens.access_token)
    user_id = uuid_mod.UUID(payload["sub"])
    user = await UserRepository.get_by_id(db, user_id)
    if not user:
        raise ResourceNotFoundException("User not found — account may have been deleted")

    return GitHubAuthResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        token_type=tokens.token_type,
        expires_in=tokens.expires_in,
        is_new_user=is_new_user,
        user_id=user.id,
        email=user.email,
        full_name=user.full_name,
    )


# ── Email Verification ────────────────────────────────────────


@router.post("/send-verification", status_code=status.HTTP_200_OK)
async def send_verification_email(
    request: Request,
    body: SendVerificationRequest,
    db: AsyncSession = Depends(get_db),
    service: EmailAuthService = Depends(get_email_auth_service),
) -> dict:
    """Send an email verification link to the user's email address."""
    await enforce_rate_limit(request, ip_limiter)
    return await service.send_verification_email(db, body.email)


@router.post("/verify-email", response_model=VerifyEmailResponse)
async def verify_email(
    body: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
    service: EmailAuthService = Depends(get_email_auth_service),
) -> VerifyEmailResponse:
    """Verify a user's email using the token from the verification link."""
    result = await service.verify_email(db, body.token)
    return VerifyEmailResponse(**result)


# ── Password Reset ──────────────────────────────────────────────


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
    service: EmailAuthService = Depends(get_email_auth_service),
) -> dict:
    """
    Send a password reset link to the user's email.
    Always returns the same message to prevent email enumeration.
    """
    await enforce_rate_limit(request, ip_limiter)
    return await service.send_password_reset_email(db, body.email)


@router.post("/reset-password", response_model=ResetPasswordResponse)
async def reset_password(
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    service: EmailAuthService = Depends(get_email_auth_service),
) -> ResetPasswordResponse:
    """Reset a user's password using the token from the reset email."""
    result = await service.reset_password(db, body.token, body.new_password)
    return ResetPasswordResponse(**result)
