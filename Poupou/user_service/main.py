from fastapi import FastAPI, HTTPException, Depends, status
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
from typing import Optional
import asyncpg
from jose import JWTError, jwt
from fastapi.security import OAuth2PasswordBearer
from dotenv import load_dotenv
import os

# Загрузка переменных окружения
load_dotenv()

app = FastAPI()

# Конфигурация JWT
SECRET_KEY = "your-secret-key"  # Замените на свой секретный ключ
ALGORITHM = "HS256"  # Алгоритм подписи токена
ACCESS_TOKEN_EXPIRE_MINUTES = 30  # Время жизни токена (в минутах)


# Модель пользователя
class UserCreate(BaseModel):
    login: str
    password: str
    email: EmailStr


class UserLogin(BaseModel):
    login: str
    password: str


class UserResponse(BaseModel):
    login: str
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    birth_date: Optional[str] = None
    phone_number: Optional[str] = None
    created_at: datetime
    updated_at: datetime


# Подключение к БД
async def get_db():
    return await asyncpg.connect(os.getenv("DATABASE_URL"))


# Функция для создания токена
def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


async def get_current_user(token: str = Depends(oauth2_scheme), db=Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        login: str = payload.get("sub")
        if login is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    db_user = await db.fetchrow("SELECT * FROM users WHERE login = $1", login)
    if db_user is None:
        raise credentials_exception
    return db_user


# Регистрация пользователя
@app.post("/register", response_model=UserResponse)
async def register(user: UserCreate, db=Depends(get_db)):
    try:
        await db.execute(
            "INSERT INTO users (login, password, email, created_at, updated_at) VALUES ($1, $2, $3, $4, $5)",
            user.login, user.password, user.email, datetime.now(), datetime.now()
        )
        db_user = await db.fetchrow("SELECT * FROM users WHERE login = $1", user.login)
        return UserResponse(
            login=db_user["login"],
            email=db_user["email"],
            first_name=db_user["first_name"],
            last_name=db_user["last_name"],
            birth_date=db_user["birth_date"],
            phone_number=db_user["phone_number"],
            created_at=db_user["created_at"],
            updated_at=db_user["updated_at"]
        )
    except asyncpg.exceptions.UniqueViolationError:
        raise HTTPException(status_code=400, detail="User already exists")


# Аутентификация
@app.post("/login")
async def login(user: UserLogin, db=Depends(get_db)):
    db_user = await db.fetchrow("SELECT * FROM users WHERE login = $1 AND password = $2", user.login, user.password)
    if not db_user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": db_user["login"]},  # В токене храним логин пользователя
        expires_delta=access_token_expires
    )

    return {"access_token": access_token, "token_type": "bearer"}


# Получение профиля
@app.get("/profile", response_model=UserResponse)
async def get_profile(current_user: dict = Depends(get_current_user)):
    return UserResponse(
        login=current_user["login"],
        email=current_user["email"],
        first_name=current_user["first_name"],
        last_name=current_user["last_name"],
        birth_date=current_user["birth_date"],
        phone_number=current_user["phone_number"],
        created_at=current_user["created_at"],
        updated_at=current_user["updated_at"]
    )
