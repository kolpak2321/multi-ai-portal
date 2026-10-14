import {readFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
export const root=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const config=Object.fromEntries((await readFile(path.join(root,'.env'),'utf8')).split(/\r?\n/).filter(l=>l&&!l.startsWith('#')&&l.includes('=')).map(l=>{const i=l.indexOf('=');return[l.slice(0,i),l.slice(i+1).trim()];}));
export async function request(route,body){
  const response=await fetch(`http://127.0.0.1:${config.PORTAL_PORT||8086}/api/`+route,{method:'POST',headers:{'Content-Type':'application/json','X-Portal-Bridge':config.APP_ACCESS_TOKEN},body:JSON.stringify(body),signal:AbortSignal.timeout(10000)});
  if(!response.ok)throw new Error(`Локальный сервер: ${response.status}`);
  return await response.json();
}
export async function session(){return JSON.parse(await readFile(path.join(root,'.sites-runtime','browser-session.json'),'utf8'));}
