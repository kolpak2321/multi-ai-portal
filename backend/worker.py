"""Docker worker handles demonstration tasks and lease recovery only."""
import asyncio
import logging
import time
from db import connect
from demo import demo_answer
from history_cleanup import cleanup_history

logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
log=logging.getLogger('portal')

async def run_provider(pool,task,answer):
    task_id,provider=task['id'],answer['provider']
    content='';status='completed';error=None;last_save=0
    await pool.execute("UPDATE answers SET status='running',started_at=now() WHERE task_id=$1 AND provider=$2",task_id,provider)
    try:
        if task['mode']!='demo': raise RuntimeError('Эту задачу должен выполнять локальный обработчик Codex')
        if await pool.fetchval('SELECT cancel_requested FROM tasks WHERE id=$1',task_id): raise asyncio.CancelledError()
        async for event in demo_answer(provider):
            content+=event.get('text','')
            if time.monotonic()-last_save>.35:
                await pool.execute('UPDATE answers SET content=$3 WHERE task_id=$1 AND provider=$2',task_id,provider,content)
                last_save=time.monotonic()
    except asyncio.CancelledError:
        status,error='cancelled','Остановлено пользователем.'
    except Exception:
        status,error='error','Не удалось показать демонстрационный ответ.'
    finally:
        await pool.execute('UPDATE answers SET status=$3,content=$4,error=$5,finished_at=now() WHERE task_id=$1 AND provider=$2',task_id,provider,status,content,error)

async def run_task(pool,task):
    answers=await pool.fetch('SELECT * FROM answers WHERE task_id=$1',task['id'])
    jobs=[asyncio.create_task(run_provider(pool,task,a)) for a in answers]
    try:
        while any(not j.done() for j in jobs):
            cancel=await pool.fetchval('UPDATE tasks SET heartbeat_at=now() WHERE id=$1 RETURNING cancel_requested',task['id'])
            if cancel:
                for job in jobs:
                    if not job.done():job.cancel()
            await asyncio.sleep(.5)
        await asyncio.gather(*jobs,return_exceptions=True)
        await pool.execute("UPDATE answers SET status='interrupted',error='Не удалось сохранить завершение ответа.',finished_at=now() WHERE task_id=$1 AND status IN ('queued','running')",task['id'])
        statuses=[r['status'] for r in await pool.fetch('SELECT status FROM answers WHERE task_id=$1',task['id'])]
        final='cancelled' if 'cancelled' in statuses else 'completed' if all(s=='completed' for s in statuses) else 'partial' if 'completed' in statuses else 'error'
        await pool.execute('UPDATE tasks SET status=$2,finished_at=now() WHERE id=$1',task['id'],final)
    finally:
        for job in jobs:
            if not job.done():job.cancel()
        await asyncio.gather(*jobs,return_exceptions=True)

async def recover_stale(conn):
    rows=await conn.fetch("UPDATE tasks SET status='interrupted',finished_at=now() WHERE status='running' AND heartbeat_at < now()-interval '45 seconds' RETURNING id")
    for row in rows:
        await conn.execute("UPDATE answers SET status='interrupted',error='Обработчик был перезапущен. Сохранённая часть ответа осталась в истории; автоматического повтора не было.',finished_at=now() WHERE task_id=$1 AND status IN ('queued','running')",row['id'])

async def main():
    pool=await connect();log.info('Worker ready: demonstration queue, recovery, Saturday 04:00 Asia/Tomsk history cleanup')
    last_cleanup_check=0
    try:
        while True:
            if time.monotonic()-last_cleanup_check>30:
                try:
                    removed=await cleanup_history(pool)
                    if removed:log.info('Weekly portal history cleanup: %s tasks removed',removed)
                    last_cleanup_check=time.monotonic()
                except Exception:log.exception('History cleanup failed; will retry')
            async with pool.acquire() as conn:
                async with conn.transaction():
                    await recover_stale(conn)
                    task=await conn.fetchrow("UPDATE tasks SET status='running',started_at=now(),heartbeat_at=now() WHERE id=(SELECT id FROM tasks WHERE status='queued' AND mode='demo' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *")
            if task:
                try:await run_task(pool,task)
                except Exception:log.warning('Task interrupted; partial answers will remain saved')
            else:await asyncio.sleep(.5)
    finally:await pool.close()

if __name__=='__main__':asyncio.run(main())
