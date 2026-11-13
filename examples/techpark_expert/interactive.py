"""interactive.py — интерактивный диалог с Expert."""
from __future__ import annotations

import time
from typing import Optional

from pyagentprolog_expert import Expert, KnowledgeGraph, Session


class ConsoleSession(Session):
    def ask_user(self, question: str) -> Optional[str]:
        print(f"\n[Expert] {question}")
        try:
            return input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return None


def main() -> None:
    t_start = time.perf_counter()

    with open("graph.pl", encoding="utf-8") as f:
        g = KnowledgeGraph.from_prolog(f.read())
    print(f"[{time.perf_counter()-t_start:.2f}s] graph: "
          f"nodes={len(g.nodes)} edges={len(g.edges)} "
          f"attrs={len(g.attributes)}")

    t0 = time.perf_counter()
    e = Expert(
        graph=g, rules_file="rules.pl",
        t2p_kwargs={"use_spacy": False},
        session=ConsoleSession(),
    )
    print(f"[{time.perf_counter()-t0:.2f}s] Expert created")

    print("Loading NLP models (10-20s on first run)...", flush=True)
    print(f"[{e.warmup_nl():.2f}s] NLP loaded")
    print(f"[{time.perf_counter()-t_start:.2f}s] total startup")

    print("=" * 70)
    print("Interactive mode. Type 'exit' to quit.")
    print("  • Вопрос:      «Кто директор технопарка Тюмень?»")
    print("  • Утверждение: «Смирнова Анна — директор технопарка Тюмень»")
    print("  • Императив:   «Хочу назначить директора в Тюмень»")
    print("=" * 70)

    while True:
        try:
            text = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not text:
            continue
        if text in ("exit", "quit", "выход"):
            return

        t0 = time.perf_counter()
        try:
            ans = e.ask(text, use_dialog=False)
        except RuntimeError as exc:
            print(f"✗ {exc}")
            continue
        elapsed = time.perf_counter() - t0

        if ans.query_result is None:
            # NL не распознан → ask_interactive (цикл доопроса)
            print(f"[{elapsed:.2f}s] NL-парсер не распознал — "
                  f"пробую ask_interactive()")
            try:
                result = e.ask_interactive(
                    text, top_k=3, max_turns=5)
            except RuntimeError as exc:
                print(f"✗ {exc}")
                continue
            print()
            print(result)
            print()
            print(f"graph: {e.graph.summary()}")
            if e._last_answer and e._last_answer.query_result:
                print()
                print("--- why() ---")
                print(e.why())
            continue

        print(f"[{elapsed:.2f}s]")
        print(ans.text)

        if ans.query_result.result:
            print()
            print("--- why() ---")
            print(e.why())
            continue

        try:
            fact_text = input(
                "[добавить факт, Enter — пропустить] > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if fact_text:
            t0 = time.perf_counter()
            r = e.assert_nl(fact_text)
            print(f"[{time.perf_counter()-t0:.2f}s] "
                  f"added={r.added}")
            if r.added.get("edges", 0) or r.added.get("nodes", 0):
                print(f"  graph: {e.graph.summary()}")


if __name__ == "__main__":
    main()