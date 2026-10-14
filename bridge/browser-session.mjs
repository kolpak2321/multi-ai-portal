import {readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {root,request,session} from './browser-client.mjs';
const [command,provider,state]=process.argv.slice(2);
const binding=await session();
if(command==='set' && ['deepseek','zai'].includes(provider) && ['on','off'].includes(state)){
  if(process.env.CODEX_THREAD_ID && process.env.CODEX_THREAD_ID!==binding.threadId)throw new Error('Привязка принадлежит другому чату');
  binding.available[provider]=state==='on';
  await writeFile(path.join(root,'.sites-runtime','browser-session.json'),JSON.stringify(binding,null,2),'utf8');
  await request('bridge/heartbeat',{provider,connected:state==='on',note:state==='on'?'Веб-сеанс проверен':'Нужен повторный вход в веб-сеанс'});
  console.log(JSON.stringify({provider,connected:state==='on'}));
}else if(command==='status')console.log(JSON.stringify(binding,null,2));
else throw new Error('Используйте status или set deepseek|zai on|off после проверки вкладки');
