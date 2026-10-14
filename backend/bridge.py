import json
from uuid import UUID,uuid4
from typing import Literal
from fastapi import APIRouter,Request,HTTPException
from pydantic import BaseModel,Field
from db import task_detail
from task_state import finish_task
from subscriptions import PROVIDERS

router=APIRouter(prefix='/bridge')
Provider=Literal['openai','deepseek','zai','claude','kimi']
WEB=('deepseek','zai')

class Heartbeat(BaseModel):
    connected:bool
    note:str=Field(max_length=300)
    provider:Provider='openai'

class Claim(BaseModel):
    runner_id:UUID
    provider:Provider='openai'

class Update(BaseModel):
    runner_id:UUID
    provider:Provider='openai'
    content:str=Field(default='',max_length=250000)
    status:Literal['running','completed','error','cancelled']='running'
    error:str|None=Field(default=None,max_length=1000)
    source_url:str|None=Field(default=None,max_length=2000)
    actual_model:str|None=Field(default=None,max_length=200)

class WebRunner(BaseModel):
    runner_id:UUID

class WebJob(BaseModel):
    task_id:UUID
    dispatch_id:UUID

class WebSubmitted(WebJob):
    provider:Literal['deepseek','zai']
    url:str=Field(max_length=2000)

class WebAck(WebJob):
    error:str|None=Field(default=None,max_length=1000)

@router.post('/heartbeat')
async def heartbeat(body:Heartbeat,request:Request):
    await request.app.state.pool.execute("INSERT INTO subscription_bridges(provider,connected,note,seen_at) VALUES($1,$2,$3,now()) ON CONFLICT(provider) DO UPDATE SET connected=$2,note=$3,seen_at=now()",body.provider,body.connected,body.note)
    return {'ok':True}

@router.post('/claim')
async def claim(body:Claim,request:Request):
    pool=request.app.state.pool
    async with pool.acquire() as conn:
        async with conn.transaction():
            task=await conn.fetchrow("""SELECT t.* FROM tasks t WHERE t.mode='live' AND t.status IN ('queued','running')
                AND NOT t.cancel_requested AND EXISTS(SELECT 1 FROM answers a WHERE a.task_id=t.id AND a.provider=$1 AND a.status='queued')
                ORDER BY t.created_at FOR UPDATE OF t SKIP LOCKED LIMIT 1""",body.provider)
            if not task:return {'task':None}
            await conn.execute("UPDATE tasks SET status='running',started_at=COALESCE(started_at,now()),heartbeat_at=now() WHERE id=$1",task['id'])
            await conn.execute('INSERT INTO answer_claims(task_id,provider,runner_id) VALUES($1,$2,$3)',task['id'],body.provider,body.runner_id)
            if body.provider=='openai':await conn.execute('INSERT INTO subscription_claims(task_id,runner_id) VALUES($1,$2) ON CONFLICT DO NOTHING',task['id'],body.runner_id)
            await conn.execute("UPDATE answers SET status='running',started_at=now() WHERE task_id=$1 AND provider=$2",task['id'],body.provider)
    return {'task':await task_detail(pool,task['id'])}

@router.post('/tasks/{task_id}/update')
async def update(task_id:UUID,body:Update,request:Request):
    if body.source_url:
        from urllib.parse import urlparse
        parsed=urlparse(body.source_url)
        domain={'deepseek':'chat.deepseek.com','zai':'chat.z.ai','openai':'chatgpt.com','claude':'claude.ai','kimi':'www.kimi.com'}[body.provider]
        if parsed.scheme!='https' or parsed.hostname!=domain:raise HTTPException(400,'Неверная ссылка на диалог')
    pool=request.app.state.pool
    async with pool.acquire() as conn:
        async with conn.transaction():
            task=await conn.fetchrow('SELECT * FROM tasks WHERE id=$1 FOR UPDATE',task_id)
            owner=await conn.fetchval('SELECT runner_id FROM answer_claims WHERE task_id=$1 AND provider=$2',task_id,body.provider)
            if owner is None and body.provider=='openai':owner=await conn.fetchval('SELECT runner_id FROM subscription_claims WHERE task_id=$1',task_id)
            if not task or owner!=body.runner_id:raise HTTPException(409,'Ответ принадлежит другому обработчику')
            answer=await conn.fetchrow('SELECT status FROM answers WHERE task_id=$1 AND provider=$2',task_id,body.provider)
            if task['status'] not in ('queued','running') or answer['status'] not in ('queued','running'):
                return {'cancel_requested':True,'terminal':True}
            await conn.execute('UPDATE tasks SET heartbeat_at=now() WHERE id=$1',task_id)
            await conn.execute('UPDATE subscription_bridges SET seen_at=now() WHERE provider=$1',body.provider)
            status='cancelled' if task['cancel_requested'] and body.status!='running' else body.status
            model=body.actual_model or next(p['model'] for p in PROVIDERS if p['id']==body.provider)
            await conn.execute("UPDATE answers SET content=$3,status=$4,error=$5,actual_model=$6,finished_at=CASE WHEN $4='running' THEN NULL ELSE now() END WHERE task_id=$1 AND provider=$2",task_id,body.provider,body.content,status,body.error,model)
            if body.source_url:await conn.execute('UPDATE answers SET source_url=$3 WHERE task_id=$1 AND provider=$2',task_id,body.provider,body.source_url)
            await finish_task(conn,task_id)
            return {'cancel_requested':task['cancel_requested'],'terminal':status!='running'}

@router.post('/browser/next')
async def browser_next(body:WebRunner,request:Request):
    pool=request.app.state.pool
    async with pool.acquire() as conn:
        async with conn.transaction():
            task=await conn.fetchrow("""SELECT t.* FROM tasks t WHERE t.mode='live' AND t.status IN ('queued','running') AND NOT t.cancel_requested
                AND EXISTS(SELECT 1 FROM answers a WHERE a.task_id=t.id AND a.provider IN ('zai','deepseek') AND a.status='queued')
                AND NOT EXISTS(SELECT 1 FROM browser_dispatches b WHERE b.task_id=t.id)
                ORDER BY t.created_at FOR UPDATE OF t SKIP LOCKED LIMIT 1""")
            if not task:return {'job':None}
            dispatch_id=uuid4()
            await conn.execute('INSERT INTO browser_dispatches(task_id,dispatch_id,runner_id) VALUES($1,$2,$3)',task['id'],dispatch_id,body.runner_id)
            await conn.execute('UPDATE tasks SET heartbeat_at=now() WHERE id=$1',task['id'])
    return {'job':{'task_id':str(task['id']),'dispatch_id':str(dispatch_id)}}

@router.post('/browser/ack')
async def browser_ack(body:WebAck,request:Request):
    pool=request.app.state.pool
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.fetchrow('SELECT id FROM tasks WHERE id=$1 FOR UPDATE',body.task_id)
            job=await conn.fetchrow('SELECT * FROM browser_dispatches WHERE task_id=$1 AND dispatch_id=$2 FOR UPDATE',body.task_id,body.dispatch_id)
            if not job:raise HTTPException(404,'Задание не найдено')
            if body.error:
                await conn.execute("UPDATE answers SET status='error',error=$2,finished_at=now() WHERE task_id=$1 AND provider IN ('zai','deepseek') AND status='queued'",body.task_id,body.error)
                await conn.execute("UPDATE browser_dispatches SET status='error' WHERE task_id=$1",body.task_id)
                await finish_task(conn,body.task_id)
            else:await conn.execute("UPDATE browser_dispatches SET status='sent' WHERE task_id=$1 AND status='pending'",body.task_id)
    return {'ok':True}

@router.post('/browser/tick')
async def browser_tick(body:WebRunner,request:Request):
    pool=request.app.state.pool
    async with pool.acquire() as conn:
        async with conn.transaction():
            jobs=await conn.fetch("SELECT b.*,b.created_at<now()-interval '15 minutes' AS expired FROM browser_dispatches b WHERE b.status IN ('pending','sent','running')")
            for job in jobs:
                await conn.fetchrow('SELECT id FROM tasks WHERE id=$1 FOR UPDATE',job['task_id'])
                orphan=job['status']=='pending' and job['runner_id']!=body.runner_id
                if job['expired'] or orphan:
                    message='Обработчик перезапущен до подтверждения доставки. Автоматического повтора не было.' if orphan else 'Не удалось завершить работу с вкладкой за 15 минут. Автоматического повтора не было.'
                    await conn.execute("UPDATE answers SET status='error',error=$2,finished_at=now() WHERE task_id=$1 AND provider IN ('zai','deepseek') AND status IN ('queued','running')",job['task_id'],message)
                    await conn.execute("UPDATE browser_dispatches SET status='error' WHERE task_id=$1",job['task_id'])
                    await finish_task(conn,job['task_id'])
                else:
                    remaining=await conn.fetchval("SELECT count(*) FROM answers WHERE task_id=$1 AND provider IN ('zai','deepseek') AND status IN ('queued','running')",job['task_id'])
                    if remaining:await conn.execute('UPDATE tasks SET heartbeat_at=now() WHERE id=$1',job['task_id'])
                    else:await conn.execute("UPDATE browser_dispatches SET status='completed' WHERE task_id=$1",job['task_id'])
    return {'ok':True}

@router.post('/browser/job')
async def browser_job(body:WebJob,request:Request):
    pool=request.app.state.pool
    async with pool.acquire() as conn:
        async with conn.transaction():
            task=await conn.fetchrow('SELECT * FROM tasks WHERE id=$1 FOR UPDATE',body.task_id)
            job=await conn.fetchrow('SELECT * FROM browser_dispatches WHERE task_id=$1 AND dispatch_id=$2',body.task_id,body.dispatch_id)
            if not task or not job:raise HTTPException(404,'Задание не найдено')
            remaining=await conn.fetchval("SELECT count(*) FROM answers WHERE task_id=$1 AND provider IN ('zai','deepseek') AND status IN ('queued','running')",body.task_id)
            if task['status'] not in ('queued','running') or task['cancel_requested'] or not remaining:
                return {'terminal':True,'task':await task_detail(conn,body.task_id)}
            answers=await conn.fetch("SELECT provider FROM answers WHERE task_id=$1 AND provider IN ('zai','deepseek') AND status='queued'",body.task_id)
            for answer in answers:
                await conn.execute('INSERT INTO answer_claims(task_id,provider,runner_id) VALUES($1,$2,$3) ON CONFLICT DO NOTHING',body.task_id,answer['provider'],job['runner_id'])
                await conn.execute("UPDATE answers SET status='running',started_at=COALESCE(started_at,now()) WHERE task_id=$1 AND provider=$2",body.task_id,answer['provider'])
            await conn.execute("UPDATE browser_dispatches SET status='running' WHERE task_id=$1",body.task_id)
            await conn.execute("UPDATE tasks SET status='running',started_at=COALESCE(started_at,now()),heartbeat_at=now() WHERE id=$1",body.task_id)
    return {'terminal':False,'task':await task_detail(pool,body.task_id),'runner_id':str(job['runner_id']),'submitted':json.loads(job['submitted'])}

@router.post('/browser/submitted')
async def browser_submitted(body:WebSubmitted,request:Request):
    from urllib.parse import urlparse
    parsed=urlparse(body.url)
    domain='chat.deepseek.com' if body.provider=='deepseek' else 'chat.z.ai'
    if parsed.scheme!='https' or parsed.hostname!=domain:raise HTTPException(400,'Неверная ссылка на диалог')
    changed=await request.app.state.pool.execute("UPDATE browser_dispatches SET submitted=submitted||$5::jsonb WHERE task_id=$1 AND dispatch_id=$2 AND (NOT (submitted ? $3) OR submitted->>$3=$4)",body.task_id,body.dispatch_id,body.provider,body.url,json.dumps({body.provider:body.url}))
    if changed=='UPDATE 0':raise HTTPException(409,'Задание не найдено или отправка уже зарегистрирована с другой ссылкой')
    return {'ok':True}
