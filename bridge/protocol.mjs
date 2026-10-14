export function buildArgs(work) {
  const args=['--no-daemon','-a','never','exec','--ignore-user-config','--skip-git-repo-check','--ephemeral','--sandbox','read-only','--json','--color','never','-C',work,
    '-c','forced_login_method="chatgpt"','-c','web_search="live"','-c','project_doc_max_bytes=0'];
  for(const feature of ['shell_tool','unified_exec','multi_agent','apps','plugins','hooks','computer_use','browser_use','view_image','image_generation','memories']) args.push('--disable',feature);
  args.push('-');return args;
}

export function sanitizedEnvironment(source) {
  const result={...source};
  for(const key of Object.keys(result)) if(/^(OPENAI_API_KEY|CODEX_API_KEY|CODEX_ACCESS_TOKEN|CODEX_THREAD_ID|CODEX_INTERNAL_ORIGINATOR_OVERRIDE)$/.test(key)) delete result[key];
  return result;
}

export function readEvent(line) {
  let event;try{event=JSON.parse(line);}catch{return {};}
  const result={};
  if(['item.completed','item.updated'].includes(event.type) && event.item?.type==='agent_message' && typeof event.item.text==='string') result.text=event.item.text;
  if(event.type==='turn.completed')result.completed=true;
  if(event.type==='turn.failed'||event.type==='error')result.failed=true;
  if(event.type==='item.completed' && ['web_search','web_search_call'].includes(event.item?.type))result.searched=true;
  return result;
}
