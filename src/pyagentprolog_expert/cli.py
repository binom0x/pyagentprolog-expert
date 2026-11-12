"""cli.py — REPL для pyagentprolog-expert.

    $ pa-expert --graph graph.pl --rules rules.pl
    > Кто директор технопарка Саратов?
    ✓ Решение:
    [1] X = Петров Пётр

    > !!why
    Запрос: edge(X, 'технопарк_саратов', 'директор').
    ...

Команды:
    !!why       объяснение последнего ответа
    !!assert    NL-утверждение → граф (интерактивный ввод)
    !!graph     статистика графа
    !!rules     правила загружены/пусты
    !!reset     сброс последнего ответа
    !!quit      выход
"""
from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path

from . import Expert
from .graph import KnowledgeGraph
from .rules_engine import load_rules


def _read(path: str | None) -> str:
    if not path:
        return ""
    p = Path(path)
    return p.read_text(encoding="utf-8") if p.is_file() else ""


def main(argv: list[str] | None = None) -> int:
    # Windows: принудительно UTF-8 для stdout/stderr,
    # чтобы кириллица в --help и в ответах не падала с UnicodeEncodeError.
    if sys.platform == "win32":
        try:
            if isinstance(sys.stdout, io.TextIOWrapper):
                sys.stdout.reconfigure(encoding="utf-8")
            if isinstance(sys.stderr, io.TextIOWrapper):
                sys.stderr.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass

    parser = argparse.ArgumentParser(
        prog="pa-expert",
        description="Expert system on knowledge graphs "
                    "(PyAgentProlog + nl2prolog)",
    )
    parser.add_argument("--graph", help="путь к graph.pl")
    parser.add_argument("--rules", help="путь к rules.pl")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)

    graph = KnowledgeGraph.from_prolog(_read(args.graph))
    rules_src = load_rules(args.rules)

    print(f"[pa-expert] graph: {graph.summary()}")
    print(f"[pa-expert] rules: {'загружен' if rules_src else 'пуст'}")
    print("Команды: !!why, !!assert, !!graph, !!rules, !!reset, !!quit")

    expert = Expert(
        graph=graph,
        rules_file=args.rules,
        debug=args.debug,
    )

    while True:
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            continue
        if line in ("!!quit", "!!exit", ":q"):
            return 0
        if line == "!!why":
            print(expert.why())
            continue
        if line == "!!graph":
            print(expert.graph.summary())
            continue
        if line == "!!rules":
            print("загружен" if expert.rules_src else "пуст")
            continue
        if line == "!!reset":
            expert.reset()
            print("сброшено")
            continue
        if line == "!!assert":
            print("Введите NL-утверждение (пустая строка — отмена):")
            text = input("…> ").strip()
            if not text:
                continue
            try:
                r = expert.assert_nl(text)
                print(f"ok={r.ok} added={r.added} error={r.error}")
            except RuntimeError as e:
                print(f"✗ {e}", file=sys.stderr)
            continue
        try:
            ans = expert.ask(line)
            print(ans.text)
        except RuntimeError as e:
            print(f"✗ {e}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
