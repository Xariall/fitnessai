import logging

from supabase import AsyncClient, acreate_client

from config import settings

logger = logging.getLogger(__name__)

_client: AsyncClient | None = None


async def get_client() -> AsyncClient:
    """Возвращает singleton AsyncClient для Supabase.

    Использует SUPABASE_SERVICE_KEY (service_role) чтобы обойти RLS на бэкенде.
    Никогда не передавай этот ключ на клиент.
    """
    global _client
    if _client is None:
        _client = await acreate_client(settings.supabase_url, settings.supabase_service_key)
        logger.info("Supabase client initialized")
    return _client
