from io import BytesIO
from re import sub

import fast_colorthief
from aiocache import cached
from aiohttp import ClientSession


@cached(ttl=86400)
async def get_color(query):
    try:
        if any(
            s in query
            for s in {"cdn.discordapp.com/icons/", "cdn.discordapp.com/avatars/"}
        ):
            query = sub(
                r"\?size=(32|64|128|256|512|1024|2048|4096)$", "?size=16", query
            )
        async with ClientSession() as session:
            async with session.get(query, timeout=5) as response:
                content = await response.read()

        color = fast_colorthief.get_dominant_color(BytesIO(content), quality=100)
        color = int(f"0x{color[0]:02x}{color[1]:02x}{color[2]:02x}", 16)
        return color
    except:
        return 0x505050
