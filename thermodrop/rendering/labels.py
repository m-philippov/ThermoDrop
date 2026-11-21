"""Подписи осей графиков."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AxisLabels:
    """Подписи осей; ``None`` — подпись по умолчанию."""

    x: Optional[str] = None
    y: Optional[str] = None
    z: Optional[str] = None
    colorbar: Optional[str] = None


def pick(custom: Optional[str], default: str) -> str:
    return default if custom is None else custom
