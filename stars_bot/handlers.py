"""
Обработчики для Stars Payment Bot
"""
import asyncio
import logging
from typing import Any, Awaitable, Callable

from aiogram import Bot, BaseMiddleware, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, PreCheckoutQuery, CallbackQuery, TelegramObject

from stars_bot.database.operations import db_get_stars_bot_token_id_by_token
from stars_bot.notifications import notify_user_payment_success
from stars_bot.ui.translations import tr

from . import services, transport
from .keyboards import (
    build_payment_inline_keyboard,
    build_payment_menu_keyboard,
    build_topup_keyboard,
    get_stars_for_credits,
)
from .models import MESSAGE_DELETE_DELAY

logger = logging.getLogger(__name__)

dp = Dispatcher()


class TokenIdMiddleware(BaseMiddleware):
    """Middleware для сохранения token_id в event data"""
    
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        bot: Bot = data.get("bot")
        if bot and bot.token:
            token_id = await db_get_stars_bot_token_id_by_token(bot.token)
            if token_id:
                data["token_id"] = token_id
                logger.debug(f"Token ID {token_id} сохранен в event data")
        
        return await handler(event, data)


dp.message.middleware(TokenIdMiddleware())
dp.callback_query.middleware(TokenIdMiddleware())
dp.pre_checkout_query.middleware(TokenIdMiddleware())


def _extract_payment_id_from_payload(payload: str) -> int | None:
    """Извлекает payment_id из payload. Возвращает None если payload невалидный."""
    if not payload or not payload.startswith("payment_"):
        return None
    try:
        return int(payload.split("_")[1])
    except (ValueError, IndexError):
        return None


@dp.pre_checkout_query()
async def pre_checkout_handler(pre_checkout_query: PreCheckoutQuery) -> None:
    """Обработчик предпродажной проверки для Telegram Stars"""
    user_id = pre_checkout_query.from_user.id
    payload = pre_checkout_query.invoice_payload

    lang = await services.get_user_lang(user_id)

    # Извлекаем payment_id из payload
    payment_id = _extract_payment_id_from_payload(payload)
    if not payment_id:
        logger.warning(f"Невалидный payload: {payload}")
        await pre_checkout_query.answer(ok=False, error_message=tr(lang, "stars_bot_invalid_payload"))
        return

    try:
        # Проверяем, что платеж существует и еще не завершен
        payment = await services.get_payment_by_id(payment_id)
        if not payment:
            logger.warning(f"Платеж {payment_id} не найден в БД")
            await pre_checkout_query.answer(ok=False, error_message=tr(lang, "stars_bot_payment_not_found"))
            return

        if payment.status == "completed":
            logger.warning(f"Платеж {payment_id} уже завершен")
            await pre_checkout_query.answer(ok=False, error_message=tr(lang, "stars_bot_payment_already_processed"))
            return

        # Подтверждаем платеж
        await pre_checkout_query.answer(ok=True)

    except Exception as e:
        logger.error(f"Ошибка при обработке pre_checkout_query: {e}", exc_info=True)
        await pre_checkout_query.answer(ok=False, error_message=tr(lang, "stars_bot_payment_error_generic"))


@dp.message(F.successful_payment)
async def on_successful_payment(msg: Message) -> None:
    """Обработчик успешной оплаты через Telegram Stars"""
    if not msg.successful_payment:
        return

    payment = msg.successful_payment
    payload = payment.invoice_payload

    # Извлекаем payment_id из payload
    payment_id = _extract_payment_id_from_payload(payload)
    if not payment_id:
        logger.warning(f"Невалидный payload: {payload}")
        return

    try:
        # Получаем данные платежа из БД
        payment_data = await services.get_payment_by_id(payment_id)
        if not payment_data:
            logger.error(f"Payment {payment_id} not found in database")
            return

        # Проверяем, что это платеж через звезды
        if payment_data.payment_provider != "stars":
            logger.warning(
                f"Payment {payment_id} is not a stars payment, provider={payment_data.payment_provider}"
            )
            return

        # Проверяем, что пользователь из сообщения совпадает с пользователем из payment_data
        message_user_id = msg.from_user.id if msg.from_user else None
        payment_user_id = payment_data.user_id
        
        if message_user_id != payment_user_id:
            logger.error(
                f"Несоответствие пользователей для платежа {payment_id}: "
                f"пользователь из сообщения={message_user_id}, пользователь из платежа={payment_user_id}"
            )
            return

        user_id = payment_data.user_id
        amount = payment_data.amount
        stars_amount = payment.total_amount

        # Обрабатываем успешный платеж (передаем уже загруженные данные платежа)
        success, updated_payment_data = await services.process_payment_success(payment_id, user_id, amount, stars_amount, payment_data=payment_data)
        if not success:
            logger.error(f"Не удалось обработать платеж {payment_id}")
            return

        # Отправляем сообщение об успешном пополнении пользователю
        # Используем payment_data, если updated_payment_data не вернулся (для обратной совместимости)
        payment_data_for_message = updated_payment_data if updated_payment_data else payment_data
        if payment_data_for_message:
            logger.debug(f"Отправка сообщения об успешном пополнении пользователю {user_id} для платежа {payment_id}")
            await send_payment_success_message_to_user(user_id, amount, stars_amount, payment_id, payment_data_for_message)
        else:
            logger.warning(f"Не удалось получить payment_data для отправки сообщения пользователю {user_id} для платежа {payment_id}")

        bot_id = payment_data.bot_id
        if bot_id:
            try:
                payment_dict = {
                    "id": payment_data.id,
                    "user_id": payment_data.user_id,
                    "amount": payment_data.amount,
                    "status": "completed",
                    "payment_provider": payment_data.payment_provider,
                    "bot_owner_id": payment_data.bot_owner_id,
                    "bot_id": payment_data.bot_id,
                }
                asyncio.create_task(notify_user_payment_success(user_id, amount, bot_id, payment_dict))
            except Exception as e:
                logger.error(f"Ошибка создания задачи отправки уведомления в исходный бот: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"Ошибка обработки successful_payment: {e}", exc_info=True)


async def send_payment_success_message_to_user(user_id: int, amount: int, stars_amount: int, payment_id: int, payment_data) -> None:
    """Отправляет сообщение об успешном пополнении баланса пользователю через тот же бот, что использовался для оплаты"""
    try:
        # Получаем токен и token_id для отправки сообщения
        token_data = await services.get_payment_token_id_for_success_message(payment_id, payment_data)
        if not token_data:
            logger.warning(f"Не удалось получить токен для отправки сообщения пользователю {user_id}")
            return
        
        token, token_id = token_data
        
        lang = await services.get_user_lang(user_id)
        success_message = tr(lang, "stars_bot_payment_success", amount=amount, stars_amount=stars_amount)
        payment_menu_keyboard = build_payment_menu_keyboard(lang)
        
        bot = Bot(token=token)
        try:
            await bot.send_message(
                chat_id=user_id,
                text=success_message,
                parse_mode="HTML",
                reply_markup=payment_menu_keyboard,
            )
            logger.info(f"✅ Отправлено сообщение об успешном пополнении пользователю {user_id} через token_id={token_id}")
        finally:
            await bot.session.close()
            
    except Exception as e:
        logger.error(f"❌ Ошибка отправки сообщения об успешном пополнении пользователю {user_id}: {e}", exc_info=True)


async def send_payment_menu(msg: Message) -> None:
    """Отправляет меню оплаты с вариантами пополнения"""
    user_id = msg.from_user.id
    lang = await services.get_user_lang(user_id)
    
    welcome_text = tr(lang, "stars_bot_welcome")
    welcome_inline_text = tr(lang, "stars_bot_welcome_inline")
    keyboard = build_topup_keyboard(lang)
    payment_menu_keyboard = build_payment_menu_keyboard(lang)
    
    await msg.answer(
        welcome_text,
        parse_mode="HTML",
        reply_markup=payment_menu_keyboard,
    )
    
    await msg.answer(
        welcome_inline_text,
        parse_mode="HTML",
        reply_markup=keyboard.as_markup(),
    )


@dp.message(Command("start"))
async def cmd_start(msg: Message) -> None:
    """Обработчик команды /start"""
    await send_payment_menu(msg)


@dp.callback_query(F.data.startswith("topup_"))
async def handle_topup_callback(callback: CallbackQuery, bot: Bot) -> None:
    """Обработчик callback query для кнопок выбора суммы пополнения"""
    await callback.answer()
    
    if not callback.data or not callback.message:
        logger.warning(f"Callback query без data или message: data={callback.data}, message={callback.message}")
        return
    
    try:
        credits_str = callback.data.replace("topup_", "")
        credits = int(credits_str)
        
        user_id = callback.from_user.id
        lang = await services.get_user_lang(user_id)
        
        token_id = None
        if bot and bot.token:
            token_id = await db_get_stars_bot_token_id_by_token(bot.token)
        
        payment_id = await services.create_payment(user_id, credits)

        stars_amount = get_stars_for_credits(credits)

        invoice_data = await transport.create_invoice_link(payment_id, credits, lang, stars_amount=stars_amount, token_id=token_id)
        
        if not invoice_data:
            error_msg = tr(lang, "stars_bot_payment_error", payment_id=payment_id)
            if callback.message:
                await callback.message.answer(error_msg, parse_mode="HTML")
            return
        
        invoice_link, bot_username = invoice_data
        message_text = tr(lang, "stars_bot_payment_created", amount=credits, stars_amount=stars_amount)
        keyboard = build_payment_inline_keyboard(invoice_link, lang)
        
        if not callback.message:
            return
        
        sent_message = await callback.message.answer(
            message_text,
            reply_markup=keyboard.as_markup(),
            parse_mode="HTML",
        )
        
        async def delete_after_delay():
            await asyncio.sleep(MESSAGE_DELETE_DELAY)
            try:
                if callback.message:
                    await bot.delete_message(
                        chat_id=sent_message.chat.id,
                        message_id=sent_message.message_id
                    )
                    logger.debug("Сообщение об оплате удалено через %s секунд (payment_id=%s)", MESSAGE_DELETE_DELAY, payment_id)
            except Exception as e:
                logger.warning(f"⚠️ Не удалось удалить сообщение об оплате: {e}")
        
        asyncio.create_task(delete_after_delay())
        
    except ValueError:
        logger.error(f"Невалидный callback_data: {callback.data}")
    except Exception as e:
        logger.error(f"Ошибка обработки callback topup: {e}", exc_info=True)
        if callback.message:
            lang = await services.get_user_lang(callback.from_user.id)
            await callback.message.answer(
                tr(lang, "stars_bot_payment_error_generic"),
                parse_mode="HTML"
            )


@dp.message(F.text)
async def handle_payment_menu_text(msg: Message) -> None:
    """Обработчик текстовых сообщений с кнопкой 'Меню оплаты'"""
    if msg.text and msg.text.startswith("/"):
        return
    
    lang = await services.get_user_lang(msg.from_user.id)
    payment_menu_text = tr(lang, "btn_payment_menu")
    
    if msg.text == payment_menu_text:
        await send_payment_menu(msg)


@dp.callback_query()
async def handle_callback_query(callback: CallbackQuery) -> None:
    """Обработчик callback query для inline кнопок"""
    await callback.answer()
