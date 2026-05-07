"""Auth router — user registration, login, JWT token generation."""
from fastapi import APIRouter
from pydantic import BaseModel
from app.core.auth import create_user, authenticate_user, create_access_token

router = APIRouter(prefix="/v1/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    role: str = "underwriter"


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/register")
async def register(req: RegisterRequest):
    create_user(name=req.name, email=req.email, password=req.password, role=req.role)
    return {"message": "User registered successfully"}


@router.post("/login")
async def login(req: LoginRequest):
    user = authenticate_user(req.email, req.password)
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(user)
    return {"access_token": token, "token_type": "bearer", "role": user.role, "name": user.name}
