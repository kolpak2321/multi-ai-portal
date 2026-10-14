import asyncio
from uuid import uuid4
from test_subscriptions import portal,body

async def test_three_independent_claims_and_public_session(portal,monkeypatch):
    c,pool=portal
    monkeypatch.setenv('PORTAL_LOGIN_PASSWORD','test-password')
    for provider in ('openai','deepseek','zai'):
        await c.post('/bridge/heartbeat',json={'provider':provider,'connected':True,'note':'test'})
    t=(await c.post('/tasks',json=body(providers=['openai','deepseek','zai']))).json()
    owners={p:str(uuid4()) for p in ('openai','deepseek','zai')}
    results=await asyncio.gather(*(c.post('/bridge/claim',json={'provider':p,'runner_id':owners[p]}) for p in owners))
    # SKIP LOCKED can defer a competing provider for one polling iteration.
    for p,r in zip(owners,results):
        for _ in range(10):
            if r.json()['task']:break
            await asyncio.sleep(.05)
            r=await c.post('/bridge/claim',json={'provider':p,'runner_id':owners[p]})
        assert r.json()['task']['id']==t['id']
    for p in ('zai','deepseek','openai'):
        await c.post('/bridge/tasks/'+t['id']+'/update',json={'provider':p,'runner_id':owners[p],'content':p,'status':'completed'})
    assert (await c.get('/tasks/'+t['id'])).json()['status']=='completed'
    login=await c.post('/login',json={'password':'test-password'})
    token=login.json()['token']
    headers={'x-portal-token':'','Authorization':'Bearer '+token}
    assert (await c.get('/tasks/'+t['id'],headers=headers)).status_code==200
    assert (await c.post('/bridge/claim',json={'runner_id':str(uuid4())},headers=headers)).status_code==401
