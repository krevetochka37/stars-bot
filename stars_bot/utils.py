"""Utility functions for Stars Payment Bot"""
import math


def get_stars_amount_for_credits(credits: int) -> int:
    """
    Рассчитывает количество звезд Telegram для указанного количества кредитов
    Использует точные значения из пресетов:
    - 150 credits = 400 stars ($6)
    - 250 credits = 650 stars ($10)
    - 500 credits = 1300 stars ($20)
    - 1000 credits = 2600 stars ($40)
    - 1500 credits = 3850 stars ($60)
    - 2000 credits = 5150 stars ($80)
    
    Args:
        credits: Количество кредитов
        
    Returns:
        Количество звезд Telegram
    """
    # Точные значения из пресетов
    stars_map = {
        150: 400,
        250: 650,
        500: 1300,
        1000: 2600,
        1500: 3850,
        2000: 5150
    }
    
    # Если это точное значение из пресета - возвращаем его
    if credits in stars_map:
        return stars_map[credits]
    
    # Для промежуточных значений используем интерполяцию
    # Находим ближайшие пресеты
    sorted_presets = sorted(stars_map.keys())
    
    # Если запрошено меньше минимального пресета
    if credits < sorted_presets[0]:
        # Используем курс минимального пресета: 150 credits = 400 stars
        # 1 credit = 400/150 = 2.67 stars
        return int(credits * 400 / 150)
    
    # Если запрошено больше максимального пресета
    if credits > sorted_presets[-1]:
        # Используем курс максимального пресета: 2000 credits = 5150 stars
        # 1 credit = 5150/2000 = 2.575 stars
        return int(credits * 5150 / 2000)
    
    # Находим два ближайших пресета для интерполяции
    lower_preset = None
    upper_preset = None
    
    for i, preset in enumerate(sorted_presets):
        if preset <= credits:
            lower_preset = preset
        if preset >= credits and upper_preset is None:
            upper_preset = preset
            break
    
    # Если нашли оба пресета - интерполируем
    if lower_preset and upper_preset:
        lower_stars = stars_map[lower_preset]
        upper_stars = stars_map[upper_preset]
        
        # Линейная интерполяция
        ratio = (credits - lower_preset) / (upper_preset - lower_preset)
        stars = lower_stars + (upper_stars - lower_stars) * ratio
        return int(math.ceil(stars))
    
    # Fallback (не должно произойти)
    return int(credits * 2.6)

