"""Security helpers."""
from __future__ import annotations

import base64
import hashlib
from typing import Tuple

from ..config import settings


def hash_phone_number(phone: str) -> Tuple[str, str]:
    """Return (sha256, last4)."""

    last4 = phone[-4:]
    salted = f"{settings.phone_salt}:{phone}"
    digest = hashlib.sha256(salted.encode("utf-8")).hexdigest()
    return digest, last4


def encode_deeplink_payload(chat_id: int) -> str:
    """Encode chat id for deep-link."""

    return base64.urlsafe_b64encode(str(chat_id).encode("utf-8")).decode("ascii")


def decode_deeplink_payload(payload: str) -> int:
    """Decode chat id from deep-link payload."""

    return int(base64.urlsafe_b64decode(payload.encode("ascii")).decode("utf-8"))
