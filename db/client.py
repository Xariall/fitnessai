import logging
from functools import lru_cache

from supabase import AsyncClient, acreate_client

from config import settings

logger = logging.getLogger(__name__)

_client: AsyncClient | None = None


async def get_client() -> AsyncClient:
    global _client
    if _client is None:
        _client = await acreate_client(settings.supabase_url, settings.supabase_key)
        logger.info("Supabase client initialized")
    return _client
