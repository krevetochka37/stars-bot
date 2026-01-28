"""
Клавиатуры для Stars Payment Bot
"""
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from stars_bot.ui.translations import tr
from stars_bot.utils import get_stars_amount_for_credits

# Варианты пополнения: (stars, usd, credits)
TOPUP_OPTIONS = [
    (200, 3, 150),
    (400, 6, 300),
    (650, 10, 500),
    (1300, 20, 1000),
    (2600, 40, 2000),
    (3850, 60, 3000),
    (5150, 80, 4000),
]

CREDITS_TO_STARS = {credits: stars for stars, usd, credits in TOPUP_OPTIONS}


def get_stars_for_credits(credits: int) -> int:
    """Возвращает количество звезд для указанного количества кредитов"""
    return CREDITS_TO_STARS.get(credits, get_stars_amount_for_credits(credits))


def build_topup_keyboard(lang: str) -> InlineKeyboardBuilder:
    """Создает inline клавиатуру с вариантами пополнения"""
    builder = InlineKeyboardBuilder()
    for stars, usd, credits in TOPUP_OPTIONS:
        button_text = tr(lang, "topup_button", stars=stars, usd=usd, credits=credits)
        builder.button(text=button_text, callback_data=f"topup_{credits}")
    builder.adjust(1)
    return builder


def build_payment_menu_keyboard(lang: str) -> ReplyKeyboardMarkup:
    """Создает клавиатуру с кнопкой 'Меню оплаты'"""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=tr(lang, "btn_payment_menu"))]],
        resize_keyboard=True,
        one_time_keyboard=False,
    )


def build_payment_inline_keyboard(invoice_link: str, lang: str) -> InlineKeyboardBuilder:
    """Создает inline клавиатуру с кнопкой оплаты"""
    builder = InlineKeyboardBuilder()
    builder.button(text=tr(lang, "btn_pay"), url=invoice_link)
    builder.adjust(1)
    return builder

