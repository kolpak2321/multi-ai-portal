import { spawn } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { readFile, writeFile, mkdir, unlink } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createInterface } from 'node:readline';
import {buildArgs,sanitizedEnvironment,readEvent} from './protocol.mjs';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const config = Object.fromEntries((await readFile(path.join(root,'.env'),'utf8')).split(/\r?\n/).filter(line=>line && !line.startsWith('#') && line.includes('=')).map(line=>{const i=line.indexOf('=');return [line.slice(0,i),line.slice(i+1).trim()];}));
const url = `http://127.0.0.1:${config.PORTAL_PORT || 8086}/api/`;
const token = config.APP_ACCESS_TOKEN;
if (!token) throw new Error('Сначала запустите start.ps1');
const runnerId = randomUUID();
const work = path.join(root,'.sites-runtime','codex-work');
const lock = path.join(root,'.sites-runtime','codex-bridge.pid');
await mkdir(work,{recursive:true});
try { const old=Number(await readFile(lock,'utf8')); if(old && old!==process.pid) { process.kill(old,0); console.log('Обработчик уже запущен'); process.exit(0); } } catch {}
await writeFile(lock,String(process.pid),{flag:'w'});
let child = null, shuttingDown = false;
const childEnv=sanitizedEnvironment(process.env);
const command=process.env.PORTAL_CODEX_EXE || 'codex';
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function request(route,body) {
  const r=await fetch(url+route,{method:'POST',headers:{'Content-Type':'application/json','X-Portal-Bridge':token},body:JSON.stringify(body),signal:AbortSignal.timeout(10000)});
  if(!r.ok) throw new Error(`Сервер обработчика: ${r.status}`);
  return await r.json();
}
async function chatGPTLogin() {
  return await new Promise(resolve=>{
    const p=spawn(command,['login','status'],{env:childEnv,windowsHide:true});
    let output='';p.stdout.on('data',b=>output+=b);p.stderr.on('data',b=>output+=b);
    p.on('error',()=>resolve(false));p.on('close',code=>resolve(code===0 && /using ChatGPT/i.test(output)));
  });
}
async function execute(task) {
  let content='', error=null, completed=false, stopped=false;
  const args=buildArgs(work);
  child=spawn(command,args,{cwd:work,env:childEnv,windowsHide:true,stdio:['pipe','pipe','pipe']});
  const activeChild=child;
  const lines=createInterface({input:child.stdout});
  let persist=Promise.resolve();
  function save(status='running') {
    persist=persist.then(async()=>{
      const state=await request(`bridge/tasks/${task.id}/update`,{runner_id:runnerId,content,status,error});
      if(state.cancel_requested && !stopped) {stopped=true;activeChild.kill();}
    }).catch(()=>{});
    return persist;
  }
  lines.on('line',line=>{
    const event=readEvent(line);
    if(event.text!==undefined) {content=event.text;void save();}
    if(event.completed) completed=true;
    if(event.failed) error='Codex не завершил запрос. Проверьте вход в ChatGPT и доступный лимит подписки.';
    if(event.searched) console.log(`Задача ${task.id.slice(0,8)}: выполнен веб-поиск`);
  });
  // Diagnostic stderr is deliberately not sent to the browser or logs.
  child.stderr.resume();
  const close=new Promise(resolve=>{child.on('error',()=>{error='Не удалось запустить Codex на компьютере';resolve(1);});child.on('close',resolve);});
  const timer=setInterval(()=>void save(),1500);
  const deadline=setTimeout(()=>{error='Превышено время ожидания (15 минут). Запрос не повторялся.';activeChild.kill();},15*60*1000);
  child.stdin.on('error',()=>{});
  child.stdin.end('Ты — исследовательский помощник портала. Ответь на русском языке. Пользуйся только веб-поиском и чтением общедоступных источников. Не запускай команды, не изменяй файлы, не взаимодействуй с аккаунтами пользователя. Для вопросов о текущих фактах выполняй веб-поиск. Приводи прямые кликабельные Markdown-ссылки на подтверждающие страницы, а не внутренние маркеры цитат. Если поиск не выполнялся, не утверждай обратное. Дай ответ на задачу, а не описание своих возможностей.\n\nЗадача пользователя:\n'+task.prompt);
  const code=await close;clearInterval(timer);clearTimeout(deadline);lines.close();
  await persist;
  if(!stopped && (!completed || code!==0 || !content)) error ||= 'Codex завершился без полного ответа. Автоматического повтора не было.';
  await save(stopped?'cancelled':error?'error':'completed');child=null;
  console.log(`Задача ${task.id.slice(0,8)}: ${stopped?'остановлена':error?'ошибка':'готово'}`);
}
async function stop() {shuttingDown=true;child?.kill();try{await unlink(lock);}catch{}process.exit(0);}
process.on('SIGINT',stop);process.on('SIGTERM',stop);
let connected=false,lastAuth=0;
console.log('Локальный обработчик ChatGPT/Codex запущен');
while(!shuttingDown) {
  try {
    if(Date.now()-lastAuth>60000){connected=await chatGPTLogin();lastAuth=Date.now();}
    await request('bridge/heartbeat',{connected,note:connected?'Подписка ChatGPT подключена через Codex':'Войдите в Codex через ChatGPT'});
    if(connected){const result=await request('bridge/claim',{runner_id:runnerId});if(result.task){await execute(result.task);continue;}}
  } catch {console.log('Ожидаем локальный сервер портала…');}
  await sleep(500);
}
