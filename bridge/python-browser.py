"""Native Chrome adapter; all task state remains in the Docker portal."""
import os,sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'.sites-runtime/python-deps'))
sys.path.insert(0,str(root/'backend'))
config=dict(l.split('=',1) for l in (root/'.env').read_text(encoding='utf-8').splitlines() if l and not l.startswith('#') and '=' in l)
os.environ['APP_ACCESS_TOKEN']=config['APP_ACCESS_TOKEN']
os.environ['PORTAL_INTERNAL_URL']='http://127.0.0.1:'+config.get('PORTAL_PORT','8086')+'/api/'
os.environ['PORTAL_USE_PROXY']='1'
os.environ['PORTAL_CDP_URL']='http://127.0.0.1:19222'
os.environ['PORTAL_PROVIDER']=sys.argv[1]
import json
os.environ['PORTAL_CHAT_URL']=json.loads((root/('.sites-runtime/'+sys.argv[1]+'-chat.json')).read_text(encoding='utf-8-sig'))['url']
from browser_worker import main
import asyncio
asyncio.run(main())
