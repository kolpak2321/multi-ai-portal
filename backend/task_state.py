async def finish_task(conn,task_id):
    rows=await conn.fetch('SELECT status FROM answers WHERE task_id=$1',task_id)
    states=[r['status'] for r in rows]
    if any(s in ('running','queued') for s in states):state='running'
    elif 'cancelled' in states:state='cancelled'
    elif all(s=='completed' for s in states):state='completed'
    elif 'completed' in states:state='partial'
    elif 'interrupted' in states:state='interrupted'
    else:state='error'
    await conn.execute("UPDATE tasks SET status=$2,finished_at=CASE WHEN $2='running' THEN NULL ELSE now() END WHERE id=$1",task_id,state)
    return state
