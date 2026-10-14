"""Subscription CLI worker, independent from the browser processes."""
import asyncio,json,os,time
from uuid import uuid4
import httpx
RUNNER=str(uuid4())
async def main():
    async with httpx.AsyncClient(base_url='http://api:8000',headers={'X-Portal-Token':os.environ['APP_ACCESS_TOKEN']},timeout=15) as c:
        async def post(route,body):
            r=await c.post('/bridge/'+route,json=body);r.raise_for_status();return r.json()
        while True:
            try:
                auth=await asyncio.create_subprocess_exec('codex','login','status',stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT)
                output,_=await auth.communicate();ready=auth.returncode==0 and b'ChatGPT' in output
                await post('heartbeat',{'provider':'openai','connected':ready,'note':'Подписка ChatGPT на сервере' if ready else 'Нужен вход ChatGPT на сервере'})
                job=await post('claim',{'runner_id':RUNNER,'provider':'openai'}) if ready else {'task':None}
                if job['task']:await execute(job['task'],post)
            except Exception as e:print(type(e).__name__,flush=True)
            await asyncio.sleep(3)
async def execute(task,post):
    content='';complete=False;error=None;cancelled=False
    async def save(status='running'):
        return await post('tasks/'+task['id']+'/update',{'runner_id':RUNNER,'provider':'openai','content':content,'status':status,'error':error})
    args=['codex','exec','--skip-git-repo-check','--ephemeral','--sandbox','read-only','--json','-c','forced_login_method="chatgpt"','-c','web_search="live"','-c','project_doc_max_bytes=0']
    for feature in ['shell_tool','unified_exec','multi_agent','apps','plugins','hooks','computer_use','browser_use','view_image','image_generation','memories']:args+=['--disable',feature]
    args+=['-']
    proc=await asyncio.create_subprocess_exec(*args,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,cwd='/tmp',limit=1024*1024)
    proc.stdin.write(('Ответь на русском на вопрос пользователя. Используй веб-поиск при необходимости и приводи прямые Markdown-ссылки. Не выполняй команды, не читай и не меняй файлы, не взаимодействуй с аккаунтами. Вопрос:\n'+task['prompt']).encode());await proc.stdin.drain();proc.stdin.close()
    async def read():
        nonlocal content,complete,error
        async for line in proc.stdout:
            try:event=json.loads(line)
            except ValueError:continue
            item=event.get('item',{})
            if event.get('type') in ('item.completed','item.updated') and item.get('type')=='agent_message':content=item.get('text','')
            if event.get('type')=='turn.completed':complete=True
            if event.get('type') in ('error','turn.failed'):error='Codex не завершил запрос; проверьте вход и лимит подписки.'
    reader=asyncio.create_task(read());deadline=time.monotonic()+600
    try:
        while proc.returncode is None:
            state=await save()
            if state['cancel_requested'] or time.monotonic()>deadline:
                cancelled=state['cancel_requested'];error=None if cancelled else 'Истекло время ожидания';proc.terminate();break
            await asyncio.sleep(2)
        await asyncio.wait_for(proc.wait(),15);await reader
        if not cancelled and (not complete or proc.returncode or not content):error=error or 'Codex завершился без полного ответа. Повтора не было.'
    except Exception:
        if proc.returncode is None:proc.kill();await proc.wait()
        reader.cancel();error='Обработчик прерван. Повтора не было.'
    await save('cancelled' if cancelled else 'error' if error else 'completed')
if __name__=='__main__':asyncio.run(main())
