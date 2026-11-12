"""demo.py — базовая демонстрация Expert на технопарках.

Что показывает:
  * Prolog-запросы поверх графа (без [nl]);
  * транзитивное замыкание, списки, отрицание;
  * query-lifting L1 → L2/L3;
  * NL-вопросы (ask) и NL-утверждения (assert_nl);
  * объяснимость (why).

Ключевые настройки:
  * ask(..., use_dialog=False) — DialogTurn в этой фразе классифицирует
    вопрос как утверждение; для демо отключаем диалог.
  * _dedup() / _uniq_values() — страховка, если Expert.query
    не дедуплицирует solutions.

Запуск:
    pip install "pyagentprolog-expert[nl]"
    python demo.py
"""
from __future__ import annotations

from typing import Any, Dict, List

from pyagentprolog_expert import Expert, KnowledgeGraph


# =====================================================================
# Утилиты
# =====================================================================
def load() -> Expert:
    g = KnowledgeGraph.from_prolog(
        open("graph.pl", encoding="utf-8").read()
    )
    return Expert(graph=g, rules_file="rules.pl")


def section(title: str) -> None:
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)


def _dedup(sols: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Убрать полные дубликаты биндингов.

    Страховка: если Expert.query вернул дубли (located_in/2 нашёл
    несколько путей к одному X), убираем их для вывода.
    """
    seen: set[tuple] = set()
    out: List[Dict[str, Any]] = []
    for s in sols:
        key = tuple(sorted((k, str(v)) for k, v in s.items()))
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def _uniq_values(sols: List[Dict[str, Any]], key: str) -> List[str]:
    """Уникальные значения поля key с сохранением порядка."""
    seen: set[str] = set()
    out: List[str] = []
    for s in sols:
        v = s.get(key)
        if v is None:
            continue
        sv = str(v)
        if sv in seen:
            continue
        seen.add(sv)
        out.append(sv)
    return out


# =====================================================================
# Демо
# =====================================================================
def main() -> None:
    e = load()

    # --------------------------------------------------------------
    section("1. Простой Prolog-запрос (без [nl])")
    # --------------------------------------------------------------
    qr = e.query("director_of('технопарк_саратов', X).")
    print(f"ok={qr.ok}  count={qr.count}")
    for sol in _dedup(qr.solutions):
        print(
            f"  X = {sol['X']}  →  "
            f"{e._describe_identifier(sol['X'])}"
        )

    # --------------------------------------------------------------
    section("2. Транзитивное замыкание — located_in/2")
    # --------------------------------------------------------------
    # located_in/2 транзитивно: возвращает ВСЕ уровни иерархии —
    # город, регион, страну. Это правильная семантика правила.
    qr = e.query("located_in('технопарк_казань', X).")
    xs = _uniq_values(qr.solutions, "X")
    print(f"Технопарк Казань находится в ({len(xs)}):")
    for x in xs:
        print(f"  • {e._describe_identifier(x)}  ({x})")
    print("  (located_in/2 транзитивно: город → регион → страна)")

    # --------------------------------------------------------------
    section("3. Список технопарков в России")
    # --------------------------------------------------------------
    qr = e.query("techpark_in_russia(T).")
    ts = _uniq_values(qr.solutions, "T")
    print(f"Всего технопарков в РФ: {len(ts)}")
    for t in ts:
        print(f"  • {e._describe_identifier(t)}")

    # --------------------------------------------------------------
    section("4. Технопарки без директора — отрицание")
    # --------------------------------------------------------------
    qr = e.query("without_director(T).")
    ts = _uniq_values(qr.solutions, "T")
    print(f"Без директора: {len(ts)}")
    for t in ts:
        print(f"  • {e._describe_identifier(t)}")

    # --------------------------------------------------------------
    section("5. Query-lifting: L1 → L2 (transitive)")
    # --------------------------------------------------------------
    qr = e.query(
        "edge('технопарк_казань', X, 'находиться_в').",
        category="transitive",
    )
    print("L1:  edge('технопарк_казань', X, 'находиться_в')")
    print(f"L2:  {qr.query.strip()}")
    print(f"lifted_from: {qr.lifted_from!r}")
    xs = _uniq_values(qr.solutions, "X")
    for x in xs:
        print(f"  • {e._describe_identifier(x)}")

    # --------------------------------------------------------------
    section("6. Query-lifting: L1 → L3 (list)")
    # --------------------------------------------------------------
    # Шаблон "list" в rules_engine._LIFT_PATTERNS использует
    # _translit('россия') == 'rossiya' → techpark_in_rossiya/1.
    # В rules.pl правило называется techpark_in_russia/1.
    # Gating по discover_rule_predicates → лифтинг не применяется.
    # См. README: как добавить явный шаблон.
    qr = e.query(
        "edge(X, 'россия', 'находиться_в').",
        category="list",
    )
    print(f"L1:  edge(X, 'россия', 'находиться_в')")
    print(f"L3:  {qr.query.strip()}")
    print(f"lifted_from: {qr.lifted_from!r}")
    if qr.lifted_from is None:
        print(
            "  ℹ️ Шаблон 'list' не сработал: в rules_engine._LIFT_PATTERNS\n"
            "     цель — techpark_in_rossiya/1 (транслит), а правило\n"
            "     называется techpark_in_russia/1. Gating gating'а.\n"
            "     См. README: явный шаблон для techpark_in_russia/1."
        )
    print(f"count (L1): {qr.count}")

    # --------------------------------------------------------------
    section("7. Регион технопарка — region_of/2")
    # --------------------------------------------------------------
    qr = e.query("region_of('технопарк_казань', R).")
    rs = _uniq_values(qr.solutions, "R")
    print(f"Регионов: {len(rs)}")
    for r in rs:
        print(f"  • {e._describe_identifier(r)}  ({r})")

    # --------------------------------------------------------------
    section("8. Кто контролирует технопарки")
    # --------------------------------------------------------------
    qr = e.query("controlled_by(T, Org).")
    for sol in _dedup(qr.solutions):
        t = e._describe_identifier(sol["T"])
        org = e._describe_identifier(sol["Org"])
        print(f"  {t} ← {org}")

    # --------------------------------------------------------------
    section("9. NL-вопрос через ask()  (use_dialog=False)")
    # --------------------------------------------------------------
    # use_dialog=False — иначе DialogTurn классифицирует вопрос
    # как утверждение и вернёт «Утверждение принято».
    try:
        ans = e.ask(
            "Кто директор технопарка Саратов?",
            use_dialog=False,
        )
        print(ans.text)
        print()
        print("--- why() ---")
        print(e.why())
    except RuntimeError as exc:
        print(f"[nl2prolog недоступен: {exc}]")

    # --------------------------------------------------------------
    section("10. NL-утверждение через assert_nl()  (best-effort)")
    # --------------------------------------------------------------
    try:
        from nl2prolog import TextToProlog

        phrase = "Смирнова Анна контролирует технопарк Тюмень"
        t2p = TextToProlog()
        facts_src, _ = t2p.parse(
            phrase, strict=True, facts_from_questions=True,
        )
        print(f"Фраза: {phrase!r}")
        print("nl2prolog извлёк:")
        print(repr(facts_src) if facts_src else "(пусто)")
        print()

        if "edge(" not in (facts_src or ""):
            print(
                "  ⚠️ nl2prolog не извлёк ни одного edge/3 — "
                "это ограничение NL-парсера, не Expert.\n"
                "     Попробуйте: «Петров Пётр владеет технопарком Тюмень»."
            )

        before = e.graph.summary()
        r = e.assert_nl(phrase)
        after = e.graph.summary()
        print(f"ok={r.ok}  added={r.added}  error={r.error}")
        print(f"before: {before}")
        print(f"after:  {after}")
    except RuntimeError as exc:
        print(f"[nl2prolog недоступен: {exc}]")

    # --------------------------------------------------------------
    section("11. NL-вопрос с category=transitive + why()")
    # --------------------------------------------------------------
    try:
        from nl2prolog import TextToProlog

        t2p = TextToProlog()
        question = "В какой стране технопарк Казань?"
        _, query_src = t2p.parse(
            question, strict=True, facts_from_questions=False,
        )
        print(f"Фраза: {question!r}")
        print(f"nl2prolog → query: {query_src!r}")
        print()

        if query_src:
            ans = e.ask(
                question,
                category="transitive",
                use_dialog=False,
            )
            print(ans.text)
            print()
            print(e.why())
        else:
            print(
                "  ⚠️ nl2prolog не распознал вопрос — "
                "это ограничение NL-парсера, не Expert.\n"
                "     Fallback: явный Prolog + лифтинг.\n"
                "     Попробуйте: «Где находится технопарк Казань?»."
            )
            qr = e.query(
                "edge('технопарк_казань', X, 'находиться_в').",
                category="transitive",
            )
            print(f"L1:  edge('технопарк_казань', X, 'находиться_в')")
            print(f"L2:  {qr.query.strip()}")
            print(f"lifted_from: {qr.lifted_from!r}")
            xs = _uniq_values(qr.solutions, "X")
            for x in xs:
                print(f"  • {e._describe_identifier(x)}")
    except RuntimeError as exc:
        print(f"[nl2prolog недоступен: {exc}]")


if __name__ == "__main__":
    main()