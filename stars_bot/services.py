"""
Сервисный слой для работы с платежами через Telegram Stars
Вся бизнес-логика и работа с БД
"""
import logging
from typing import List, Optional

from stars_bot.database.operations import (
    db_add_credits,
    db_add_referral_bonus,
    db_create_payment,
    db_get_lang,
    db_get_payment_row_by_id,
    db_get_payment_row_by_external_id,
    db_get_stars_bot_token_by_id,
    db_list_active_stars_bot_tokens_rows,
    db_pick_random_active_stars_bot_token,
    db_update_payment_status_by_id,
    db_update_payment_stars_bot_token_id,
    db_update_payment_usd_breakdown,
    db_update_referral_status,
)

from .models import PaymentRecord, StarsBotToken, STARS_TO_USD_RATE
from .utils import get_stars_amount_for_credits

logger = logging.getLogger(__name__)


async def _get_bot_owner_id_from_payment(payment_id: int) -> Optional[int]:
    """Получает bot_owner_id из платежа"""
    row = await db_get_payment_row_by_id(payment_id)
    if not row:
        return None
    return PaymentRecord.from_row(row).bot_owner_id


async def get_payment_by_id(payment_id: int) -> Optional[PaymentRecord]:
    """Получает платеж по ID"""
    row = await db_get_payment_row_by_id(payment_id)
    if not row:
        return None
    return PaymentRecord.from_row(row)


async def create_payment(user_id: int, amount: int, bot_owner_id: Optional[int] = None, bot_id: Optional[str] = None) -> int:
    """Создает новый платеж. Возвращает payment_id"""
    payment_id = await db_create_payment(user_id, amount, payment_provider="stars", bot_owner_id=bot_owner_id, bot_id=bot_id)
    logger.info(f"Создан платеж {payment_id} для пользователя {user_id}, сумма: {amount} кредитов")
    return payment_id


async def get_user_lang(user_id: int) -> str:
    """Получает язык пользователя, возвращает 'ru' по умолчанию"""
    lang = await db_get_lang(user_id)
    return lang or "ru"


async def get_payment_token_id_for_success_message(payment_id: int, payment_data: PaymentRecord | None = None) -> Optional[tuple[str, int]]:
    """Получает токен и token_id для отправки сообщения об успешном пополнении. Возвращает (token, token_id) или None"""
    try:
        if payment_data:
            bot_id_str = payment_data.bot_id
        else:
            payment_data = await get_payment_by_id(payment_id)
            if not payment_data:
                logger.error(f"Платеж {payment_id} не найден")
                return None
            bot_id_str = payment_data.bot_id
        
        token_id = None
        if bot_id_str and str(bot_id_str).startswith("stars_token_"):
            try:
                token_id = int(str(bot_id_str).replace("stars_token_", ""))
            except ValueError:
                logger.warning(f"Не удалось извлечь token_id из bot_id={bot_id_str}")
        
        if token_id:
            token_data = await db_get_stars_bot_token_by_id(token_id)
            if not token_data:
                logger.warning(f"Не удалось получить токен для token_id={token_id}, используем случайный")
                token_data = await get_random_active_stars_bot_token()
                if token_data:
                    token, token_id, _ = token_data
                    return (token, token_id)
                else:
                    logger.warning(f"Не удалось получить токен для отправки сообщения пользователю: нет активных токенов")
                    return None
            else:
                token, _ = token_data
                return (token, token_id)
        else:
            logger.warning(f"Token_id не найден для платежа {payment_id} (bot_id={bot_id_str}), используем случайный токен")
            token_data = await get_random_active_stars_bot_token()
            if not token_data:
                logger.warning(f"Не удалось получить токен для отправки сообщения: нет активных токенов")
                return None
            token, token_id, _ = token_data
            return (token, token_id)
            
    except Exception as e:
        logger.error(f"❌ Ошибка получения токена для отправки сообщения об успешном пополнении: {e}", exc_info=True)
        return None


async def process_payment_success(
    payment_id: int, user_id: int, amount: int, stars_amount: int, payment_data: PaymentRecord | None = None
) -> tuple[bool, PaymentRecord | None]:
    """
    Обрабатывает успешный платеж:
    - Проверяет статус платежа (если уже completed - ничего не делает)
    - Начисляет кредиты пользователю
    - Начисляет реферальный бонус (если есть)
    - Обновляет статус платежа в БД на completed
    - Обновляет статус реферала
    - Обновляет USD значения для статистики
    """
    if not payment_data:
        payment_data = await get_payment_by_id(payment_id)
        if not payment_data:
            logger.error(f"Платеж {payment_id} не найден в БД")
            return False, None
    
    # Проверяем статус платежа ПЕРЕД обработкой
    if payment_data.status == "completed":
        logger.info(f"Платеж {payment_id} уже обработан (статус: completed), пропускаем обработку")
        return True, None

    bot_owner_id = payment_data.bot_owner_id
    
    if bot_owner_id:
        logger.debug("Получен bot_owner_id из платежа: %s", bot_owner_id)

    # Начисляем кредиты пользователю
    try:
        await db_add_credits(user_id, amount)
        logger.info(f"✅ Начислено {amount} кредитов пользователю {user_id} за платеж {payment_id}")
    except Exception as e:
        logger.error(f"❌ Ошибка начисления кредитов: {e}")
        return False

    # Обновляем статус платежа напрямую по payment_id
    status_updated = await db_update_payment_status_by_id(payment_id, "completed")

    if not status_updated:
        logger.warning(f"⚠️ Не удалось обновить статус платежа {payment_id}, но кредиты уже начислены")
        # Не возвращаем False, так как кредиты уже начислены
    else:
        logger.debug("Статус платежа %s обновлен на 'completed' в БД", payment_id)

    if bot_owner_id:
        try:
            await db_add_referral_bonus(user_id, amount, bot_owner_id=bot_owner_id)
            logger.debug(
                "Начислен реферальный бонус владельцу бота %s за платеж пользователя %s",
                bot_owner_id,
                user_id,
            )
        except Exception as e:
            logger.warning(f"⚠️ Ошибка начисления реферального бонуса: {e}")

    # Обновляем статус реферала
    try:
        await db_update_referral_status(referred_id=user_id, status="completed")
        logger.debug("Статус реферала обновлен для пользователя %s", user_id)
    except Exception as e:
        logger.warning(f"⚠️ Ошибка обновления статуса реферала: {e}")

    # Обновляем реальные USD значения в БД для статистики
    gross_amount_usd = stars_amount * STARS_TO_USD_RATE
    # Для Telegram Stars комиссия Telegram = 0%, поэтому net = gross, fee = 0
    net_amount_usd = gross_amount_usd
    fee_amount_usd = 0.0

    try:
        await db_update_payment_usd_breakdown(
            payment_id,
            net_amount_usd=net_amount_usd,
            gross_amount_usd=gross_amount_usd,
            fee_amount_usd=fee_amount_usd,
        )
        logger.debug(
            "Обновлены реальные USD значения: %s звезд = $%.2f USD",
            stars_amount,
            gross_amount_usd,
        )
    except Exception as e:
        logger.warning(f"⚠️ Ошибка обновления USD значений: {e}")

    return True, payment_data


async def get_active_stars_bot_tokens() -> List[StarsBotToken]:
    """Получает все активные токены Stars Payment Bot"""
    rows = await db_list_active_stars_bot_tokens_rows()
    return [StarsBotToken.from_row(row) for row in rows]


async def get_random_active_stars_bot_token() -> Optional[tuple[str, int, Optional[str]]]:
    """Получает случайный активный токен, token_id и username Stars Payment Bot для создания invoice"""
    return await db_pick_random_active_stars_bot_token()


async def get_payment_by_external_id(external_payment_id: str, payment_provider: str = "stars") -> Optional[PaymentRecord]:
    """Получает платеж по external_payment_id"""
    row = await db_get_payment_row_by_external_id(external_payment_id, payment_provider)
    if not row:
        return None
    return PaymentRecord.from_row(row)


async def process_payment_manually(external_payment_id: str, payment_provider: str = "stars") -> tuple[bool, PaymentRecord | None]:
    try:
        # Получаем данные платежа по external_payment_id
        payment_data = await get_payment_by_external_id(external_payment_id, payment_provider)
        if not payment_data:
            logger.error(f"Платеж с external_payment_id={external_payment_id}, provider={payment_provider} не найден в БД")
            return False, None
        
        payment_id = payment_data.id
        
        # Проверяем, что это платеж через звезды
        if payment_data.payment_provider != payment_provider:
            logger.warning(f"Платеж {payment_id} имеет другой провайдер: ожидался {payment_provider}, получен {payment_data.payment_provider}")
            return False, None
        
        if payment_data.status == "completed":
            logger.info(f"Платеж {payment_id} уже обработан (статус: completed), пропускаем обработку")
            return True, None
        
        user_id = payment_data.user_id
        amount = payment_data.amount
        
        # Получаем bot_owner_id
        bot_owner_id = payment_data.bot_owner_id
        
        # Начисляем кредиты пользователю
        try:
            await db_add_credits(user_id, amount)
            logger.info(f"✅ Начислено {amount} кредитов пользователю {user_id} за платеж {payment_id} (ручная обработка)")
        except Exception as e:
            logger.error(f"❌ Ошибка начисления кредитов: {e}")
            return False, None
        
        # Начисляем реферальный бонус (если есть)
        if bot_owner_id:
            try:
                await db_add_referral_bonus(user_id, amount, bot_owner_id=bot_owner_id)
                logger.info(f"✅ Начислен реферальный бонус владельцу бота {bot_owner_id} за платеж {payment_id}")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка начисления реферального бонуса: {e}")
        
        # Обновляем статус реферала
        try:
            await db_update_referral_status(referred_id=user_id, status="completed")
            logger.debug(f"Статус реферала обновлен для пользователя {user_id}")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка обновления статуса реферала: {e}")
        
        status_updated = await db_update_payment_status_by_id(payment_id, "completed")
        if status_updated:
            logger.info(f"✅ Статус платежа {payment_id} обновлен на 'completed'")
        else:
            logger.warning(f"⚠️ Не удалось обновить статус платежа {payment_id}")
        
        return True, payment_data
        
    except Exception as e:
        logger.error(f"❌ Ошибка ручной обработки платежа: {e}", exc_info=True)
        return False, None
