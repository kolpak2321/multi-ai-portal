"""Short-lived portal sessions, separate from the internal worker credential."""
import base64
import hashlib
import hmac
import json
import os
import time
from fastapi import HTTPException

def issue_session():
    payload=base64.urlsafe_b64encode(json.dumps({'exp':int(time.time())+8*3600}).encode()).decode().rstrip('=')
    signature=hmac.new(os.environ['APP_ACCESS_TOKEN'].encode(),payload.encode(),hashlib.sha256).hexdigest()
    return payload+'.'+signature

def valid_session(value):
    try:
        payload,signature=value.split('.')
        expected=hmac.new(os.environ['APP_ACCESS_TOKEN'].encode(),payload.encode(),hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature,expected) and json.loads(base64.urlsafe_b64decode(payload+'='*(-len(payload)%4)))['exp']>time.time()
    except (ValueError,KeyError,TypeError):return False

def check_password(value):
    expected=os.getenv('PORTAL_LOGIN_PASSWORD','')
    if not expected or not hmac.compare_digest(hashlib.sha256(value.encode()).digest(),hashlib.sha256(expected.encode()).digest()):
        raise HTTPException(401,'Неверный пароль портала')
