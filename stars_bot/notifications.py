"""
Модуль для отправки уведомлений в основное приложение, ЗАГЛУШКА!!
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


async def notify_user_payment_success(
    user_id: int,
    amount: int,
    bot_id: str | None = None,
    payment_data: dict | None = None,
) -> bool:
    # Заглушка - функция не выполняет никаких действий
    logger.debug(f"notify_user_payment_success called for user {user_id}, amount {amount}, bot_id {bot_id}")
    return True

