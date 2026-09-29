import asyncio, sys, json, time
sys.path.insert(0, '/app')
from pathlib import Path
from core.providers.xai_oauth import XaiOAuthClient, DeviceCode

async def main():
    pending = json.loads(Path('/data/auth/pending_device.json').read_text())
    client = XaiOAuthClient(Path('/data/auth/xai_session.json'))
    code = DeviceCode(
        verification_uri='https://accounts.x.ai/oauth2/device',
        user_code='used',
        device_code=pending['device_code'],
        interval=pending.get('interval', 5.0),
        expires_in=pending.get('expires_in', 1800),
    )
    try:
        session = await client.poll_for_session(code, timeout=pending['expires_in'] - (time.time() - pending['requested_at']))
        print('LOGIN_OK')
        print('EMAIL=' + session.email)
        print('USER_ID=' + session.user_id)
        print('EXPIRES_IN=' + str(int(session.expires_in)))
        print('HAS_REFRESH=' + str(bool(session.refresh_token)))
    except Exception as e:
        print('LOGIN_STATUS: %r' % e)
    finally:
        await client.aclose()

asyncio.run(main())