"""session.py — интерфейс интерактивной сессии (ask_user).

Используется `Expert.ask_interactive()` для доопроса пользователя.
Реализация — на стороне UI (Gradio, CLI, тесты).
"""
from __future__ import annotations

import queue
import threading
from typing import Optional


class NullSession:
    """Сессия по умолчанию: ask_user не поддерживается."""

    def ask_user(self, question: str) -> Optional[str]:
        return None


class Session:
    """Очереди ввода/вывода для интерактивного опроса.

    UI-поток читает output_queue (вопросы) и пишет в input_queue
    (ответы пользователя). Expert.ask_interactive() читает вопросы
    из output_queue и ждёт ответа в input_queue.
    """

    def __init__(self) -> None:
        self.input_queue: queue.Queue[Optional[str]] = queue.Queue()
        self.output_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self._lock = threading.Lock()
        self.running = False

    def ask_user(self, question: str) -> Optional[str]:
        self.output_queue.put(("question", question))
        return self.input_queue.get()

    def send(self, text: str) -> None:
        self.input_queue.put(text)

    def poll(self) -> list[tuple[str, object]]:
        msgs: list[tuple[str, object]] = []
        while True:
            try:
                msgs.append(self.output_queue.get_nowait())
            except queue.Empty:
                break
        return msgs

    def stop(self) -> None:
        with self._lock:
            self.running = False
        self.input_queue.put(None)


__all__ = ["NullSession", "Session"]
