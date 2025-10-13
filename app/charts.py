"""Utilities for building matplotlib charts."""
from __future__ import annotations

import io
from datetime import date
from typing import Iterable, Sequence

import matplotlib
import matplotlib.pyplot as plt

matplotlib.use("Agg")


def build_checkin_chart(dates: Sequence[date], morning: Sequence[int], evening: Sequence[int]) -> io.BytesIO:
    """Render attendance chart into in-memory buffer."""

    figure, ax = plt.subplots(figsize=(12, 6))
    ax.plot(dates, morning, label="Утро", marker="o")
    ax.plot(dates, evening, label="Вечер", marker="o")
    ax.set_xlabel("Дата")
    ax.set_ylabel("Количество отметок")
    ax.set_title("Посещаемость смен")
    ax.grid(True)
    ax.legend()

    buffer = io.BytesIO()
    figure.tight_layout()
    figure.savefig(buffer, format="png")
    buffer.seek(0)
    plt.close(figure)
    return buffer
