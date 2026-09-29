import asyncio, json, sys
sys.path.insert(0, '/app')
from pathlib import Path
import httpx
from core.providers.xai_oauth import XaiOAuthClient

async def main():
    session = XaiOAuthClient(Path('/data/auth/xai_session.json')).load_session()
    assert session and session.access_token, 'no session'
    print('SESSION_EMAIL=' + session.email)
    async with httpx.AsyncClient(timeout=20.0) as http:
        r = await http.get('https://api.x.ai/v1/models', headers={'Authorization': 'Bearer ' + session.access_token})
        print('MODELS_STATUS=' + str(r.status_code))
        if r.status_code == 200:
            ids = [m.get('id') for m in r.json().get('data', [])][:10]
            print('MODELS=' + ', '.join(str(i) for i in ids))
        else:
            print('BODY=' + r.text[:300])

asyncio.run(main())