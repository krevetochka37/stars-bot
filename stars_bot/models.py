from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Optional, Sequence


def row_to_dict(row: Mapping[str, Any] | Sequence[Any], columns: tuple[str, ...]) -> dict[str, Any]:
    """Преобразует строку БД в словарь с именованными колонками"""
    if isinstance(row, Mapping):
        return dict(row)
    return {col: row[idx] if idx < len(row) else None for idx, col in enumerate(columns)}


PAYMENT_COLUMNS = (
    "id",
    "user_id",
    "amount",
    "status",
    "payment_provider",
    "bot_owner_id",
    "bot_id",
    "created_at",
)

@dataclass
class PaymentRecord:
    id: int
    user_id: int
    amount: int
    status: str
    payment_provider: str
    bot_owner_id: Optional[int] = None
    bot_id: Optional[str] = None
    created_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any] | Sequence[Any]) -> "PaymentRecord":
        data = row_to_dict(row, PAYMENT_COLUMNS)
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            amount=data["amount"],
            status=data["status"],
            payment_provider=data["payment_provider"],
            bot_owner_id=data.get("bot_owner_id"),
            bot_id=data.get("bot_id"),
            created_at=data.get("created_at"),
        )


STARS_BOT_TOKEN_COLUMNS = (
    "id",
    "token",
    "bot_username",
    "is_active",
    "created_at",
    "updated_at",
)


@dataclass
class StarsBotToken:
    id: int
    token: str
    bot_username: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any] | Sequence[Any]) -> "StarsBotToken":
        """Создает StarsBotToken из строки БД"""
        data = row_to_dict(row, STARS_BOT_TOKEN_COLUMNS)
        return cls(
            id=data["id"],
            token=data["token"],
            bot_username=data.get("bot_username"),
            is_active=bool(data.get("is_active", True)),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


# Константы
STARS_TO_USD_RATE = 0.01  # 1 звезда = $0.01 USD
MESSAGE_DELETE_DELAY = 60  # секунд

