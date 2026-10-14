import pytest
from fixed_chat import conversation_url,require_bound_chat
CHAT='https://claude.ai/chat/12345678-1234-1234-1234-123456789abc'

def test_fixed_chat_allows_only_existing_conversation():
    assert conversation_url(CHAT+'?model=example')==CHAT
    require_bound_chat(CHAT,CHAT)
    for invalid in ('https://claude.ai/new','https://claude.ai/','https://evil.example/chat/12345678-1234-1234-1234-123456789abc'):
        with pytest.raises(ValueError):conversation_url(invalid)

def test_switching_chat_stops_send():
    with pytest.raises(RuntimeError):require_bound_chat(CHAT.replace('789abc','789def'),CHAT)

@pytest.mark.parametrize("provider,url",[
 ('deepseek','https://chat.deepseek.com/a/chat/s/12345678-1234-1234-1234-123456789abc'),
 ('zai','https://chat.z.ai/c/12345678-1234-1234-1234-123456789abc'),
 ('kimi','https://www.kimi.com/chat/example123')])
def test_all_services_reject_home_other_chat_and_wrong_host(provider,url):
    assert conversation_url(url,provider)==url
    require_bound_chat(url,url,provider)
    with pytest.raises(ValueError):conversation_url(url.split('/')[0]+'//'+url.split('/')[2]+'/',provider)
    with pytest.raises(RuntimeError):require_bound_chat(url.replace('example123','other123').replace('789abc','789def'),url,provider)
    with pytest.raises(ValueError):conversation_url(CHAT,provider)
