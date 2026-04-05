from pydantic import BaseModel, EmailStr


class MFALoginRequest(BaseModel):
    email: str
    password: str
    otp: str


class MFASetupResponse(BaseModel):
    secret: str
    provisioning_uri: str


class MFAVerifyRequest(BaseModel):
    otp: str


class SSOStartResponse(BaseModel):
    provider: str
    authorization_url: str
    state: str


class SSOCallbackResponse(BaseModel):
    access_token: str
    token_type: str = 'bearer'
    provider: str = 'google'
    email: EmailStr
    is_new_user: bool = False
