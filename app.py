#!/usr/bin/env python3
"""
FastAPI приложение для обработки webhook'ов Stars Payment Bot
Поддерживает несколько токенов из таблицы stars_bot_tokens
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

from contextlib import asynccontextmanager
from typing import Dict

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Update
from fastapi import FastAPI, HTTPException, Header, Depends, Query
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
dotenv_path = PROJECT_ROOT / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path)
else:
    load_dotenv()

sys.path.insert(0, str(PROJECT_ROOT))

from stars_bot.database.operations import close_pool, get_pool
from stars_bot.config.settings import Settings
from stars_bot.models import StarsBotToken
from stars_bot.utils import get_stars_amount_for_credits

from stars_bot import handlers, services

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

WEBHOOK_URL = os.getenv("STARS_WEBHOOK_URL")

bots_registry: Dict[int, tuple[Bot, Dispatcher]] = {}


async def setup_single_bot(token_record: StarsBotToken, proxy_url: str | None = None) -> tuple[Bot, Dispatcher]:
    """Настраивает одного бота. Возвращает (bot, dp)"""
    token_id = token_record.id
    token = token_record.token
    token_preview = token[:8] if token else "unknown"

    try:
        bot = Bot(
            token=token,
            default=DefaultBotProperties(parse_mode="HTML"),
        )

        # Используем глобальный dispatcher из handlers
        dp = handlers.dp

        if not WEBHOOK_URL:
            raise ValueError("STARS_WEBHOOK_URL не настроен для webhook режима")
        webhook_path = f"{WEBHOOK_URL}/stars/{token_id}"
        await bot.set_webhook(
            url=webhook_path,
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query", "pre_checkout_query"]
        )
        logger.info(f"✅ Webhook установлен для токена {token_preview}... (ID: {token_id}): {webhook_path}")

        # Проверяем, что webhook действительно установлен
        webhook_info = await bot.get_webhook_info()
        if webhook_info.url == webhook_path:
            logger.info(f"✅ Webhook подтверждён для токена {token_preview}... (ID: {token_id}): {webhook_info.url}")
        else:
            logger.warning(f"⚠️ Webhook URL не совпадает для токена {token_preview}... (ID: {token_id})! Ожидалось: {webhook_path}, получено: {webhook_info.url}")

        bots_registry[token_id] = (bot, dp)
        return bot, dp

    except Exception as e:
        logger.error(f"❌ Ошибка настройки бота с токеном {token_preview}... (ID: {token_id}): {e}", exc_info=True)
        raise


async def setup_all_bots() -> None:
    settings = Settings.load()
    proxy_url = settings.get_proxy_url()
    
    active_tokens = await services.get_active_stars_bot_tokens()
    
    if not active_tokens:
        error_msg = (
            "Не найдено активных токенов в таблице stars_bot_tokens. "
            "Добавьте хотя бы один токен в таблицу stars_bot_tokens с is_active=TRUE."
        )
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    logger.info(f"✅ Найдено {len(active_tokens)} активных токенов в БД")
    
    tasks = [
        asyncio.create_task(setup_single_bot(token_record, proxy_url))
        for token_record in active_tokens
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    success_count = 0
    for idx, result in enumerate(results):
        if isinstance(result, Exception):
            token_preview = active_tokens[idx].token[:8] if idx < len(active_tokens) else "unknown"
            logger.error(f"❌ Бот с токеном {token_preview}... не настроен: {result}")
        else:
            success_count += 1
    
    logger.info(f"🚀 Настроено {success_count} из {len(active_tokens)} ботов")


async def cleanup_all_bots() -> None:
    for token_id, (bot, _) in bots_registry.items():
        try:
            await bot.delete_webhook()
            await bot.session.close()
            logger.info(f"✅ Webhook удалён для бота ID: {token_id}")
        except Exception as e:
            logger.error(f"❌ Ошибка удаления webhook для бота ID {token_id}: {e}")
    
    bots_registry.clear()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()
    logger.info("Database connection pool initialized")
    
    try:
        await setup_all_bots()
        logger.info("Все боты настроены и готовы к работе")
    except Exception as e:
        logger.error(f"Критическая ошибка при настройке ботов: {e}")
        raise
    
    yield
    
    # Очистка при остановке
    await cleanup_all_bots()
    await close_pool()
    logger.info("Database connection pool closed")


app = FastAPI(lifespan=lifespan)


# Кэш для настроек
_settings_cache: Settings | None = None


def get_settings() -> Settings:
    """Получает настройки (с кэшированием)"""
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = Settings.load()
    return _settings_cache


async def verify_admin_token(
    x_admin_token: str | None = Header(None, alias="X-Admin-Token"),
    admin_token: str | None = Query(None, alias="admin_token"),
    settings: Settings = Depends(get_settings),
) -> None:
    """
    Dependency для проверки admin token.
    Поддерживает два способа передачи токена:
    1. Через заголовок X-Admin-Token
    2. Через query параметр admin_token
    """
    if not settings.admin_token:
        logger.warning("ADMIN_TOKEN не настроен в переменных окружения")
        raise HTTPException(
            status_code=500,
            detail="Admin token не настроен. Установите переменную окружения ADMIN_TOKEN."
        )
    
    provided_token = x_admin_token or admin_token
    
    if not provided_token:
        logger.warning("Попытка доступа к защищенному эндпоинту без токена")
        raise HTTPException(
            status_code=401,
            detail="Требуется заголовок X-Admin-Token или query параметр admin_token"
        )
    
    if provided_token != settings.admin_token:
        logger.warning(f"Попытка доступа с невалидным токеном: {provided_token[:8]}...")
        raise HTTPException(
            status_code=403,
            detail="Невалидный admin token"
        )


@app.post("/stars/{token_id}")
async def handle_webhook(token_id: int, update: Update):
    """Обработка webhook'ов от Telegram для Stars Payment Bot по token_id"""
    if token_id not in bots_registry:
        logger.warning(f"Бот с token_id={token_id} не найден в реестре")
        return JSONResponse({"ok": True})
    
    bot, dp = bots_registry[token_id]
    
    try:
        await dp.feed_update(bot=bot, update=update)
        return JSONResponse({"ok": True}, status_code=200)
    except Exception as e:
        logger.error(f"Ошибка обработки update для бота token_id={token_id}: {e}", exc_info=True)
        # Всегда возвращаем 200 OK для Telegram, чтобы не было повторных запросов
        return JSONResponse({"ok": False, "error": "Internal server error"}, status_code=200)


@app.get("/")
async def root():
    return {
        "status": "ok",
        "bot": "stars",
        "active_bots": len(bots_registry),
        "webhook_endpoint": "/stars/{token_id}",
        "health_endpoint": "/health"
    }


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "bot": "stars",
        "active_bots": len(bots_registry)
    }


@app.post("/setup-webhooks")
async def setup_webhooks():
    try:
        await cleanup_all_bots()
        await setup_all_bots()
        return {
            "success": True,
            "message": f"Webhook'и установлены для {len(bots_registry)} ботов"
        }
    except Exception as e:
        logger.error(f"Ошибка переустановки webhook'ов: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/process-payment/{external_payment_id}")
async def process_payment_manually_endpoint(
    external_payment_id: str,
    payment_provider: str = "stars",
    _: None = Depends(verify_admin_token),
):
    """
    Ручная обработка платежа по external_payment_id.
    Начисляет кредиты пользователю, даже если статус уже completed.
    
    Args:
        external_payment_id: External payment ID из таблицы payments
        payment_provider: Провайдер платежа (по умолчанию "stars")
    """
    try:
        success, payment_data = await services.process_payment_manually(external_payment_id, payment_provider)
        if success:
            if payment_data:
                user_id = payment_data.user_id
                amount = payment_data.amount
                stars_amount = get_stars_amount_for_credits(amount)
                payment_id = payment_data.id
                
                try:
                    await handlers.send_payment_success_message_to_user(user_id, amount, stars_amount, payment_id, payment_data)
                except Exception as e:
                    logger.warning(f"Не удалось отправить сообщение об успешном пополнении пользователю {user_id}: {e}")
            
            return {
                "success": True,
                "message": f"Платеж с external_payment_id={external_payment_id} обработан успешно, кредиты начислены"
            }
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Не удалось обработать платеж с external_payment_id={external_payment_id}, provider={payment_provider}"
            )
    except Exception as e:
        logger.error(f"Ошибка обработки платежа {external_payment_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
