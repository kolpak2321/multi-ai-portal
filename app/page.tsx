"use client";
import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { Activity, ArrowDownToLine, ArrowUpRight, Check, Clock3, Copy, History, Layers3, LoaderCircle, Maximize2, MessageSquare, Plus, Search, Send, Settings2, ShieldCheck, Square, Terminal, Trash2, X, Zap } from "lucide-react";

type Provider = { id: string; name: string; company: string; model: string; configured: boolean; url: string; connection?: string; note?: string };
type Answer = { provider: string; model: string; actual_model: string | null; status: string; content: string; error: string | null; started_at: string | null; finished_at: string | null; finish_reason: string | null; source_url?: string | null };
type Task = { id: string; prompt: string; mode: "demo" | "live"; status: string; created_at: string; cancel_requested: boolean; answers: Answer[] };
type HistoryItem = { id: string; prompt: string; mode: "demo" | "live"; status: string; created_at: string; answer_count: number; completed_count: number };
const META: Record<string, { color: string; letter: string; subtitle: string }> = {
  claude: { color: "#df977b", letter: "C", subtitle: "Anthropic" }, openai: { color: "#55c7a5", letter: "◎", subtitle: "Подписка ChatGPT" }, zai: { color: "#a58aff", letter: "Z", subtitle: "GLM" }, deepseek: { color: "#7795ff", letter: "D", subtitle: "DeepSeek" }, kimi: { color: "#da91df", letter: "K", subtitle: "Moonshot AI" },
};
const DEFAULTS: Provider[] = [
  {id:"openai",name:"ChatGPT",company:"OpenAI",model:"Codex · подписка ChatGPT",configured:false,url:"https://chatgpt.com/",connection:"codex"},
  {id:"claude",name:"Claude",company:"Anthropic",model:"Веб-версия Claude",configured:false,url:"https://claude.ai/"},
  {id:"zai",name:"Z.ai",company:"Z.ai",model:"Z.ai · веб-сеанс",configured:false,url:"https://chat.z.ai/",connection:"browser"},
  {id:"deepseek",name:"DeepSeek",company:"DeepSeek",model:"DeepSeek · веб-сеанс",configured:false,url:"https://chat.deepseek.com/",connection:"browser"},
  {id:"kimi",name:"Kimi",company:"Moonshot AI",model:"Веб-версия Kimi",configured:false,url:"https://www.kimi.com/"},
];
const STATUS: Record<string, string> = { queued: "В очереди", running: "Отвечает", completed: "Готово", error: "Ошибка", partial: "Частично", cancelled: "Остановлено", interrupted: "Прервано", truncated: "Лимит длины" };
const EXAMPLES = ["Составь план запуска нового продукта", "Сравни SQL и NoSQL для веб-приложения", "Напиши Python-функцию обработки CSV"];
const REMOTE = process.env.NEXT_PUBLIC_PORTAL_BACKEND_URL || "";
const API_BASE = REMOTE ? REMOTE.replace(/\/$/, "") + "/" : "/api/";
function date(value: string) { return new Date(value).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }); }
function active(task: Task | null) { return !!task && ["queued", "running"].includes(task.status); }
function seconds(answer: Answer) { return answer.started_at ? Math.max(0, (new Date(answer.finished_at || Date.now()).getTime() - new Date(answer.started_at).getTime()) / 1000).toFixed(1) + " с" : "—"; }
async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const token = typeof window !== 'undefined' ? sessionStorage.getItem('portal:session') : null;
  const response = await fetch(API_BASE + path, {...options,cache:'no-store',headers:{...options?.headers,...(REMOTE && token ? {Authorization:`Bearer ${token}`} : {})}}); const body = await response.json();
  if(response.status===401 && REMOTE && sessionStorage.getItem('portal:session')===token) {sessionStorage.removeItem('portal:session');window.dispatchEvent(new Event('portal:login'));}
  if (!response.ok) { const detail = (body as { detail?: unknown })?.detail; throw new Error(typeof detail === "string" ? detail : "Проверьте параметры запроса."); }
  return body as T;
}
// React escapes all model text; never execute raw HTML from model answers.
function Markdown({ text }: { text: string }) {
  return <div className="markdown">{text.split(/(```[\s\S]*?```)/g).map((segment, i) => {
    if (segment.startsWith("```")) return <pre key={i}><code>{segment.replace(/^```[^\n]*\n?/, "").replace(/```$/, "")}</code></pre>;
    return segment.split("\n").map((line, j) => {
      if (line.startsWith("### ")) return <h4 key={`${i}-${j}`}>{line.slice(4)}</h4>;
      if (line.startsWith("## ")) return <h3 key={`${i}-${j}`}>{line.slice(3)}</h3>;
      if (line.startsWith("# ")) return <h3 key={`${i}-${j}`}>{line.slice(2)}</h3>;
      if (!line.trim()) return <div className="paragraph-gap" key={`${i}-${j}`} />;
      const inline = line.split(/(\[[^\]]+\]\(https?:\/\/[^)]+\)|\*\*[^*]+\*\*|`[^`]+`)/g).map((part, k) => part.startsWith("[") ? <a key={k} href={part.slice(part.indexOf("](")+2,-1)} target="_blank" rel="noopener noreferrer">{part.slice(1,part.indexOf("]("))}</a> : part.startsWith("**") ? <strong key={k}>{part.slice(2, -2)}</strong> : part.startsWith("`") ? <code key={k}>{part.slice(1, -1)}</code> : part);
      return <p className={/^[-*] /.test(line) || /^\d+\. /.test(line) ? "list-line" : ""} key={`${i}-${j}`}>{inline}</p>;
    });
  })}</div>;
}

export default function Portal() {
  const [needsLogin,setNeedsLogin]=useState(false),[loginPassword,setLoginPassword]=useState(''),[authEpoch,setAuthEpoch]=useState(0),[loginBusy,setLoginBusy]=useState(false);
  const [providers, setProviders] = useState<Provider[]>(DEFAULTS), [selected, setSelected] = useState<string[]>(["openai"]);
  const [prompt, setPrompt] = useState(""), [mode, setMode] = useState<"demo" | "live">("live"), [task, setTask] = useState<Task | null>(null);
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [search, setSearch] = useState(""), [sending, setSending] = useState(false), [online, setOnline] = useState(false), [streamLost, setStreamLost] = useState(false);
  const [hasMore, setHasMore] = useState(false), [loadingMore, setLoadingMore] = useState(false), searchRef = useRef("");
  const [error, setError] = useState(""), [notice, setNotice] = useState(""), [modal, setModal] = useState<string | null>(null), [sidebar, setSidebar] = useState(false);
  const [, tick] = useState(0), dialog = useRef<HTMLDialogElement>(null), textarea = useRef<HTMLTextAreaElement>(null), source = useRef<EventSource | null>(null), requestKey = useRef<string | null>(null), currentId = useRef<string | null>(null);
  const busy = sending || active(task), ready = providers.filter(p => p.configured).length;
  const doneCount = task?.answers.filter(a => !["queued", "running"].includes(a.status)).length || 0;
  const refresh = useCallback(async () => { const h = await api<{tasks: HistoryItem[]}>("tasks?q=" + encodeURIComponent(searchRef.current)); setHistory(h.tasks); setHasMore(h.tasks.length === 50); }, []);
  useEffect(() => {
    searchRef.current = search;
    if (!online) return;
    let disposed = false;
    const timer = setTimeout(() => { void api<{ tasks: HistoryItem[] }>("tasks?q=" + encodeURIComponent(search)).then(h => { if (!disposed) { setHistory(h.tasks); setHasMore(h.tasks.length === 50); } }).catch(() => {}); }, 250);
    return () => { disposed = true; clearTimeout(timer); };
  }, [search, online]);
  async function loadMore() {
    setLoadingMore(true);
    try { const h = await api<{ tasks: HistoryItem[] }>(`tasks?offset=${history.length}&q=${encodeURIComponent(search)}`); setHistory(old => [...old, ...h.tasks]); setHasMore(h.tasks.length === 50); }
    catch (e) { setError((e as Error).message); } finally { setLoadingMore(false); }
  }
  const follow = useCallback((next: Task) => {
    source.current?.close(); currentId.current = next.id; setTask(next); setPrompt(next.prompt); if(active(next)) setMode(next.mode); setStreamLost(false);
    localStorage.setItem("portal:last-task", next.id);
    if (!active(next)) return;
    if(REMOTE) return;
    const stream = new EventSource(`/api/tasks/${next.id}/events`); source.current = stream;
    stream.addEventListener("snapshot", event => { if (currentId.current !== next.id) return; setTask(JSON.parse((event as MessageEvent).data)); setStreamLost(false); });
    stream.addEventListener("done", () => { stream.close(); void refresh().catch(() => {}); });
    stream.onopen = () => setStreamLost(false); stream.onerror = () => setStreamLost(true);
  }, [refresh]);
  useEffect(() => {
    let disposed = false;
    async function init() {
      try {
        const data = await api<{ providers: Provider[] }>("providers"); if (disposed) return;
        setProviders(data.providers); setSelected(data.providers.filter(p => p.configured).map(p => p.id)); setOnline(true); setMode("live"); await refresh();
        const last = localStorage.getItem("portal:last-task");
        if (last && !disposed) { try { const restored = await api<Task>(`tasks/${last}`); if (!disposed) follow(restored); } catch { localStorage.removeItem("portal:last-task"); } }
      } catch (e) { if (!disposed) setError((e as Error).message); }
    }
    void init(); return () => { disposed = true; source.current?.close(); };
  }, [refresh, follow, authEpoch]);
  useEffect(()=>{const handler=()=>setNeedsLogin(true);window.addEventListener('portal:login',handler);return()=>window.removeEventListener('portal:login',handler);},[]);
  useEffect(() => { if(needsLogin)return;const timer=setInterval(() => {void api<{providers:Provider[]}>("providers").then(data=>{setProviders(data.providers);setOnline(true);}).catch(()=>setOnline(false));},5000); return () => clearInterval(timer); }, [needsLogin]);
  useEffect(() => { if (!active(task)) return; const timer = setInterval(() => tick(n => n + 1), 1000); return () => clearInterval(timer); }, [task?.status]);
  useEffect(() => {
    if (!task || !active(task)) return;
    const watchedId=task.id;
    const timer = setInterval(() => { void api<Task>(`tasks/${watchedId}`).then(next => { if(currentId.current!==watchedId)return;setTask(next); if (!active(next)) { source.current?.close(); setStreamLost(false); void refresh(); } }).catch(() => setStreamLost(true)); }, 2000);
    return () => clearInterval(timer);
  }, [task?.id, task?.status, refresh]);
  useEffect(() => { if (modal && dialog.current && !dialog.current.open) dialog.current.showModal(); if (!modal && dialog.current?.open) dialog.current.close(); }, [modal]);
  useEffect(() => { if (!notice) return; const timer = setTimeout(() => setNotice(""), 3000); return () => clearTimeout(timer); }, [notice]);
  function newTask() {
    if (busy) { setNotice("Сначала дождитесь ответа или остановите текущую задачу."); return; }
    source.current?.close(); currentId.current = null; setTask(null); setPrompt(""); setError(""); setMode("live"); setSelected(providers.filter(p => p.configured).map(p => p.id)); requestKey.current = null;
    localStorage.removeItem("portal:last-task"); setSidebar(false); textarea.current?.focus();
  }
  async function submit() {
    if (busy || !prompt.trim() || !selected.length) return;
    setSending(true); setError(""); requestKey.current ||= crypto.randomUUID();
    try { const created = await api<Task>("tasks", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ prompt, mode, providers: selected, request_key: requestKey.current }) }); requestKey.current = null; follow(created); await refresh(); }
    catch (e) { setError((e as Error).message); } finally { setSending(false); }
  }
  async function stop() { if (!task) return; try { await api(`tasks/${task.id}/cancel`, { method: "POST", body: "{}" }); setTask({ ...task, cancel_requested: true }); } catch (e) { setError((e as Error).message); } }
  async function openHistory(item: HistoryItem) { try { follow(await api<Task>(`tasks/${item.id}`)); setSidebar(false); setError(""); } catch (e) { setError((e as Error).message); } }
  async function copy(text: string) { try { await navigator.clipboard.writeText(text); setNotice("Скопировано в буфер обмена"); } catch { setNotice("Не удалось скопировать. Выделите текст вручную."); } }
  function download() {
    if (!task) return;
    const text = `# Задача\n\n${task.prompt}\n\nРежим: ${task.mode === "demo" ? "демонстрация, шаблонные тексты" : "подписка ChatGPT через Codex"}\n\n` + task.answers.map(a => `## ${providers.find(p => p.id === a.provider)?.name}\n\nМодель: ${a.actual_model || a.model}\nСтатус: ${STATUS[a.status]}${a.source_url ? "\nДиалог: " + a.source_url : ""}\n\n${a.content}\n${a.error || ""}`).join("\n\n---\n\n");
    const url = URL.createObjectURL(new Blob([text], { type: "text/markdown;charset=utf-8" })); const anchor = document.createElement("a"); anchor.href = url; anchor.download = `portal-${task.id.slice(0, 8)}.md`; anchor.click(); URL.revokeObjectURL(url);
  }
  const expanded = task?.answers.find(a => modal === "answer:" + a.provider), expandedProvider = providers.find(p => p.id === expanded?.provider);
  const filteredHistory = history.filter(h => h.prompt.toLowerCase().includes(search.toLowerCase()));
  if(needsLogin) return <main style={{maxWidth:520,margin:'10vh auto'}}><h1>Multi-Agent Portal</h1><p>Вход в демонстрационный портал · v2.0.0</p><form onSubmit={async e=>{e.preventDefault();setLoginBusy(true);setError('');try{const result=await api<{token:string}>('login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:loginPassword})});sessionStorage.setItem('portal:session',result.token);setLoginPassword('');setNeedsLogin(false);setAuthEpoch(n=>n+1);}catch(e){setError((e as Error).message);}finally{setLoginBusy(false);}}}><label htmlFor="portal-password">Пароль портала</label><input id="portal-password" type="password" autoComplete="current-password" value={loginPassword} onChange={e=>setLoginPassword(e.target.value)} required style={{display:'block',width:'100%',padding:14,margin:'15px 0',background:'#171820',border:'1px solid #444',borderRadius:8}}/><button className="send-button" disabled={loginBusy}>{loginBusy?'Входим…':'Войти'}</button><p role="alert">{error}</p></form></main>;
  return <div className="app-shell">
    <span style={{position:'fixed',bottom:5,right:12,fontSize:10,color:'#9294a6',zIndex:10}}>v2.0.0 · {REMOTE?'Ноутбук':'Локально'}</span>
    {sidebar && <button className="sidebar-overlay" aria-label="Закрыть историю" onClick={() => setSidebar(false)} />}
    <aside className={`sidebar ${sidebar ? "visible" : ""}`}>
      <a className="brand" href={REMOTE?'./':'/'} aria-label="Multi-Agent Portal"><span className="brand-icon"><Layers3 size={21} /></span><span>multi<span className="brand-light">agent</span><span className="brand-tag">WORKSPACE</span></span></a>
      <button className="new-task" onClick={newTask}><Plus size={17} /> Новая задача <span>+</span></button>
      <div className="sidebar-section-label"><span>РАБОЧЕЕ ПРОСТРАНСТВО</span></div>
      <button className="nav-item active" onClick={() => setSidebar(false)}><Layers3 size={17} /> Ответы ИИ <span className="nav-count">5</span></button>
      <button className="nav-item" onClick={() => setModal("settings")}><Settings2 size={17} /> Подключения <span className="nav-count">{ready}/5</span></button>
      <div className="sidebar-section-label history-label"><span>ИСТОРИЯ ЗАДАЧ</span><span>{history.length}</span></div>
      <label className="history-search"><Search size={14} /><input placeholder="Найти задачу…" value={search} onChange={e => setSearch(e.target.value)} aria-label="Поиск в истории" /></label>
      <div className="history-list">{filteredHistory.length ? filteredHistory.map(item => <button className={`history-item ${task?.id === item.id ? "selected" : ""}`} key={item.id} onClick={() => void openHistory(item)}><MessageSquare size={14} /><span><strong>{item.prompt}</strong><small>{date(item.created_at)} <span>· {item.mode === "demo" ? "Демо" : STATUS[item.status]}</span></small></span></button>) : <div className="history-empty"><History size={22} /><p>{search ? "Задачи не найдены" : "Здесь будет ваша история"}</p><span>{search ? "Попробуйте другой запрос" : "Ответы сохраняются автоматически"}</span></div>}</div>
      {hasMore && <button className="history-more" disabled={loadingMore} onClick={() => void loadMore()}>{loadingMore ? "Загружаем…" : "Показать ещё"}</button>}
      <div className="sidebar-bottom"><div className="local-badge"><ShieldCheck size={15} /><span>Локальное пространство</span><span className="status-dot" /></div><div className="user"><span className="avatar">Вы</span><div><strong>Ваш портал</strong><small>Docker · подписки</small></div><button className="icon-button" aria-label="Настройки подключений" onClick={() => setModal("settings")}><Settings2 size={16} /></button></div></div>
    </aside>
    <div className="workspace"><header className="topbar"><div className="breadcrumbs"><button className="mobile-history icon-button" aria-label="Открыть историю" onClick={() => setSidebar(true)}><History size={19} /></button><span>Рабочее пространство</span><span className="crumb-divider">/</span><strong>Ответы ИИ</strong></div><div className="topbar-right"><span className={`online ${online ? "connected" : ""}`}><span className="status-dot" />{online ? "Сервер подключён" : "Подключение…"}</span><button className="icon-button" aria-label="Подключения" onClick={() => setModal("settings")}><Settings2 size={17} /></button></div></header>
      <main><div className="intro"><div><div className="eyebrow"><span className="eyebrow-line" /> MULTI-AGENT DISPATCHER</div><h1>Одна задача. <span>Все ваши ИИ.</span></h1><p>ChatGPT, DeepSeek и Z.ai — через ваши подписки и открытые веб-сеансы.</p></div><div className="intro-emblem"><Layers3 size={36} /><span>×5</span></div></div>
        <section className="composer" aria-label="Новая задача"><div className="composer-heading"><span><Zap size={16} /> Опишите задачу</span><span className="keyboard-hint">Ctrl + Enter <span>для отправки</span></span></div>
          <textarea ref={textarea} value={prompt} maxLength={24000} onChange={e => { setPrompt(e.target.value); requestKey.current = null; }} disabled={busy} onKeyDown={e => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); void submit(); } }} placeholder="Что вы хотите решить? Например: составь план масштабирования веб-приложения до 100 000 пользователей…" aria-label="Опишите задачу" />
          <div className="examples"><span>Попробуйте</span>{EXAMPLES.map(example => <button key={example} disabled={busy} onClick={() => { setPrompt(example); requestKey.current = null; textarea.current?.focus(); }}>{example}<ArrowUpRight size={12} /></button>)}</div><div className="composer-divider" />
          <div className="composer-footer"><div className="provider-select"><span>Отправить:</span>{providers.map(p => <button key={p.id} className={`provider-chip ${selected.includes(p.id) ? "selected" : ""}`} style={{ "--provider": META[p.id].color } as CSSProperties} disabled={busy || (mode === "live" && !p.configured)} onClick={() => { setSelected(s => s.includes(p.id) ? s.filter(v => v !== p.id) : [...s, p.id]); requestKey.current = null; }} aria-pressed={selected.includes(p.id)} title={p.configured ? "Подписка подключена" : "Подключение готовится"}><span className="chip-dot" />{p.name}{selected.includes(p.id) && <Check size={11} />}</button>)}</div><div className="submit-actions"><button className="clear-button" disabled={busy || !prompt} onClick={() => { setPrompt(""); requestKey.current = null; }} aria-label="Очистить задачу"><Trash2 size={14} /></button>{busy ? <button className="stop-button" disabled={sending || !!task?.cancel_requested} onClick={() => void stop()}><Square size={13} />{task?.cancel_requested ? "Останавливаем…" : "Остановить"}</button> : <button className="send-button" disabled={!prompt.trim() || !selected.length || !online} onClick={() => void submit()}><Send size={15} /> {mode === "live" ? selected.length === 1 ? `Отправить в ${providers.find(p => p.id === selected[0])?.name}` : `Отправить выбранным (${selected.length})` : `Показать демо (${selected.length})`}</button>}</div></div>
        </section>
        <div className="mode-strip"><div><span className={`mode-indicator ${mode}`} /><strong>{mode === "demo" ? "Демонстрационный режим" : "Подписки и веб-сеансы"}</strong><span>{mode === "demo" ? "Шаблонные тексты для проверки интерфейса" : ready ? `${ready} из 5 моделей подключено` : "Ожидаем обработчики"}</span></div><button className="mode-switch" disabled={busy} onClick={() => { setMode(mode === "demo" ? "live" : "demo"); setSelected(mode === "demo" ? providers.filter(p => p.configured).map(p => p.id) : DEFAULTS.map(p => p.id)); requestKey.current = null; }}>{mode === "demo" ? "Вернуться к ChatGPT" : "Включить демо"}<ArrowUpRight size={13} /></button></div>
        {error && <div className="error-banner" role="alert"><Activity size={16} /><span>{error}</span><button className="icon-button" aria-label="Закрыть сообщение" onClick={() => setError("")}><X size={15} /></button></div>}
        {streamLost && active(task) && <div className="connection-banner" role="status"><LoaderCircle size={15} className="spinning" /> Восстанавливаем соединение. Задача продолжает выполняться на сервере.</div>}
        <div className="results-heading"><div><h2>Ответы моделей</h2><span>{task ? `${doneCount}/${task.answers.length} завершено` : "Независимые ответы"}</span>{busy && <LoaderCircle size={14} className="spinning" />}</div><div className="results-tools">{task && <><button className="icon-button" onClick={download} aria-label="Скачать ответы"><ArrowDownToLine size={16} /></button></>}<span className="parallel-badge"><span className="status-dot" /> {busy ? "Задача выполняется" : `${ready}/5 подключено`}</span></div></div>
        <div className="answers-grid">{providers.map(p => {
          const answer = task?.answers.find(a => a.provider === p.id), chosen = selected.includes(p.id);
          return <article className={`answer-card ${answer?.status || "empty"} ${!answer && !chosen ? "unselected" : ""}`} style={{ "--provider": META[p.id].color } as CSSProperties} key={p.id}>
            <div className="card-header"><div className="provider-identity"><span className="provider-avatar">{META[p.id].letter}</span><div><h3>{p.name}</h3><span>{META[p.id].subtitle}</span></div></div><span className={`answer-status ${answer?.status || "idle"}`}>{answer?.status === "running" ? <LoaderCircle size={10} className="spinning" /> : <span />}{answer ? STATUS[answer.status] : "Ожидание"}</span></div>
            <div className="model-line"><span>{answer?.actual_model || answer?.model || p.model}</span>{task?.mode === "demo" && answer ? <span className="demo-label">ДЕМО</span> : <span className={`api-dot ${p.configured ? "ready" : ""}`} title={p.configured ? "Подписка подключена" : "Подключение готовится"} />}</div>
            <div className="answer-content">{answer?.content ? <Markdown text={answer.content} /> : answer?.status === "running" ? <div className="answer-loading"><span className="thinking-orbit"><Layers3 size={20} /></span><strong>{task?.mode === "demo" ? "Показываем пример…" : "Модель готовит ответ…"}</strong><p>{task?.mode === "demo" ? "Проверяем параллельное отображение" : p.id === "openai" ? "Codex выполняет задачу и ищет источники" : "Ожидаем ответ в веб-вкладке; Codex должен быть открыт"}</p></div> : answer?.error ? <div className="answer-empty error-empty"><Activity size={23} /><strong>{STATUS[answer.status]}</strong><p>{answer.error}</p></div> : <div className="answer-empty"><MessageSquare size={25} /><strong>{answer ? "В очереди" : p.configured ? chosen ? "Готов к вашей задаче" : "Выберите модель выше" : "Подключим следующим этапом"}</strong><p>{answer ? "Ожидаем свободный обработчик" : p.configured ? "Ответ появится здесь после отправки задачи" : "Пока доступен переход в веб-версию"}</p><span className="empty-line" />{p.id !== "openai" && <a className="service-link" href={p.url} target="_blank" rel="noopener noreferrer">Открыть сервис <ArrowUpRight size={12}/></a>}</div>}{answer?.content && answer.error && <p className="inline-error">{answer.error}</p>}</div>
            <div className="card-metrics"><span><Clock3 size={12} />{answer ? seconds(answer) : "—"}</span><span>{answer ? task?.mode === "demo" ? "Пример" : p.id === "openai" ? "Подписка" : "Веб-сеанс" : p.id === "openai" ? "Codex" : p.configured ? "Вкладка" : "Следующий этап"}</span></div>
            <div className="card-footer"><span>{answer ? task?.mode === "demo" ? "Демонстрационный текст" : p.id === "openai" ? "Через Codex" : "Через веб-вкладку" : p.id === "openai" ? "Поиск в интернете" : "Веб-версия"}</span><div>{answer?.source_url && <a className="icon-button" href={answer.source_url} target="_blank" rel="noopener noreferrer" aria-label={`Открыть диалог ${p.name}`}><ArrowUpRight size={13}/></a>}<button className="icon-button" disabled={!answer?.content} aria-label={`Копировать ответ ${p.name}`} onClick={() => void copy(answer?.content || "")}><Copy size={13} /></button><button className="icon-button" disabled={!answer?.content} aria-label={`Развернуть ответ ${p.name}`} onClick={() => setModal("answer:" + p.id)}><Maximize2 size={13} /></button></div></div>
          </article>;
        })}</div>
        <div className="workspace-note"><ShieldCheck size={16} /><p><strong>Ваша подписка. Ваша история.</strong> ChatGPT работает через Codex. DeepSeek и Z.ai обрабатывают задачи параллельно в Docker. История сохраняется на ноутбуке.</p><span>V2.0</span></div>
        <footer className="main-footer"><span>Ваше пространство для лучших решений</span><span>Сравнение и Deep Research — следующий этап <ArrowUpRight size={12} /></span></footer>
      </main>
    </div>
    <dialog ref={dialog} className={`modal ${expanded ? "answer-modal" : ""}`} onCancel={() => setModal(null)} onClick={e => { if (e.target === dialog.current) setModal(null); }}><div className="modal-content">
      <div className="modal-heading"><div><span className="eyebrow">MULTI-AGENT PORTAL</span><h2>{modal === "settings" ? "Подписки и подключения" : expandedProvider?.name}</h2></div><button className="icon-button" aria-label="Закрыть окно" onClick={() => setModal(null)}><X size={21} /></button></div>
      {modal === "settings" && <><p className="modal-description">ChatGPT работает через Codex, в котором выполнен вход под вашей подпиской. Для каждой задачи запускается отдельный сеанс; история этой беседы в него не передаётся.</p><div className="settings-providers">{providers.map(p => <div key={p.id}><span className="provider-avatar" style={{"--provider":META[p.id].color} as CSSProperties}>{META[p.id].letter}</span><span><strong>{p.name}</strong><small>{p.model}</small></span><span className={p.configured ? "configured-label" : "missing-label"}>{p.configured ? <Check size={13}/> : <Terminal size={13}/>}{p.configured ? "Подключено" : p.connection === "planned" || !p.connection ? "Следующий этап" : "Не подключено"}</span></div>)}</div><div className="settings-instructions"><h3>Локальный обработчик</h3><p>Запускается автоматически командой start.ps1. Если он выключен, выполните:</p><div className="command"><code>.\start-bridge.ps1</code><button className="icon-button" aria-label="Скопировать команду" onClick={() => void copy(".\\start-bridge.ps1")}><Copy size={15}/></button></div><p>Если Codex просит войти, выполните <code>codex login</code> и выберите вход через ChatGPT.</p></div><p className="settings-note">DeepSeek и Z.ai работают в независимых браузерах Docker. Этот чат для обработки не нужен. При истечении сеанса потребуется повторный вход. При ошибке первоначального открытия DeepSeek выполняется одно обновление страницы до отправки. Claude и Kimi подключим следующим этапом.</p></>}
      {expanded && <><div className="expanded-meta"><span>{expanded.actual_model || expanded.model}</span><span>{task?.mode === "demo" ? "Демонстрационный текст" : STATUS[expanded.status]}</span><button className="secondary-button" onClick={() => void copy(expanded.content)}><Copy size={14} /> Копировать</button></div><Markdown text={expanded.content} />{expanded.error && <p className="inline-error">{expanded.error}</p>}</>}
    </div></dialog>
    {notice && <div className="toast" role="status"><Check size={16} />{notice}</div>}
  </div>;
}
