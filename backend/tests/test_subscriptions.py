import os
import asyncio
import time
from uuid import uuid4,UUID
from pathlib import Path
import asyncpg
import httpx
import pytest_asyncio
from main import app
from worker import run_task,recover_stale

@pytest_asyncio.fixture
async def portal(monkeypatch):
    name='test_'+uuid4().hex
    admin=await asyncpg.connect(os.environ['DATABASE_URL'])
    await admin.execute(f'CREATE SCHEMA "{name}"')
    pool=await asyncpg.create_pool(os.environ['DATABASE_URL'],min_size=1,max_size=10,server_settings={'search_path':name})
    for file in ('schema.sql','subscription-schema.sql'):
        await pool.execute(Path(__file__).parents[1].joinpath(file).read_text())
    app.state.pool=pool;monkeypatch.setenv('APP_ACCESS_TOKEN','integration-token')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',headers={'x-portal-token':'integration-token'}) as client:
        yield client,pool
    await pool.close();await admin.execute(f'DROP SCHEMA "{name}" CASCADE');await admin.close()

def body(**overrides):
    return {'prompt':'Проверка подписки','providers':['openai'],'mode':'live','request_key':str(uuid4()),**overrides}

async def ready(client):
    return await client.post('/bridge/heartbeat',json={'connected':True,'note':'Подписка ChatGPT подключена'})

async def test_only_chatgpt_subscription_ready(portal):
    c,_=portal
    assert (await c.post('/tasks',json=body())).status_code==400
    await ready(c)
    providers=(await c.get('/providers')).json()['providers']
    assert [p['id'] for p in providers if p['configured']]==['openai']
    assert (await c.post('/tasks',json=body(providers=['openai','deepseek']))).status_code==400
    assert (await c.post('/tasks',json=body())).status_code==201

async def test_dead_bridge_not_ready(portal):
    c,pool=portal;await ready(c)
    await pool.execute("UPDATE subscription_bridges SET seen_at=now()-interval '30 seconds'")
    assert not (await c.get('/providers')).json()['providers'][0]['configured']

async def test_authentication_and_validation(portal):
    c,_=portal
    assert (await c.post('/bridge/claim',json={'runner_id':str(uuid4())},headers={'x-portal-token':'wrong'})).status_code==401
    assert (await c.post('/bridge/heartbeat',json={'connected':True,'note':'fixture'},headers={'origin':'http://evil.example'})).status_code==403
    assert (await c.post('/tasks',json=body(prompt='  '))).status_code==422
    assert (await c.post('/tasks',json=body(providers=['unknown']))).status_code==422
    assert (await c.post('/tasks',json=body(providers=['openai','openai']))).status_code==422

async def test_idempotency_and_exclusive_lease(portal):
    c,pool=portal;await ready(c);request=body()
    responses=await asyncio.gather(*[c.post('/tasks',json=request) for _ in range(3)])
    ids={r.json()['id'] for r in responses};assert len(ids)==1
    runners=[str(uuid4()),str(uuid4())]
    leases=await asyncio.gather(*[c.post('/bridge/claim',json={'runner_id':r}) for r in runners])
    assert sum(r.json()['task'] is not None for r in leases)==1
    owner=next(runners[i] for i,r in enumerate(leases) if r.json()['task'])
    other=next(r for r in runners if r!=owner);task_id=ids.pop()
    assert (await c.post(f'/bridge/tasks/{task_id}/update',json={'runner_id':other,'content':'unauthorized'})).status_code==409
    assert (await c.post('/tasks',json={**request,'prompt':'Другая задача'})).status_code==409

async def test_response_history_sse_and_no_billing_fields(portal):
    c,_=portal;await ready(c)
    task=(await c.post('/tasks',json=body())).json();runner=str(uuid4())
    await c.post('/bridge/claim',json={'runner_id':runner})
    text='Ответ с [источником](https://openai.com/).'
    result=await c.post(f"/bridge/tasks/{task['id']}/update",json={'runner_id':runner,'content':text,'status':'completed'})
    assert result.status_code==200
    detail=(await c.get('/tasks/'+task['id'])).json()
    assert detail['status']=='completed' and detail['answers'][0]['content']==text
    assert 'cost_usd' not in detail['answers'][0] and 'rates' not in detail['answers'][0]
    history=(await c.get('/tasks')).json()['tasks'][0]
    assert history['id']==task['id'] and 'known_cost' not in history
    assert (await c.get('/stats')).status_code==404
    stream=await c.get('/tasks/'+task['id']+'/events')
    assert 'event: snapshot' in stream.text and 'event: done' in stream.text

async def test_cancel_and_partial_answer_preserved(portal):
    c,_=portal;await ready(c)
    task=(await c.post('/tasks',json=body())).json();runner=str(uuid4())
    await c.post('/bridge/claim',json={'runner_id':runner})
    await c.post('/tasks/'+task['id']+'/cancel')
    result=await c.post(f"/bridge/tasks/{task['id']}/update",json={'runner_id':runner,'content':'Часть ответа'})
    assert result.json()['cancel_requested']
    await c.post(f"/bridge/tasks/{task['id']}/update",json={'runner_id':runner,'content':'Часть ответа','status':'cancelled'})
    detail=(await c.get('/tasks/'+task['id'])).json()
    assert detail['status']=='cancelled' and detail['answers'][0]['content']=='Часть ответа'

async def test_queued_cancel_never_claimed(portal):
    c,_=portal;await ready(c)
    task=(await c.post('/tasks',json=body())).json()
    await c.post('/tasks/'+task['id']+'/cancel')
    assert (await c.post('/bridge/claim',json={'runner_id':str(uuid4())})).json()['task'] is None

async def test_restart_does_not_repeat_subscription_request(portal):
    c,pool=portal;await ready(c)
    task=(await c.post('/tasks',json=body())).json();runner=str(uuid4())
    await c.post('/bridge/claim',json={'runner_id':runner})
    await c.post(f"/bridge/tasks/{task['id']}/update",json={'runner_id':runner,'content':'Сохранённый ответ'})
    await pool.execute("UPDATE tasks SET heartbeat_at=now()-interval '60 seconds' WHERE id=$1",UUID(task['id']))
    await recover_stale(pool)
    result=(await c.get('/tasks/'+task['id'])).json()
    assert result['status']=='interrupted' and result['answers'][0]['content']=='Сохранённый ответ'
    assert (await c.post('/bridge/claim',json={'runner_id':str(uuid4())})).json()['task'] is None

async def test_demo_still_parallel_and_separate_from_subscription(portal):
    c,pool=portal
    task=(await c.post('/tasks',json=body(mode='demo',providers=['openai','claude','zai','deepseek','kimi']))).json()
    assert (await c.post('/bridge/claim',json={'runner_id':str(uuid4())})).json()['task'] is None
    row=await pool.fetchrow("UPDATE tasks SET status='running',started_at=now(),heartbeat_at=now() WHERE id=$1 RETURNING *",UUID(task['id']))
    start=time.monotonic();await run_task(pool,row);assert time.monotonic()-start<6
    result=(await c.get('/tasks/'+task['id'])).json()
    assert result['status']=='completed' and len(result['answers'])==5
    assert all('демонстрационный' in a['content'] for a in result['answers'])

async def ready_web(client):
    await ready(client)
    for provider in ['deepseek','zai']:
        await client.post('/bridge/heartbeat',json={'provider':provider,'connected':True,'note':'Проверен вход'})

async def test_three_connections_available_and_independent_results(portal):
    c,_=portal;await ready_web(c)
    available=(await c.get('/providers')).json()['providers']
    assert {p['id'] for p in available if p['configured']}=={'openai','deepseek','zai'}
    task=(await c.post('/tasks',json=body(providers=['openai','deepseek','zai']))).json()
    runner=str(uuid4());browser_runner=str(uuid4())
    await c.post('/bridge/claim',json={'runner_id':runner})
    job=(await c.post('/bridge/browser/next',json={'runner_id':browser_runner})).json()['job']
    await c.post('/bridge/browser/ack',json=job)
    await c.post(f"/bridge/tasks/{task['id']}/update",json={'runner_id':runner,'content':'OpenAI answer','status':'completed'})
    assert (await c.get('/tasks/'+task['id'])).json()['status']=='running'
    opened=(await c.post('/bridge/browser/job',json=job)).json()
    assert not opened['terminal']
    replies=await asyncio.gather(*[c.post(f"/bridge/tasks/{task['id']}/update",json={'runner_id':browser_runner,'provider':p,'content':p+' answer','status':'completed'}) for p in ['deepseek','zai']])
    assert all(r.status_code==200 for r in replies)
    result=(await c.get('/tasks/'+task['id'])).json()
    assert result['status']=='completed' and len(result['answers'])==3
    assert {a['content'] for a in result['answers']}=={'OpenAI answer','deepseek answer','zai answer'}
    assert (await c.post('/bridge/browser/job',json=job)).json()['terminal']

async def test_web_dispatch_only_once_and_nonce_checked(portal):
    c,_=portal;await ready_web(c)
    task=(await c.post('/tasks',json=body(providers=['zai']))).json();runner=str(uuid4())
    results=await asyncio.gather(*[c.post('/bridge/browser/next',json={'runner_id':runner}) for _ in range(3)])
    jobs=[r.json()['job'] for r in results if r.json()['job']]
    assert len(jobs)==1
    job=jobs[0]
    assert (await c.post('/bridge/browser/job',json={**job,'dispatch_id':str(uuid4())})).status_code==404
    await c.post('/bridge/browser/job',json=job)
    assert (await c.post('/bridge/browser/submitted',json={**job,'provider':'zai','url':'https://evil.example/'})).status_code==400
    good={**job,'provider':'zai','url':'https://chat.z.ai/c/fixture'}
    assert (await c.post('/bridge/browser/submitted',json=good)).status_code==200
    assert (await c.post('/bridge/browser/submitted',json=good)).status_code==200
    assert (await c.post('/bridge/browser/submitted',json={**good,'url':'https://chat.z.ai/c/second'})).status_code==409
    assert (await c.post('/bridge/browser/job',json=job)).json()['submitted']=={'zai':good['url']}

async def test_web_queue_failure_preserves_successful_openai(portal):
    c,_=portal;await ready_web(c)
    task=(await c.post('/tasks',json=body(providers=['openai','deepseek']))).json();runner=str(uuid4())
    await c.post('/bridge/claim',json={'runner_id':runner})
    await c.post(f"/bridge/tasks/{task['id']}/update",json={'runner_id':runner,'content':'Ответ OpenAI','status':'completed'})
    job=(await c.post('/bridge/browser/next',json={'runner_id':str(uuid4())})).json()['job']
    await c.post('/bridge/browser/ack',json={**job,'error':'Нет связи с чатом Codex'})
    result=(await c.get('/tasks/'+task['id'])).json()
    assert result['status']=='partial'
    assert next(a for a in result['answers'] if a['provider']=='openai')['content']=='Ответ OpenAI'

async def test_browser_wait_heartbeat_and_timeout_no_duplicate(portal):
    c,pool=portal;await ready_web(c)
    task=(await c.post('/tasks',json=body(providers=['deepseek']))).json();runner=str(uuid4())
    job=(await c.post('/bridge/browser/next',json={'runner_id':runner})).json()['job']
    await c.post('/bridge/browser/job',json=job)
    await pool.execute("UPDATE tasks SET heartbeat_at=now()-interval '60 seconds' WHERE id=$1",UUID(task['id']))
    await c.post('/bridge/browser/tick',json={'runner_id':runner});await recover_stale(pool)
    assert (await c.get('/tasks/'+task['id'])).json()['status']=='running'
    await pool.execute("UPDATE browser_dispatches SET created_at=now()-interval '16 minutes' WHERE task_id=$1",UUID(task['id']))
    await c.post('/bridge/browser/tick',json={'runner_id':runner})
    assert (await c.get('/tasks/'+task['id'])).json()['status']=='error'
    assert (await c.post('/bridge/browser/next',json={'runner_id':runner})).json()['job'] is None

async def test_cancel_after_first_response_finishes_waiting_web(portal):
    c,_=portal;await ready_web(c)
    task=(await c.post('/tasks',json=body(providers=['openai','zai']))).json();runner=str(uuid4())
    await c.post('/bridge/claim',json={'runner_id':runner})
    await c.post(f"/bridge/tasks/{task['id']}/update",json={'runner_id':runner,'content':'Ответ','status':'completed'})
    await c.post('/tasks/'+task['id']+'/cancel')
    result=(await c.get('/tasks/'+task['id'])).json()
    assert result['status']=='cancelled'
    assert next(a for a in result['answers'] if a['provider']=='zai')['status']=='cancelled'

async def test_dispatcher_restart_does_not_resend_or_lose_pending_task(portal):
    c,_=portal;await ready_web(c)
    first=(await c.post('/tasks',json=body(providers=['zai']))).json()
    await c.post('/bridge/browser/next',json={'runner_id':str(uuid4())})
    await c.post('/bridge/browser/tick',json={'runner_id':str(uuid4())})
    result=(await c.get('/tasks/'+first['id'])).json()
    assert result['status']=='error'
    assert (await c.post('/bridge/browser/next',json={'runner_id':str(uuid4())})).json()['job'] is None
    second=(await c.post('/tasks',json=body(providers=['zai']))).json()
    job=(await c.post('/bridge/browser/next',json={'runner_id':str(uuid4())})).json()['job']
    await c.post('/bridge/browser/ack',json=job)
    await c.post('/bridge/browser/tick',json={'runner_id':str(uuid4())})
    assert (await c.get('/tasks/'+second['id'])).json()['status']=='queued'
    assert not (await c.post('/bridge/browser/job',json=job)).json()['terminal']
