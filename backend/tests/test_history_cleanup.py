from datetime import datetime,timezone
from uuid import uuid4
from history_cleanup import latest_slot,cleanup_history
from test_subscriptions import portal,body,ready

def test_saturday_tomsk_boundary():
 assert latest_slot(datetime(2026,10,16,20,59,tzinfo=timezone.utc)).day==10
 assert latest_slot(datetime(2026,10,16,21,0,tzinfo=timezone.utc)).day==17

async def test_cleanup_only_finished_history_and_catches_missed_saturday(portal):
 c,pool=portal
 wed=datetime(2026,10,14,tzinfo=timezone.utc)
 assert await cleanup_history(pool,wed)==0
 await ready(c)
 done=(await c.post('/tasks',json=body())).json()['id']
 active=(await c.post('/tasks',json=body())).json()['id']
 recent=(await c.post('/tasks',json=body())).json()['id']
 await pool.execute("UPDATE tasks SET status='completed',finished_at='2026-10-14T00:00:00Z' WHERE id=$1",__import__('uuid').UUID(done))
 await pool.execute("UPDATE tasks SET status='completed',finished_at='2026-10-17T00:00:00Z' WHERE id=$1",__import__('uuid').UUID(recent))
 assert await cleanup_history(pool,wed)==0
 monday=datetime(2026,10,19,tzinfo=timezone.utc)
 assert await cleanup_history(pool,monday)==1
 assert await pool.fetchval('SELECT count(*) FROM answers WHERE task_id=$1',__import__('uuid').UUID(done))==0
 assert await pool.fetchval('SELECT count(*) FROM tasks')==2
 assert await pool.fetchval('SELECT count(*) FROM subscription_bridges')==1
 assert await cleanup_history(pool,monday)==0
