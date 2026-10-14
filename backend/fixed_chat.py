"""Only explicitly bound existing conversations are allowed."""
import re
from urllib.parse import urlsplit

def conversation_url(url,provider='claude'):
    value=urlsplit(url)
    hosts={'claude':'claude.ai','deepseek':'chat.deepseek.com','zai':'chat.z.ai','kimi':'www.kimi.com'}
    paths={'claude':r'/chat/[0-9a-fA-F-]{36}','deepseek':r'/a/chat/s/[0-9a-fA-F-]{36}','zai':r'/c/[0-9a-fA-F-]{36}','kimi':r'/chat/[a-zA-Z0-9_-]+'}
    host=value.hostname if provider=='kimi' and value.hostname in ('www.kimi.ai','www.kimi.com') else hosts[provider]
    if value.scheme!='https' or value.hostname!=host or value.username or value.password or value.port not in (None,443):
        raise ValueError('Нужен HTTPS-адрес существующего чата выбранного сервиса')
    if not re.fullmatch(paths[provider],value.path):
        raise ValueError('Главная страница и создание новых чатов запрещены')
    return 'https://'+host+value.path

def require_bound_chat(current,bound,provider='claude'):
    if conversation_url(current,provider)!=conversation_url(bound,provider):
        raise RuntimeError('Открыт другой чат. Отправка остановлена.')
