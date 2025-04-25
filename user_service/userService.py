import os
import jwt
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from passlib.context import CryptContext
from kafka import KafkaProducer
import json
import time
from kafka.errors import NoBrokersAvailable

user_app = FastAPI(title="User Management Service")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@db_users:5432/usersdb")
SECRET_KEY = os.getenv("SECRET_KEY", "ultra-secure-key")
TOKEN_ALGORITHM = "HS256"

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()
password_hasher = CryptContext(schemes=["bcrypt"], deprecated="auto")

class UserAccount(Base):
    __tablename__ = "user_accounts"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, nullable=False)
    password_hash = Column(String(128), nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    first_name = Column(String(80))
    last_name = Column(String(80))
    birth_date = Column(DateTime)
    phone_number = Column(String(20))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

def hash_password(password: str) -> str:
    return password_hasher.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return password_hasher.verify(plain_password, hashed_password)

@user_app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class UserRegistration(BaseModel):
    username: str
    password: str
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    birth_date: Optional[datetime] = None
    phone_number: Optional[str] = None

class UserAuthentication(BaseModel):
    username: str
    password: str

@user_app.post("/users/register", status_code=201)
def register_user(user_data: UserRegistration, db: Session = Depends(get_db)):
    existing = db.query(UserAccount).filter(
        (UserAccount.username == user_data.username) |
        (UserAccount.email == user_data.email)
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username or email already in use")

    hashed_pw = hash_password(user_data.password)
    new_user = UserAccount(
        username=user_data.username,
        password_hash=hashed_pw,
        email=user_data.email,
        first_name=user_data.first_name,
        last_name=user_data.last_name,
        birth_date=user_data.birth_date,
        phone_number=user_data.phone_number
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"message": "User registration successful"}

def generate_auth_token(user_id: int) -> str:
    expire = datetime.utcnow() + timedelta(minutes=60)
    payload = {
        "sub": str(user_id),
        "exp": expire
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=TOKEN_ALGORITHM)

@user_app.post("/users/login")
def authenticate_user(auth_data: UserAuthentication, db: Session = Depends(get_db)):
    user = db.query(UserAccount).filter(UserAccount.username == auth_data.username).first()
    if not user or not verify_password(auth_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = generate_auth_token(user_id=user.id)
    return {"access_token": token}

@user_app.get("/users/profile")
def get_user_profile(db: Session = Depends(get_db), user_id: int = 1):
    user = db.query(UserAccount).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "username": user.username,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "birth_date": user.birth_date,
        "phone_number": user.phone_number,
        "created_at": user.created_at,
        "updated_at": user.updated_at
    }

@user_app.put("/users/profile")
def update_user_profile(
    db: Session = Depends(get_db),
    user_id: int = 1,
    user_data: UserRegistration = Depends()
):
    user = db.query(UserAccount).get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.first_name = user_data.first_name or user.first_name
    user.last_name = user_data.last_name or user.last_name
    user.birth_date = user_data.birth_date or user.birth_date
    user.phone_number = user_data.phone_number or user.phone_number
    user.email = user_data.email or user.email
    db.commit()
    db.refresh(user)
    return {"message": "Profile updated successfully"}

@user_app.post('/users/register')
def register_user_event(user: UserRegistration):
    producer = KafkaProducer(
        bootstrap_servers=['kafka:9092'],
        value_serializer=lambda v: json.dumps(v).encode('utf-8')
    )
    producer.send('user-registrations', {
        'userId': str(user.id),
        'registeredAt': datetime.utcnow().isoformat()
    })
    return user

@user_app.get("/")
def health_check():
    return {"status": "User Service operational"}