from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import or_, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import User
from ..schemas import UserCreate
from ..serialization import user_dict
from ..auth.deps import get_current_user
from ..auth.utils import verify_password, get_password_hash, create_access_token
from ..teams.service import create_team, create_board

router = APIRouter()

@router.post("/register", status_code=201)
def register(data: UserCreate, db: Session = Depends(get_db)):
    duplicate = db.query(User).filter(or_(func.lower(User.email) == data.email,
                                           func.lower(User.username) == data.username.lower())).first()
    if duplicate:
        raise HTTPException(409, "Email or username already registered")
    user = User(email=data.email, username=data.username.lower(), full_name=data.full_name,
                hashed_password=get_password_hash(data.password))
    db.add(user)
    try:
        db.flush()
        team = create_team(db, user, "My Team", "My personal workspace")
        create_board(db, team, user, "My Board", visibility="private")
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Email or username already registered") from None
    return user_dict(user)

@router.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    identifier = form.username.lower()
    user = db.query(User).filter(or_(func.lower(User.email) == identifier,
                                     func.lower(User.username) == identifier)).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(401, "Incorrect username/email or password",
                            headers={"WWW-Authenticate": "Bearer"})
    if user.hashed_password.startswith(("$2a$", "$2b$", "$2y$")):
        user.hashed_password = get_password_hash(form.password)
        db.commit()
    return {"access_token": create_access_token({"sub": str(user.id)}),
            "token_type": "bearer", "user": user_dict(user)}

@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return user_dict(user)
