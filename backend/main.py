import os
import json
import asyncio
from uuid import UUID, uuid4
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator
from db import connect, task_detail, serialize
from subscriptions import connections, PROVIDERS as SUBSCRIPTIONS
from bridge import router as bridge_router
from task_state import finish_task
from fastapi.middleware.cors import CORSMiddleware
from access import issue_session, valid_session, check_password

@asynccontextmanager
async def lifespan(app):
    app.state.pool = await connect()
    yield
    await app.state.pool.close()

app = FastAPI(title="Multi-Agent Portal", lifespan=lifespan, docs_url=None, redoc_url=None)
allowed_origins=[x.strip() for x in os.getenv('PORTAL_ALLOWED_ORIGINS','').split(',') if x.strip()]
app.add_middleware(CORSMiddleware,allow_origins=allowed_origins,allow_methods=['GET','POST'],allow_headers=['Authorization','Content-Type'],max_age=600)

class Login(BaseModel):
    password:str=Field(max_length=200)

# Bounded, in-memory throttle; no credentials or prompts are logged.
login_attempts={}
@app.post('/login')
async def login(body:Login, request:Request):
    import time
    now=time.monotonic(); key=request.client.host
    for host in list(login_attempts):
        if now-login_attempts[host][0]>60:login_attempts.pop(host,None)
    start,count=login_attempts.get(key,(now,0))
    if count>=20:raise HTTPException(429,'Подождите минуту перед повторным входом')
    if len(login_attempts)>10000:raise HTTPException(429,'Попробуйте позже')
    login_attempts[key]=(start,count+1)
    check_password(body.password)
    return {'token':issue_session(),'expires_in':28800}

@app.get('/version')
async def version():return {'version':'2.0.0','deployment':os.getenv('PORTAL_DEPLOYMENT','local')}

async def authorize(request: Request):
    import hmac
    if not request.url.path.startswith('/bridge/'):
        auth=request.headers.get('authorization','')
        if auth.startswith('Bearer ') and valid_session(auth[7:]):
            origin=request.headers.get('origin')
            if origin and origin not in allowed_origins:raise HTTPException(403,'Этот сайт не разрешён')
            return
    token = os.getenv("APP_ACCESS_TOKEN", "")
    if not token or not hmac.compare_digest(request.headers.get("x-portal-token", ""), token):
        raise HTTPException(401, "Нет доступа")
    origin = request.headers.get("origin")
    if origin:
        # The browser talks only to the same-origin Next proxy.
        raise HTTPException(403, "Прямые запросы браузера запрещены")

class NewTask(BaseModel):
    prompt: str = Field(min_length=1, max_length=24000)
    providers: list[str] = Field(min_length=1, max_length=5)
    mode: Literal["demo", "live"] = "demo"
    request_key: UUID

    @field_validator("prompt")
    @classmethod
    def meaningful(cls, value):
        if not value.strip():
            raise ValueError("Введите задачу")
        return value.strip()

    @field_validator("providers")
    @classmethod
    def known_providers(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("Провайдеры не должны повторяться")
        for value in values:
            if value not in {p['id'] for p in SUBSCRIPTIONS}:
                raise ValueError('Неизвестный сервис')
        return values

@app.get("/health")
async def health(request: Request):
    await request.app.state.pool.fetchval("SELECT 1")
    return {"ok": True}

@app.get("/providers", dependencies=[Depends(authorize)])
async def providers():
    return {"providers": await connections(app.state.pool)}

@app.post("/tasks", dependencies=[Depends(authorize)], status_code=201)
async def create_task(body: NewTask, request: Request):
    pool = request.app.state.pool
    if body.mode == "live":
        available = await connections(pool)
        unavailable=[p['name'] for p in available if p['id'] in body.providers and not p['configured']]
        if unavailable:raise HTTPException(400,'Не подключены: '+', '.join(unavailable)+'. Откройте «Подключения».')
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Lock idempotency key: double clicks/retries never create a second billable task.
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext($1))", str(body.request_key))
            existing = await conn.fetchrow("SELECT id,prompt,mode FROM tasks WHERE request_key=$1", body.request_key)
            if existing:
                old_providers = {r['provider'] for r in await conn.fetch("SELECT provider FROM answers WHERE task_id=$1", existing['id'])}
                if existing['prompt'] != body.prompt or existing['mode'] != body.mode or old_providers != set(body.providers):
                    raise HTTPException(409, "Ключ запроса уже использован для другой задачи")
                return await task_detail(conn, existing['id'])
            await conn.execute("SELECT pg_advisory_xact_lock(419272)")
            active = await conn.fetchval("SELECT count(*) FROM tasks WHERE status IN ('queued','running')")
            if active >= 10:
                raise HTTPException(429, "В очереди уже 10 задач. Дождитесь завершения.")
            task_id = uuid4()
            await conn.execute("INSERT INTO tasks (id,request_key,prompt,mode) VALUES ($1,$2,$3,$4)", task_id, body.request_key, body.prompt, body.mode)
            for p in body.providers:
                c = next(value for value in SUBSCRIPTIONS if value['id']==p)
                await conn.execute("INSERT INTO answers (task_id,provider,model) VALUES ($1,$2,$3)",task_id,p,c['model'])
    return await task_detail(pool, task_id)

@app.get("/tasks", dependencies=[Depends(authorize)])
async def history(request: Request, q: str = "", offset: int = 0):
    if offset < 0 or len(q) > 200:
        raise HTTPException(400, "Некорректный поиск")
    rows = await request.app.state.pool.fetch("""SELECT t.id,t.prompt,t.mode,t.status,t.created_at,t.finished_at,
       count(a.provider)::int AS answer_count, count(*) FILTER (WHERE a.status='completed')::int AS completed_count
       FROM tasks t JOIN answers a ON a.task_id=t.id WHERE t.prompt ILIKE $1
       GROUP BY t.id ORDER BY t.created_at DESC LIMIT 50 OFFSET $2""", "%" + q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_') + "%", offset)
    return {"tasks": [serialize(r) for r in rows]}

@app.get("/tasks/{task_id}", dependencies=[Depends(authorize)])
async def detail(task_id: UUID, request: Request):
    task = await task_detail(request.app.state.pool, task_id)
    if not task:
        raise HTTPException(404, "Задача не найдена")
    return task

@app.post("/tasks/{task_id}/cancel", dependencies=[Depends(authorize)])
async def cancel(task_id: UUID, request: Request):
    pool = request.app.state.pool
    async with pool.acquire() as conn:
        async with conn.transaction():
            task = await conn.fetchrow("SELECT * FROM tasks WHERE id=$1 FOR UPDATE", task_id)
            if not task:
                raise HTTPException(404, "Задача не найдена")
            if task['status'] == 'queued':
                await conn.execute("UPDATE tasks SET cancel_requested=true,status='cancelled',finished_at=now() WHERE id=$1", task_id)
                await conn.execute("UPDATE answers SET status='cancelled',error='Остановлено до отправки запроса.',finished_at=now() WHERE task_id=$1",task_id)
            elif task['status'] == 'running':
                await conn.execute("UPDATE tasks SET cancel_requested=true WHERE id=$1", task_id)
                await conn.execute("UPDATE answers SET status='cancelled',error='Остановлено до отправки.',finished_at=now() WHERE task_id=$1 AND status='queued'",task_id)
                await finish_task(conn,task_id)
    return {"ok": True}

@app.get("/tasks/{task_id}/events", dependencies=[Depends(authorize)])
async def events(task_id: UUID, request: Request):
    pool = request.app.state.pool
    if not await pool.fetchval("SELECT 1 FROM tasks WHERE id=$1", task_id):
        raise HTTPException(404, "Задача не найдена")
    async def stream():
        previous = ""
        while not await request.is_disconnected():
            task = await task_detail(pool, task_id)
            payload = json.dumps(task, ensure_ascii=False)
            if payload != previous:
                yield f"event: snapshot\ndata: {payload}\n\n"
                previous = payload
            else:
                yield ": heartbeat\n\n"
            if task["status"] not in ("queued", "running"):
                yield "event: done\ndata: {}\n\n"
                return
            await asyncio.sleep(.65)
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})

app.include_router(bridge_router,dependencies=[Depends(authorize)])
