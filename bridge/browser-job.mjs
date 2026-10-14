import {readFile} from 'node:fs/promises';
import {request,session} from './browser-client.mjs';
const [command,task_id,dispatch_id,provider,value,status='completed']=process.argv.slice(2);
if(!/^[0-9a-f-]{36}$/.test(task_id||'')||!/^[0-9a-f-]{36}$/.test(dispatch_id||''))throw new Error('Неверный идентификатор задания');
const job=await request('bridge/browser/job',{task_id,dispatch_id});
if(command==='open'){
  console.log(JSON.stringify({...job,browser:await session()},null,2));
}else if(job.terminal){console.log(JSON.stringify({terminal:true,status:job.task.status}));}
else{
  if(!['deepseek','zai'].includes(provider))throw new Error('Неподдерживаемый сервис');
  if(command==='submitted')console.log(JSON.stringify(await request('bridge/browser/submitted',{task_id,dispatch_id,provider,url:value})));
  else if(command==='save'){
    if(!['completed','error','cancelled','running'].includes(status))throw new Error('Неверный статус');
    const content=await readFile(value,'utf8');
    console.log(JSON.stringify(await request(`bridge/tasks/${task_id}/update`,{runner_id:job.runner_id,provider,content,status,error:status==='error'?'Не удалось завершить запрос во вкладке. Сохранённые сведения — в тексте ответа.':null})));
  }else throw new Error('Команда: open, submitted или save');
}
