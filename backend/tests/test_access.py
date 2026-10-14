import time
from access import issue_session,valid_session,check_password
from fastapi import HTTPException
import pytest

def test_signed_session_and_tampering(monkeypatch):
    monkeypatch.setenv('APP_ACCESS_TOKEN','test-internal')
    token=issue_session()
    assert valid_session(token)
    assert not valid_session(token+'0')
    monkeypatch.setattr(time,'time',lambda:99999999999)
    assert not valid_session(token)

def test_portal_password_separate(monkeypatch):
    monkeypatch.setenv('PORTAL_LOGIN_PASSWORD','test-login')
    check_password('test-login')
    with pytest.raises(HTTPException):check_password('test-internal')
