import test from 'node:test';
import assert from 'node:assert/strict';
import {buildArgs,sanitizedEnvironment,readEvent} from './protocol.mjs';

test('forces subscription authentication, enables search and excludes writes',()=>{
  const args=buildArgs('C:/Workspace with spaces');
  assert.ok(args.includes('forced_login_method="chatgpt"'));
  assert.ok(args.includes('web_search="live"'));
  assert.equal(args[args.indexOf('--sandbox')+1],'read-only');
  assert.ok(!args.includes('--dangerously-bypass-approvals-and-sandbox'));
  assert.ok(args.includes('--no-daemon'));
});
test('shell, computer, plugins and delegation unavailable',()=>{
  const args=buildArgs('work');
  for(const feature of ['shell_tool','unified_exec','multi_agent','apps','plugins','computer_use','browser_use']) {
    const index=args.indexOf(feature);assert.equal(args[index-1],'--disable');
  }
});
test('credentials and parent chat identifiers not inherited',()=>{
  const result=sanitizedEnvironment({OPENAI_API_KEY:'secret',CODEX_API_KEY:'secret2',CODEX_THREAD_ID:'parent',CODEX_HOME:'auth-store',PATH:'tools'});
  assert.deepEqual(result,{CODEX_HOME:'auth-store',PATH:'tools'});
});
test('reads final answer but never reasoning or command text',()=>{
  assert.deepEqual(readEvent(JSON.stringify({type:'item.completed',item:{type:'agent_message',text:'Ответ'}})),{text:'Ответ'});
  assert.deepEqual(readEvent(JSON.stringify({type:'item.completed',item:{type:'reasoning',text:'private'}})),{});
  assert.deepEqual(readEvent(JSON.stringify({type:'item.completed',item:{type:'command_execution',text:'private'}})),{});
});
test('error and malformed events do not become successful answers',()=>{
  assert.deepEqual(readEvent('not JSON'),{});
  assert.deepEqual(readEvent('{"type":"turn.failed"}'),{failed:true});
  assert.deepEqual(readEvent('{"type":"turn.completed"}'),{completed:true});
});
test('recognizes actual search event without logging the query',()=>{
  const event=readEvent(JSON.stringify({type:'item.completed',item:{type:'web_search',query:'private user question'}}));
  assert.deepEqual(event,{searched:true});
});
