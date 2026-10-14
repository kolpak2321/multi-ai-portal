"""Claude is allowed to use one explicitly bound existing conversation only."""
import re
from urllib.parse import urlsplit

def conversation_url(url):
    value=urlsplit(url)
    if value.scheme!='https' or value.hostname!='claude.ai' or value.username or value.password or value.port not in (None,443):
        raise ValueError('Для Claude нужен адрес существующего чата claude.ai')
    if not re.fullmatch(r'/chat/[0-9a-fA-F-]{36}',value.path):
        raise ValueError('Для Claude запрещены главная страница и создание новых чатов')
    return 'https://claude.ai'+value.path

def require_bound_chat(current,bound):
    if conversation_url(current)!=conversation_url(bound):
        raise RuntimeError('Claude переключён в другой чат. Отправка остановлена.')
