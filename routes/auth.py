from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field

from database import users
from utils.limiter import limiter
from utils.security import hash_password, verify_password
from utils.token import create_access_token
from models.user import UserCreate, UserOut
from utils.validate import validate_email, validate_password, validate_string, sanitize_text

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginBody(BaseModel):
    email: str
    password: str


@router.post("/register", response_model=dict)
@limiter.limit("5/minute")
def register(body: UserCreate, request: Request):
    email = validate_email(body.email)
    validate_password(body.password)
    name = validate_string(body.name, "Name", min_len=1, max_len=100)

    if users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    user_doc = {
        "name": sanitize_text(name),
        "email": email,
        "password": hash_password(body.password),
    }
    result = users.insert_one(user_doc)
    token = create_access_token({"sub": str(result.inserted_id)})
    user_out = UserOut(id=str(result.inserted_id), name=name, email=email)
    return {"token": token, "user": user_out}


@router.post("/login", response_model=dict)
@limiter.limit("10/minute")
def login(body: LoginBody, request: Request):
    email = validate_email(body.email)
    user = users.find_one({"email": email})
    if not user or not verify_password(body.password, user["password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token({"sub": str(user["_id"])})
    user_out = UserOut(id=str(user["_id"]), name=user["name"], email=user["email"])
    return {"token": token, "user": user_out}
