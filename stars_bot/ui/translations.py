"""Translations for Stars Payment Bot"""
from typing import Dict

_TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "ru": {
        "btn_pay": "💳 Оплатить звездами",
        "btn_payment_menu": "💎 Меню оплаты",
        "payment_invoice_title": "Пополнение баланса на {amount} кредитов",
        "payment_invoice_description": "Оплата {amount} кредитов через Telegram Stars",
        "payment_invoice_label": "{amount} кредитов",
        "stars_bot_welcome": "⭐ <b>Добро пожаловать в бот для оплаты звездами!</b>",
        "stars_bot_welcome_inline": "💎 Выберите удобную сумму пополнения ниже:\n\n✨ Все платежи безопасны и обрабатываются через Telegram Stars",
        "topup_button": "⭐ {stars} звезд • ${usd} • {credits} токенов",
        "stars_bot_payment_created": "💳 <b>Платеж готов к оплате!</b>\n\n📊 <b>Детали:</b>\n💰 Вы получите: <b>{amount} кредитов</b>\n⭐ К оплате: <b>{stars_amount} звезд</b>\n\n👇 Нажмите кнопку ниже для оплаты:",
        "stars_bot_payment_error": "Ошибка создания платежной ссылки для платежа {payment_id}. Попробуйте позже.",
        "stars_bot_invalid_payload": "Неверный payload платежа",
        "stars_bot_payment_not_found": "Платеж не найден",
        "stars_bot_payment_already_processed": "Платеж уже обработан",
        "stars_bot_payment_error_generic": "Ошибка обработки платежа",
        "stars_bot_payment_success": "🎉 <b>Оплата успешна!</b>\n\n✅ Вам начислено: <b>{amount} кредитов</b>\n⭐ Оплачено: <b>{stars_amount} звезд</b>\n\n💚 Спасибо за использование нашего сервиса!",
    },
    "en": {
        "btn_pay": "💳 Pay with Stars",
        "btn_payment_menu": "💎 Payment Menu",
        "payment_invoice_title": "Top up balance for {amount} credits",
        "payment_invoice_description": "Payment for {amount} credits via Telegram Stars",
        "payment_invoice_label": "{amount} credits",
        "stars_bot_welcome": "⭐ <b>Welcome to the Stars Payment Bot!</b>",
        "stars_bot_welcome_inline": "💎 Select your preferred top-up amount below:\n\n✨ All payments are secure and processed via Telegram Stars",
        "topup_button": "⭐ {stars} stars • ${usd} • {credits} tokens",
        "stars_bot_payment_created": "💳 <b>Payment ready!</b>\n\n📊 <b>Details:</b>\n💰 You will receive: <b>{amount} credits</b>\n⭐ To pay: <b>{stars_amount} stars</b>\n\n👇 Click the button below to pay:",
        "stars_bot_payment_error": "Error creating payment link for payment {payment_id}. Please try again later.",
        "stars_bot_invalid_payload": "Invalid payment payload",
        "stars_bot_payment_not_found": "Payment not found",
        "stars_bot_payment_already_processed": "Payment already processed",
        "stars_bot_payment_error_generic": "Error processing payment",
        "stars_bot_payment_success": "🎉 <b>Payment successful!</b>\n\n✅ You received: <b>{amount} credits</b>\n⭐ Paid: <b>{stars_amount} stars</b>\n\n💚 Thank you for using our service!",
    },
    "zh": {
        "btn_pay": "💳 使用星币支付",
        "btn_payment_menu": "💎 支付菜单",
        "payment_invoice_title": "充值 {amount} 积分",
        "payment_invoice_description": "通过 Telegram 星币 支付 {amount} 积分",
        "payment_invoice_label": "{amount} 积分",
        "stars_bot_welcome": "⭐ <b>欢迎使用星币支付机器人！</b>",
        "stars_bot_welcome_inline": "💎 请在下方选择您喜欢的充值金额：\n\n✨ 所有支付均安全，通过 Telegram 星币处理",
        "topup_button": "⭐ {stars} 星币 • ${usd} • {credits} 代币",
        "stars_bot_payment_created": "💳 <b>付款已准备就绪！</b>\n\n📊 <b>详情：</b>\n💰 您将获得：<b>{amount} 积分</b>\n⭐ 需支付：<b>{stars_amount} 星币</b>\n\n👇 点击下方按钮进行支付：",
        "stars_bot_payment_error": "为付款 {payment_id} 创建支付链接时出错。请稍后再试。",
        "stars_bot_invalid_payload": "无效的付款 payload",
        "stars_bot_payment_not_found": "未找到付款",
        "stars_bot_payment_already_processed": "付款已处理",
        "stars_bot_payment_error_generic": "处理付款时出错",
        "stars_bot_payment_success": "🎉 <b>支付成功！</b>\n\n✅ 您获得：<b>{amount} 积分</b>\n⭐ 已支付：<b>{stars_amount} 星币</b>\n\n💚 感谢使用我们的服务！",
    },
}


def tr(lang: str, key: str, **kwargs) -> str:
    # Если язык не поддерживается, используем русский по умолчанию
    if lang not in _TRANSLATIONS:
        lang = "ru"
    
    # Получаем перевод
    translation = _TRANSLATIONS.get(lang, {}).get(key, _TRANSLATIONS.get("ru", {}).get(key, key))
    
    # Форматируем строку с параметрами, если они есть
    if kwargs:
        try:
            return translation.format(**kwargs)
        except KeyError:
            # Если не хватает параметров, возвращаем как есть
            return translation
    
    return translation

