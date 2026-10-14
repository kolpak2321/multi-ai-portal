"""One independent process per web provider. Uses visible browser UI only."""
import asyncio
import os
import time
from uuid import uuid4
from pathlib import Path
import httpx
from playwright.async_api import async_playwright

PROVIDER=os.environ['PORTAL_PROVIDER']
HOME={'deepseek':'https://chat.deepseek.com/','zai':'https://chat.z.ai/'}[PROVIDER]
RUNNER=str(uuid4())
BASE=os.getenv('PORTAL_INTERNAL_URL','http://api:8000')
PROFILE=Path('/profiles')/PROVIDER
CDP=os.getenv('PORTAL_CDP_URL')

async def main():
    header='X-Portal-Bridge' if os.getenv('PORTAL_USE_PROXY') else 'X-Portal-Token'
    async with httpx.AsyncClient(base_url=BASE,headers={header:os.environ['APP_ACCESS_TOKEN']},timeout=15) as client:
        async def post(route,body):
            r=await client.post('bridge/'+route,json=body);r.raise_for_status();return r.json()
        async with async_playwright() as pw:
            if CDP:
                browser=await pw.chromium.connect_over_cdp(CDP)
                context=browser.contexts[0]
                from urllib.parse import urlparse
                page=next((p for p in context.pages if urlparse(p.url).hostname==urlparse(HOME).hostname),None)
                if page is None:
                    page=await context.new_page();await page.goto(HOME,wait_until='domcontentloaded')
            else:
                PROFILE.mkdir(parents=True,exist_ok=True)
                context=await pw.chromium.launch_persistent_context(str(PROFILE),headless=os.getenv('HEADLESS','true')=='true',viewport={'width':1100,'height':800})
                page=context.pages[0] if context.pages else await context.new_page()
                await page.goto(HOME,wait_until='domcontentloaded')
            while True:
                try:
                    # Login readiness requires the composer and absence of a login form.
                    composer=page.locator('textarea').last
                    text=await page.locator('body').inner_text()
                    login=any(s in text.lower() for s in ['log in to deepseek','войти в deepseek','sign in to continue','вход в deepseek'])
                    if PROVIDER=='zai' and '\nSign in\n' in '\n'+text+'\n':login=True
                    ready=await composer.is_visible() and not login
                    blocked='403 ERROR' in text or 'Request blocked' in text
                    label='Chrome на ноутбуке' if CDP else 'браузер Docker'
                    await post('heartbeat',{'provider':PROVIDER,'connected':ready and not blocked,'note':'Сайт блокирует подключение (403)' if blocked else label+' подключён' if ready else 'Нужен вход: '+label})
                    if ready:
                        job=await post('claim',{'provider':PROVIDER,'runner_id':RUNNER})
                        if job['task']:await execute(page,job['task'],post)
                except Exception as exc:
                    print(PROVIDER,type(exc).__name__,flush=True)
                    try:await post('heartbeat',{'provider':PROVIDER,'connected':False,'note':'Серверному браузеру требуется проверка входа или страницы'})
                    except Exception:pass
                await asyncio.sleep(.5)

async def execute(page,task,post):
    content='';submitted=False;last_content='';stable_since=None
    async def save(status='running',error=None):
        return await post(f'tasks/{task["id"]}/update',{'runner_id':RUNNER,'provider':PROVIDER,'content':content,'status':status,'error':error,'source_url':page.url if submitted and page.url!=HOME else None})
    try:
        state=await save()
        if state['cancel_requested']:await save('cancelled');return
        old_composer=page.locator('textarea').last
        if await old_composer.is_visible() and await old_composer.input_value():raise RuntimeError('В поле есть черновик. Он сохранён, задача не отправлялась.')
        await page.goto(HOME,wait_until='domcontentloaded')
        if PROVIDER=='deepseek':
            body=(await page.locator('body').inner_text()).lower()
            if any(s in body for s in ['something went wrong','ошибка загрузки']):await page.reload(wait_until='domcontentloaded')
        composer=page.locator('textarea').last
        if await composer.input_value():raise RuntimeError('В поле обнаружен черновик. Отправка остановлена.')
        await composer.fill(task['prompt'])
        await composer.press('Enter');submitted=True
        deadline=time.monotonic()+600
        while time.monotonic()<deadline:
            # Provider-specific answer containers; never copy user prompts or reasoning.
            selector='.ds-markdown' if PROVIDER=='deepseek' else '[id="response-content-container"]'
            nodes=page.locator(selector)
            if await nodes.count():
                candidate=await nodes.last.evaluate("""e=>Array.from(e.querySelectorAll('p,h1,h2,h3,h4,pre,li')).filter(n=>!n.closest('.thinking-chain-container')&&!n.parentElement.closest('li,pre')).map(n=>{const c=n.cloneNode(true);c.querySelectorAll('a[href]').forEach(a=>{const u=a.getAttribute('href');if(/^https?:\\/\\//.test(u))a.textContent='['+a.textContent+']('+u+')';});return c.textContent.trim();}).join('\\n\\n')""") if PROVIDER=='zai' else await nodes.last.inner_text()
                if candidate!=last_content:last_content=candidate;stable_since=time.monotonic()
                content=candidate
            state=await save()
            if state['cancel_requested']:
                stop=page.get_by_role('button',name='Stop',exact=True)
                if await stop.count():await stop.click()
                await save('cancelled');return
            stop_visible=await page.get_by_role('button',name='Stop',exact=True).is_visible()
            # Require a visible finished response control plus stable final content.
            controls=await page.locator('.regenerate-response-button').count() if PROVIDER=='zai' else await page.get_by_role('button',name='Читать вслух').count()
            if content and controls and not stop_visible and stable_since and time.monotonic()-stable_since>3:
                await save('completed');print(PROVIDER,task['id'],'completed',flush=True);return
            await asyncio.sleep(2)
        raise RuntimeError('Истекло время ожидания ответа. Повторной отправки не было.')
    except Exception as exc:
        await save('error',str(exc)[:500] if isinstance(exc,RuntimeError) else 'Ошибка браузера после отправки. Автоматического повтора не было.' if submitted else 'Не удалось открыть форму модели; проверьте вход в серверном браузере.')

if __name__=='__main__':asyncio.run(main())
