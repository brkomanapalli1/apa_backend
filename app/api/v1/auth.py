from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from jose import JWTError
from sqlalchemy.orm import Session
from app.db.enums import UserRole

from app.core.config import settings
from app.core.deps import get_current_user, get_db
from app.core.security import (
    PasswordResetTokenService,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
)
from app.schemas.mfa import MFALoginRequest, MFASetupResponse, MFAVerifyRequest, SSOCallbackResponse, SSOStartResponse
from app.schemas.user import UserResponse
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService
from app.services.email_service import EmailService
from app.services.observability import AUTH_REFRESH_COUNT
from app.services.mfa_service import MFAService
from app.services.oauth_state_service import OAuthStateService

router = APIRouter()
audit = AuditService()
mfa_service = MFAService()
oauth_state_service = OAuthStateService()
auth_service = AuthService()
email_service = EmailService()
password_reset_tokens = PasswordResetTokenService()


def _assign_role_for_new_user(db: Session, email: str) -> UserRole:
    if email == settings.DEFAULT_ADMIN_EMAIL or db.query(User).count() == 0:
        return UserRole.ADMIN
    return UserRole.MEMBER


def _issue_tokens(db: Session, user: User) -> TokenResponse:
    access_token = create_access_token(user.email)
    refresh_token, token_jti, expires_at = create_refresh_token(user.email)
    auth_service.issue_refresh_token(db, user, token_jti, expires_at)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post('/register', response_model=TokenResponse)
def register(payload: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail='Email already exists')
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=get_password_hash(payload.password),
        role=_assign_role_for_new_user(db, payload.email),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    audit.log(db, action='auth.register', user_id=user.id, entity_type='user', entity_id=str(user.id), ip_address=request.client.host if request.client else None)
    AUTH_REFRESH_COUNT.labels('success').inc()
    return _issue_tokens(db, user)


@router.post('/login', response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail='Invalid credentials')
    if mfa_service.require_mfa(user):
        raise HTTPException(status_code=403, detail='MFA required. Use /auth/login-mfa')
    audit.log(db, action='auth.login', user_id=user.id, entity_type='user', entity_id=str(user.id), ip_address=request.client.host if request.client else None)
    return _issue_tokens(db, user)


@router.post('/login-mfa', response_model=TokenResponse)
def login_mfa(payload: MFALoginRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail='Invalid credentials')
    if not user.totp_secret or not mfa_service.verify(user.totp_secret, payload.otp):
        raise HTTPException(status_code=401, detail='Invalid one-time passcode')
    audit.log(db, action='auth.login_mfa', user_id=user.id, entity_type='user', entity_id=str(user.id), ip_address=request.client.host if request.client else None)
    return _issue_tokens(db, user)


@router.post('/refresh', response_model=TokenResponse)
def refresh_tokens(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    try:
        token_payload = decode_token(payload.refresh_token)
    except JWTError as exc:
        AUTH_REFRESH_COUNT.labels('invalid').inc()
        raise HTTPException(status_code=401, detail='Invalid refresh token') from exc
    if token_payload.get('type') != 'refresh':
        raise HTTPException(status_code=401, detail='Invalid refresh token')
    token_jti = token_payload.get('jti')
    email = token_payload.get('sub')
    if not token_jti or not email:
        raise HTTPException(status_code=401, detail='Invalid refresh token')
    existing = auth_service.get_valid_refresh_token(db, token_jti)
    if not existing:
        AUTH_REFRESH_COUNT.labels('revoked').inc()
        raise HTTPException(status_code=401, detail='Refresh token revoked or expired')
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=401, detail='User not found')
    auth_service.revoke_refresh_token(db, token_jti)
    audit.log(db, action='auth.refresh', user_id=user.id, entity_type='user', entity_id=str(user.id), detail=token_jti, ip_address=request.client.host if request.client else None)
    return _issue_tokens(db, user)


@router.post('/logout')
def logout(payload: RefreshRequest, request: Request, db: Session = Depends(get_db)):
    try:
        token_payload = decode_token(payload.refresh_token)
        token_jti = token_payload.get('jti')
        email = token_payload.get('sub')
    except JWTError:
        token_jti = None
        email = None
    if token_jti:
        auth_service.revoke_refresh_token(db, token_jti)
    user = db.query(User).filter(User.email == email).first() if email else None
    audit.log(db, action='auth.logout', user_id=user.id if user else None, entity_type='user', entity_id=str(user.id) if user else None, detail=token_jti, ip_address=request.client.host if request.client else None)
    return {'message': 'Logged out'}


@router.post('/logout-all')
def logout_all(request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    count = auth_service.revoke_all_for_user(db, current_user.id)
    audit.log(db, action='auth.logout_all', user_id=current_user.id, entity_type='user', entity_id=str(current_user.id), detail=str(count), ip_address=request.client.host if request.client else None)
    return {'message': 'Logged out from all sessions', 'revoked': count}


@router.post('/password/forgot')
def forgot_password(payload: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()
    if user:
        token = password_reset_tokens.create(user.email)
        reset_url = f"{settings.FRONTEND_URL}/reset-password?token={token}"
        html = f'<p>Reset your password:</p><p><a href="{reset_url}">Reset password</a></p>'
        text = f'Reset your password: {reset_url}'
        email_service.send_email(to=user.email, subject='Reset your password', html=html, text=text)
        audit.log(db, action='auth.password_reset_requested', user_id=user.id, entity_type='user', entity_id=str(user.id), ip_address=request.client.host if request.client else None)
    return {'message': 'If the account exists, a reset email has been sent'}


@router.post('/password/reset')
def reset_password(payload: ResetPasswordRequest, request: Request, db: Session = Depends(get_db)):
    try:
        email = password_reset_tokens.verify(payload.token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=400, detail='User not found')
    user.hashed_password = get_password_hash(payload.new_password)
    db.add(user)
    db.commit()
    auth_service.revoke_all_for_user(db, user.id)
    audit.log(db, action='auth.password_reset_completed', user_id=user.id, entity_type='user', entity_id=str(user.id), ip_address=request.client.host if request.client else None)
    return {'message': 'Password reset successful'}


@router.post('/mfa/setup', response_model=MFASetupResponse)
def setup_mfa(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    secret = mfa_service.generate_secret()
    current_user.totp_secret = secret
    db.add(current_user)
    db.commit()
    return MFASetupResponse(secret=secret, provisioning_uri=mfa_service.provisioning_uri(current_user.email, secret))


@router.post('/mfa/verify')
def verify_mfa(payload: MFAVerifyRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not current_user.totp_secret or not mfa_service.verify(current_user.totp_secret, payload.otp):
        raise HTTPException(status_code=400, detail='Invalid code')
    current_user.mfa_enabled = True
    db.add(current_user)
    db.commit()
    return {'message': 'MFA enabled'}


@router.get('/sso/google/start', response_model=SSOStartResponse)
def start_google_sso(return_to: str | None = None):
    if not settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=400, detail='Google SSO not configured')
    state = oauth_state_service.create(provider='google', return_to=return_to)
    params = {
        'client_id': settings.GOOGLE_CLIENT_ID,
        'response_type': 'code',
        'redirect_uri': settings.GOOGLE_REDIRECT_URI,
        'scope': 'openid email profile',
        'access_type': 'offline',
        'include_granted_scopes': 'true',
        'prompt': 'select_account',
        'state': state,
    }
    authorization_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
    return SSOStartResponse(provider='google', authorization_url=authorization_url, state=state)


@router.get('/sso/google/callback', response_model=SSOCallbackResponse)
def google_sso_callback(code: str, state: str, request: Request, db: Session = Depends(get_db)):
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=400, detail='Google SSO not configured')

    try:
        state_payload = oauth_state_service.verify(state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if state_payload.get('provider') != 'google':
        raise HTTPException(status_code=400, detail='OAuth provider mismatch')

    token_payload = {
        'code': code,
        'client_id': settings.GOOGLE_CLIENT_ID,
        'client_secret': settings.GOOGLE_CLIENT_SECRET,
        'redirect_uri': settings.GOOGLE_REDIRECT_URI,
        'grant_type': 'authorization_code',
    }

    try:
        with httpx.Client(timeout=15) as client:
            token_res = client.post('https://oauth2.googleapis.com/token', data=token_payload)
            token_res.raise_for_status()
            id_token = token_res.json().get('id_token')
            if not id_token:
                raise HTTPException(status_code=400, detail='Google token exchange did not return id_token')
            info_res = client.get('https://oauth2.googleapis.com/tokeninfo', params={'id_token': id_token})
            info_res.raise_for_status()
            profile = info_res.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f'Google SSO failed: {exc}') from exc

    email = profile.get('email')
    email_verified = str(profile.get('email_verified')).lower() == 'true'
    hosted_domain = profile.get('hd')
    aud = profile.get('aud')
    if aud != settings.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=400, detail='Google audience mismatch')
    if not email or not email_verified:
        raise HTTPException(status_code=400, detail='Google account email is missing or unverified')
    if settings.GOOGLE_ALLOWED_DOMAIN and hosted_domain != settings.GOOGLE_ALLOWED_DOMAIN:
        raise HTTPException(status_code=403, detail='Google account domain is not allowed')

    user = db.query(User).filter(User.email == email).first()
    is_new_user = False
    if not user:
        is_new_user = True
        name = profile.get('name') or email.split('@')[0]
        user = User(
            email=email,
            full_name=name,
            hashed_password=get_password_hash(profile.get('sub', email)),
            sso_provider='google',
            role=_assign_role_for_new_user(db, email),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        user.sso_provider = 'google'
        if profile.get('name') and not user.full_name:
            user.full_name = profile['name']
        db.add(user)
        db.commit()
        db.refresh(user)

    audit.log(db, action='auth.sso_google_callback', user_id=user.id, entity_type='user', entity_id=str(user.id), detail=email, ip_address=request.client.host if request.client else None)
    token_response = _issue_tokens(db, user)
    return SSOCallbackResponse(access_token=token_response.access_token, token_type='bearer', email=user.email, is_new_user=is_new_user)


@router.get('/me', response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post('/push-token')
def register_push_token(
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Register or update Expo push token for the current user."""
    token = payload.get("push_token", "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="push_token is required")
    current_user.push_token = token
    db.add(current_user)
    db.commit()
    return {"ok": True, "push_token": token}


@router.delete('/push-token')
def unregister_push_token(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove push token (on logout)."""
    current_user.push_token = None
    db.add(current_user)
    db.commit()
    return {"ok": True}