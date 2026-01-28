"""Utility functions for Stars Payment Bot"""
import math


def get_stars_amount_for_credits(credits: int) -> int:
    """
    Рассчитывает количество звезд Telegram для указанного количества кредитов
    """
    stars_map = {
        150: 400,
        250: 650,
        500: 1300,
        1000: 2600,
        1500: 3850,
        2000: 5150
    }
    
    if credits in stars_map:
        return stars_map[credits]
    
    # Для промежуточных значений используем интерполяцию
    # Находим ближайшие пресеты
    sorted_presets = sorted(stars_map.keys())
    
    # Если запрошено меньше минимального пресета
    if credits < sorted_presets[0]:
        return int(credits * 400 / 150)
    
    # Если запрошено больше максимального пресета
    if credits > sorted_presets[-1]:
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

