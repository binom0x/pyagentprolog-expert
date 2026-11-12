"""interactive.py — интерактивный опрос через ask_interactive().

Пользователь вводит «Хочу назначить директора в Тюмень» — Expert
задаёт вопросы, пользователь отвечает, факты добавляются в граф.
"""
from __future__ import annotations

import queue
import threading

from pyagentprolog_expert import Expert, KnowledgeGraph, Session


class ConsoleSession(Session):
    """Session с консольным вводом/выводом в отдельном потоке."""

    def __init__(self) -> None:
        super().__init__()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while True:
            try:
                msgs = self.poll()
            except Exception:
                return
            for kind, payload in msgs:
                if kind == "question":
                    print(f"\n[Expert] {payload}")
                    try:
                        answer = input("> ").strip()
                    except (EOFError, KeyboardInterrupt):
                        self.send("")
                        return
                    self.send(answer)
            if self._stopped():
                return

    def _stopped(self) -> bool:
        try:
            return self.input_queue.get_nowait() is None
        except queue.Empty:
            return False


def main() -> None:
    g = KnowledgeGraph.from_prolog(open("graph.pl", encoding="utf-8").read())
    sess = ConsoleSession()
    e = Expert(graph=g, rules_file="rules.pl", session=sess)

    print("=" * 70)
    print("Интерактивный режим: «Хочу назначить директора в Тюмень»")
    print("=" * 70)

    try:
        result = e.ask_interactive(
            "Хочу назначить директора в технопарк Тюмень",
            top_k=3,
            max_turns=5,
        )
        print()
        print("=" * 70)
        print("Результат:")
        print(result)
        print()
        print("Граф после диалога:", e.graph.summary())
        print()
        print("why():")
        print(e.why())
    finally:
        sess.stop()


if __name__ == "__main__":
    main()