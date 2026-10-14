"""Subscription connections; credentials remain in the user's Codex installation."""
PROVIDERS = [
    {"id":"openai","name":"ChatGPT","company":"OpenAI","model":"Codex · подписка ChatGPT","url":"https://chatgpt.com/"},
    {"id":"claude","name":"Claude","company":"Anthropic","model":"Claude · выбранная модель","url":"https://claude.ai/"},
    {"id":"zai","name":"Z.ai","company":"Z.ai","model":"Z.ai · веб-сеанс","url":"https://chat.z.ai/"},
    {"id":"deepseek","name":"DeepSeek","company":"DeepSeek","model":"DeepSeek · веб-сеанс","url":"https://chat.deepseek.com/"},
    {"id":"kimi","name":"Kimi","company":"Moonshot AI","model":"Kimi · постоянный чат","url":"https://www.kimi.com/"},
]

async def connections(pool):
    bridges={r['provider']:r for r in await pool.fetch("SELECT provider,connected,note,seen_at>now()-interval '20 seconds' AS fresh FROM subscription_bridges")}
    result=[]
    for p in PROVIDERS:
        bridge=bridges.get(p['id']);ready=bool(bridge and bridge['fresh'] and bridge['connected'])
        supported=p['id'] in ('openai','deepseek','zai','claude','kimi')
        result.append({**p,'configured':ready,'connection':'codex' if p['id']=='openai' else 'browser' if supported else 'planned',
            'note':bridge['note'] if bridge and bridge['fresh'] else 'Обработчик не запущен' if supported else 'Автоматическое подключение — следующий этап'})
    return result

async def create_bridge_tables(pool):
    from pathlib import Path
    await pool.execute(Path(__file__).with_name('subscription-schema.sql').read_text())
