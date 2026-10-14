"""Weekly portal-only history cleanup. Never touches provider conversations."""
from datetime import datetime,timedelta,timezone

TOMSK=timezone(timedelta(hours=7))

def latest_slot(now):
    local=now.astimezone(TOMSK)
    slot=(local-timedelta(days=(local.weekday()-5)%7)).replace(hour=4,minute=0,second=0,microsecond=0)
    if slot>local:slot-=timedelta(days=7)
    return slot

async def cleanup_history(pool,now=None):
    now=now or datetime.now(timezone.utc)
    slot=latest_slot(now)
    async with pool.acquire() as conn:
        async with conn.transaction():
            if not await conn.fetchval('SELECT pg_try_advisory_xact_lock(419273)'):return 0
            state=await conn.fetchrow("SELECT last_slot FROM portal_maintenance WHERE name='history_cleanup' FOR UPDATE")
            # First installation schedules the next Saturday; no immediate deletion.
            if state is None:
                await conn.execute("INSERT INTO portal_maintenance(name,last_slot) VALUES('history_cleanup',$1)",slot)
                return 0
            if state['last_slot']>=slot:return 0
            count=await conn.fetchval("""WITH removed AS (
                DELETE FROM tasks WHERE status IN ('completed','partial','error','cancelled','interrupted')
                AND COALESCE(finished_at,created_at)<$1
                RETURNING id) SELECT count(*) FROM removed""",slot)
            await conn.execute("UPDATE portal_maintenance SET last_slot=$1,last_run_at=$2,deleted_tasks=$3 WHERE name='history_cleanup'",slot,now,count)
            return count
