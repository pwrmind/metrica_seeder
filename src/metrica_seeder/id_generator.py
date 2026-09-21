"""Генерация ClientID по алгоритму, аналогичному Яндекс.Метрике."""
import random
import time


def generate_client_id() -> str:
    """Unix-время в секундах + случайное число. Пример: 1712345678123456789."""
    now_sec = int(time.time())
    rand_part = random.randint(1_000_000, 999_999_999)
    return f"{now_sec}{rand_part}"