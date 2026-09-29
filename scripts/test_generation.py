import asyncio, sys, os
sys.path.insert(0, '/app')
from pathlib import Path
from core.providers.adapter import SpecDrivenProvider
from core.types import GenerationRequest, MediaKind
from core.xai_login import XaiLoginService

async def main():
    login = XaiLoginService(Path('/data/auth/xai_session.json'))
    prov = SpecDrivenProvider.from_name('grok_build', xai_session=login)
    req = GenerationRequest(prompt='a small red cube on white background', kind=MediaKind.IMAGE, user_id=1)
    try:
        media = await prov.generate(req, timeout=120.0)
        print('GEN_OK kind=' + media.kind.value + ' model=' + media.model)
        print('DATA_TYPE=' + ('bytes' if isinstance(media.data, bytes) else 'url'))
        if isinstance(media.data, bytes):
            print('SIZE=' + str(len(media.data)))
        else:
            print('URL=' + str(media.data)[:200])
    except Exception as e:
        print('GEN_ERR: %r' % e)
    finally:
        await prov.aclose()

asyncio.run(main())