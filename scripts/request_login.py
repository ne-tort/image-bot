import asyncio, sys
sys.path.insert(0, '/app')
from pathlib import Path
from core.providers.xai_oauth import XaiOAuthClient

async def main():
    client = XaiOAuthClient(Path('/data/auth/xai_session.json'))
    try:
        code = await client.request_device_code()
        print('VERIFICATION_URL=' + code.verification_uri_complete)
        print('VERIFICATION_URL_PLAIN=' + code.verification_uri)
        print('USER_CODE=' + code.user_code)
        print('EXPIRES_IN=' + str(code.expires_in))
        # Сохраняем device_code для фазы 2
        import json
        Path('/data/auth/pending_device.json').parent.mkdir(parents=True, exist_ok=True)
        Path('/data/auth/pending_device.json').write_text(json.dumps({
            'device_code': code.device_code,
            'interval': code.interval,
            'expires_in': code.expires_in,
            'requested_at': __import__('time').time(),
        }))
    except Exception as e:
        print('ERROR: %r' % e)
        raise
    finally:
        await client.aclose()

asyncio.run(main())