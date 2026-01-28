"""
Транспортный слой для создания invoice
"""
import logging
from typing import Optional

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import LabeledPrice

from stars_bot.config.settings import Settings
from stars_bot.database.operations import (
    db_get_stars_bot_token_by_id,
    db_update_payment_stars_bot_token_id,
)
from stars_bot.ui.translations import tr
from stars_bot.utils import get_stars_amount_for_credits

from . import services

logger = logging.getLogger(__name__)

# Кэш для прокси URL
_cached_proxy_url: str | None = None


async def create_invoice_link(
    payment_id: int, amount: int, lang: str, stars_amount: int | None = None, token_id: int | None = None
) -> Optional[tuple[str, Optional[str]]]:
    """Создает invoice link для платежа"""
    try:
        if token_id:
            token_data = await db_get_stars_bot_token_by_id(token_id)
            if not token_data:
                logger.warning(f"Токен с token_id={token_id} не найден, используем случайный")
                token_data = await services.get_random_active_stars_bot_token()
                if not token_data:
                    logger.error("❌ Не найдено активных токенов для создания invoice")
                    return None
                random_token, token_id, bot_username = token_data
            else:
                random_token, bot_username = token_data
                logger.debug("Используем токен для invoice: token=%s..., token_id=%s, username=%s", random_token[:8], token_id, bot_username)
        else:
            token_data = await services.get_random_active_stars_bot_token()
            if not token_data:
                logger.error("❌ Не найдено активных токенов для создания invoice")
                return None
            random_token, token_id, bot_username = token_data
            logger.debug("Получен случайный токен для invoice: token=%s..., token_id=%s, username=%s", random_token[:8], token_id, bot_username)
        
        await db_update_payment_stars_bot_token_id(payment_id, token_id)

        # Конвертируем кредиты в звезды Telegram по точному курсу, если не передано
        if stars_amount is None:
            stars_amount = get_stars_amount_for_credits(amount)

        # Получаем прокси из настроек
        global _cached_proxy_url
        if _cached_proxy_url is None:
            settings = Settings.load()
            _cached_proxy_url = settings.get_proxy_url()
        proxy_url = _cached_proxy_url
        
        session = AiohttpSession(proxy=proxy_url, limit=10) if proxy_url else AiohttpSession(limit=10)
        temp_bot = Bot(token=random_token, session=session)
        try:
            invoice_link = await temp_bot.create_invoice_link(
                title=tr(lang, "payment_invoice_title", amount=amount),
                description=tr(lang, "payment_invoice_description", amount=amount),
                payload=f"payment_{payment_id}",
                currency="XTR",  # XTR - код валюты для Telegram Stars
                prices=[LabeledPrice(label=tr(lang, "payment_invoice_label", amount=amount), amount=stars_amount)],
            )

            logger.debug("Invoice link создан для платежа %s через бот %s...", payment_id, random_token[:8])
            return (invoice_link, bot_username)
        finally:
            # Закрываем сессию временного бота
            await temp_bot.session.close()
    except Exception as e:
        logger.error(f"❌ Ошибка создания invoice link для платежа {payment_id}: {e}", exc_info=True)
        return None



