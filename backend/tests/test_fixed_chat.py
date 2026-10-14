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
