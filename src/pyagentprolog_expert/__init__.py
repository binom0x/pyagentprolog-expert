"""pyagentprolog-expert — экспертная система на графе знаний.

Публичный фасад. Пакет НЕ требует установленного kg-editor:
`KnowledgeGraph` встроен (см. graph.py).

Опциональные зависимости:
  * nl2prolog   — для `Expert.ask()` / `Expert.assert_nl()`;
  * sentence-transformers — для семантической унификации.

Без них работают `Expert.query()`, `Expert.assert_facts_src()`,
`Expert.why()`, весь CLI (кроме `!!assert`).

    from pyagentprolog_expert import Expert, KnowledgeGraph

    g = KnowledgeGraph.from_prolog(open("graph.pl").read())
    e = Expert(graph=g, rules_file="rules.pl")
    print(e.query("edge(X, 'obj', 'pred').").solutions)

    # если установлен nl2prolog:
    print(e.ask("Кто директор технопарка Саратов?").text)
"""
from __future__ import annotations

from ._version import __version__, __version_info__
from .expert import (
    AssertResult,
    Expert,
    ExpertAnswer,
    QueryResult,
)
from .graph import (
    Attribute,
    Edge,
    KnowledgeGraph,
    Node,
)
from .humanize import (
    humanize_vars,
    is_var_like,
    strip_var_suffix,
)
from .rules_engine import (
    discover_rule_predicates,
    lift_query,
    load_rules,
)
from .session import (
    NullSession,
    Session,
)

__all__ = [
    "AssertResult",
    "Attribute",
    "Edge",
    # эксперт
    "Expert",
    "ExpertAnswer",
    # граф
    "KnowledgeGraph",
    "Node",
    "NullSession",
    "QueryResult",
    # session
    "Session",
    # версия
    "__version__",
    "__version_info__",
    "discover_rule_predicates",
    "humanize_vars",
    "is_var_like",
    "lift_query",
    # rules
    "load_rules",
    # humanize
    "strip_var_suffix",
]
