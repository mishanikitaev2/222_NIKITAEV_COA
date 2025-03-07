from fastapi import FastAPI, HTTPException, Request
import httpx

app = FastAPI()
USER_SERVICE_URL = "http://user-service:8001"  # URL сервиса пользователей

# Проксирование запросов на сервис пользователей
@app.post("/register")
async def register(request: Request):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{USER_SERVICE_URL}/register", json=await request.json())
        return response.json()

@app.post("/login")
async def login(request: Request):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{USER_SERVICE_URL}/login", json=await request.json())
        return response.json()

@app.get("/profile")
async def get_profile(request: Request):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{USER_SERVICE_URL}/profile", headers=request.headers)
        return response.json()

@app.put("/profile")
async def update_profile(request: Request):
    async with httpx.AsyncClient() as client:
        response = await client.put(f"{USER_SERVICE_URL}/profile", json=await request.json(), headers=request.headers)
        return response.json()