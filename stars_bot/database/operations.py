"""Database operations for Stars Payment Bot"""
import logging
import os
from pathlib import Path
from typing import Optional

import asyncpg
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Загружаем переменные окружения из .env файла
PROJECT_ROOT = Path(__file__).resolve().parents[2]
dotenv_path = PROJECT_ROOT / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path)
else:
    load_dotenv()

_pool: Optional[asyncpg.Pool] = None
_payments_usd_columns_ensured = False


async def get_pool() -> asyncpg.Pool:
    """Получает или создает connection pool"""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "6432")),
            database=os.getenv("DB_NAME", "refbot"),
            user=os.getenv("DB_USER", "postgres"),
            password=os.getenv("DB_PASSWORD", ""),
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
    return _pool


async def close_pool() -> None:
    """Закрывает connection pool"""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def _ensure_payments_usd_columns() -> None:
    """Обеспечивает наличие USD колонок в таблице payments"""
    global _payments_usd_columns_ensured
    if _payments_usd_columns_ensured:
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("ALTER TABLE payments ADD COLUMN IF NOT EXISTS net_amount_usd REAL")
            await conn.execute("ALTER TABLE payments ADD COLUMN IF NOT EXISTS gross_amount_usd REAL")
            await conn.execute("ALTER TABLE payments ADD COLUMN IF NOT EXISTS fee_amount_usd REAL")
            await conn.execute("ALTER TABLE payments ADD COLUMN IF NOT EXISTS expected_net_amount_usd REAL")
            await conn.execute("ALTER TABLE payments ADD COLUMN IF NOT EXISTS expected_gross_amount_usd REAL")
            await conn.execute("ALTER TABLE payments ADD COLUMN IF NOT EXISTS expected_fee_amount_usd REAL")
    _payments_usd_columns_ensured = True


async def db_get_payment_row_by_id(payment_id: int):
    """Возвращает строку платежа по ID (для Telegram Stars)"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, user_id, amount, status, payment_provider, bot_owner_id, bot_id, created_at
            FROM payments
            WHERE id = $1
            """,
            payment_id,
        )
        return row


async def db_get_payment_row_by_external_id(external_payment_id: str, payment_provider: str):
    """Возвращает строку платежа по external_payment_id и payment_provider"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, user_id, amount, status, payment_provider, bot_owner_id, bot_id, created_at
            FROM payments
            WHERE external_payment_id = $1 AND payment_provider = $2
            """,
            external_payment_id,
            payment_provider,
        )
        return row


async def db_list_active_stars_bot_tokens_rows():
    """Возвращает все активные токены Stars Payment Bot"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, token, bot_username, is_active, created_at, updated_at FROM stars_bot_tokens WHERE is_active = TRUE"
        )
        return rows


async def db_pick_random_active_stars_bot_token():
    """Возвращает случайный активный токен, token_id и username Stars Payment Bot"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, token, bot_username FROM stars_bot_tokens WHERE is_active = TRUE ORDER BY RANDOM() LIMIT 1"
        )
        if not row:
            return None
        return row["token"], row["id"], row["bot_username"]


async def db_get_stars_bot_token_by_id(token_id: int) -> Optional[tuple[str, Optional[str]]]:
    """Возвращает токен и username Stars Payment Bot по token_id"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT token, bot_username FROM stars_bot_tokens WHERE id = $1 AND is_active = TRUE",
            token_id,
        )
        if not row:
            return None
        return row["token"], row["bot_username"]


async def db_get_stars_bot_token_id_by_token(token: str) -> Optional[int]:
    """Возвращает token_id по токену бота"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id FROM stars_bot_tokens WHERE token = $1 AND is_active = TRUE",
            token,
        )
        if not row:
            return None
        return row["id"]


async def db_update_payment_stars_bot_token_id(payment_id: int, token_id: int) -> None:
    """Сохраняет stars_bot_token_id в платеже (используем bot_id для хранения token_id как строку)"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE payments
            SET bot_id = $1
            WHERE id = $2
            """,
            f"stars_token_{token_id}",
            payment_id,
        )


async def db_get_payment_stars_bot_token_id(payment_id: int) -> Optional[int]:
    """Получает stars_bot_token_id из платежа"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT bot_id FROM payments WHERE id = $1",
            payment_id,
        )
        if not row or not row["bot_id"]:
            return None
        
        bot_id_str = str(row["bot_id"])
        if bot_id_str.startswith("stars_token_"):
            try:
                return int(bot_id_str.replace("stars_token_", ""))
            except ValueError:
                return None
        return None


async def db_get_lang(user_id: int) -> Optional[str]:
    """Получает язык пользователя (быстрый запрос только языка). Возвращает None если язык не установлен."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT lang FROM users WHERE user_id=$1", user_id)
        if row and row["lang"]:
            lang = str(row["lang"]).strip().lower()
            # Проверяем, что язык валидный (после приведения к нижнему регистру)
            if lang in ["ru", "en", "zh"]:
                return lang
        return None


async def db_create_payment(user_id: int, amount: int, payment_provider: str = "stars", bot_owner_id: Optional[int] = None, bot_id: Optional[str] = None) -> int:
    """Создает новый платеж в БД. Возвращает payment_id"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                """
                INSERT INTO payments (user_id, amount, status, payment_provider, bot_owner_id, bot_id, created_at)
                VALUES ($1, $2, 'pending', $3, $4, $5, NOW())
                RETURNING id
                """,
                user_id,
                amount,
                payment_provider,
                bot_owner_id,
                bot_id,
            )
            payment_id = row["id"]
            
            external_payment_id = f"stars_{payment_id}"
            await conn.execute(
                """
                UPDATE payments
                SET external_payment_id = $1
                WHERE id = $2
                """,
                external_payment_id,
                payment_id,
            )
            
            return payment_id


async def db_add_credits(user_id: int, delta: int) -> None:
    """Добавляет кредиты пользователю"""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "INSERT INTO users(user_id, balance) VALUES($1,0) ON CONFLICT(user_id) DO NOTHING",
                user_id,
            )
            await conn.execute(
                "UPDATE users SET balance = COALESCE(balance, 0) + $1 WHERE user_id=$2",
                delta,
                user_id,
            )


async def db_add_referral_bonus(user_id: int, amount: int, bot_owner_id: Optional[int] = None, ref_percent: float = 0.05) -> bool:
    """Начисляет реферальный бонус владельцу бота"""
    if not bot_owner_id:
        return False
    
    bonus = int(amount * ref_percent)
    if bonus <= 0:
        return False
    
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Создаем пользователя-владельца бота, если его нет
                await conn.execute(
                    "INSERT INTO users(user_id, balance) VALUES($1, 0) ON CONFLICT(user_id) DO NOTHING",
                    bot_owner_id,
                )
                # Начисляем бонус
                await conn.execute(
                    "UPDATE users SET balance = COALESCE(balance, 0) + $1 WHERE user_id=$2",
                    bonus,
                    bot_owner_id,
                )
        return True
    except Exception as e:
        logger.error(f"db_add_referral_bonus failed: {e}", exc_info=True)
        return False


async def db_update_referral_status(referred_id: int, status: str) -> bool:
    """Обновляет статус реферала"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE referrals
                    SET status = $1, updated_at = NOW()
                    WHERE referred_id = $2
                    """,
                    status,
                    referred_id,
                )
        return True
    except Exception as e:
        logger.error(f"db_update_referral_status failed: {e}", exc_info=True)
        return False


async def db_update_payment_status_by_id(payment_id: int, status: str) -> bool:
    """Обновляет статус платежа по payment_id"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                result = await conn.execute(
                    """
                    UPDATE payments
                    SET status = $1, updated_at = NOW()
                    WHERE id = $2
                    """,
                    status,
                    payment_id,
                )
                # Проверяем, были ли обновлены строки
                if result == "UPDATE 0":
                    logger.warning(f"Не найдено платежей для обновления: payment_id={payment_id}")
                    return False
        return True
    except Exception as e:
        logger.error(f"Ошибка обновления статуса платежа по payment_id: {e}", exc_info=True)
        return False


async def db_update_payment_status_by_external(external_payment_id: str, payment_provider: str, status: str) -> bool:
    """Обновляет статус платежа по external_payment_id"""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                result = await conn.execute(
                    """
                    UPDATE payments
                    SET status = $1, updated_at = NOW()
                    WHERE external_payment_id = $2 AND payment_provider = $3
                    """,
                    status,
                    external_payment_id,
                    payment_provider,
                )
                if result == "UPDATE 0":
                    logger.warning(f"Не найдено платежей для обновления: external_id={external_payment_id}, provider={payment_provider}")
                    return False
        return True
    except Exception as e:
        logger.error(f"Ошибка обновления статуса платежа по external_id: {e}", exc_info=True)
        return False


async def db_update_payment_usd_breakdown(
    payment_id: int,
    net_amount_usd: Optional[float],
    gross_amount_usd: Optional[float],
    fee_amount_usd: Optional[float],
) -> None:
    """Обновляет USD значения платежа"""
    try:
        await _ensure_payments_usd_columns()
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    """
                    UPDATE payments
                    SET net_amount_usd = $1,
                        gross_amount_usd = $2,
                        fee_amount_usd = $3,
                        updated_at = NOW()
                    WHERE id = $4
                    """,
                    net_amount_usd,
                    gross_amount_usd,
                    fee_amount_usd,
                    payment_id,
                )
    except Exception as e:
        logger.error(f"Ошибка обновления USD-данных платежа: {e}", exc_info=True)
