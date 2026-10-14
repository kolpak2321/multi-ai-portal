import os
import asyncio
from pathlib import Path
import asyncpg

async def connect():
    for attempt in range(30):
        try:
            pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=1, max_size=10)
            async with pool.acquire() as conn:
                # Serialize bootstrap between API and worker; migrations can replace
                # this initial, additive schema bootstrap in later versions.
                async with conn.transaction():
                    await conn.execute("SELECT pg_advisory_xact_lock(419271)")
                    await conn.execute(Path(__file__).with_name("schema.sql").read_text())
                    await conn.execute(Path(__file__).with_name("subscription-schema.sql").read_text())
            return pool
        except (OSError, asyncpg.PostgresConnectionError):
            if attempt == 29:
                raise
            await asyncio.sleep(1)

def serialize(row):
    import datetime
    from decimal import Decimal
    from uuid import UUID
    return {k: str(v) if isinstance(v, UUID) else v.isoformat() if isinstance(v, datetime.datetime) else float(v) if isinstance(v, Decimal) else v for k, v in dict(row).items()}

async def task_detail(pool, task_id):
    task = await pool.fetchrow("SELECT * FROM tasks WHERE id=$1", task_id)
    if not task:
        return None
    result = serialize(task)
    result.pop("request_key", None)
    result["answers"] = [serialize(r) for r in await pool.fetch("SELECT * FROM answers WHERE task_id=$1 ORDER BY provider", task_id)]
    import json
    raw_sources=await pool.fetchval('SELECT submitted FROM browser_dispatches WHERE task_id=$1',task_id)
    sources=json.loads(raw_sources) if raw_sources else {}
    for answer in result['answers']:
        answer['source_url']=sources.get(answer['provider']) or answer.get('source_url')
        if result['mode']=='demo':
            answer['content']=answer['content'].replace('API Z.ai','сервис Z.ai').replace('API Kimi','сервис Kimi')
        for name in ('input_tokens','output_tokens','cached_tokens','cache_write_tokens','usage_complete','cost_usd','cost_status','rates','rates_date','rates_model'):
            answer.pop(name,None)
    return result
