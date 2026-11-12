"""rules_engine.py — правила предметной области и query-lifting.

Правила (Horn-клаузы: located_in/2, solution/1, human_readable/2 …) —
это НЕ формат графа знаний. Они живут в отдельном файле `rules.pl` и
подгружаются в Agent вместе с `_CONVENIENCE_RULES` на каждый запрос.
`KnowledgeGraph` их не видит и не сериализует (по контракту
«Формат графа знаний на Prolog» §2.6, §7.2).

Функции:
    load_rules(path) -> str
    lift_query(query, category, known_rules) -> str
    discover_rule_predicates(rules_src) -> set[tuple[str, int]]
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

_LIFT_PATTERNS = (
    (
        "transitive",
        re.compile(
            r"^edge\('(?P<s>[^']+)',\s*(?P<o>X|[^,]+),\s*"
            r"'находиться_в'\)$"
        ),
        lambda m: f"located_in('{m.group('s')}', {m.group('o')})",
    ),
    (
        "list",
        re.compile(
            r"^edge\(X,\s*'(?P<o>[^']+)',\s*'находиться_в'\)$"
        ),
        lambda m: f"techpark_in_{_translit(m.group('o'))}(X)",
    ),
    (
        "region",
        re.compile(
            r"^edge\('(?P<s>[^']+)',\s*X,\s*'находиться_в'\)$"
        ),
        lambda m: f"region_of('{m.group('s')}', X)",
    ),
)

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e",
    "ё": "e", "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k",
    "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "shch", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
}


def _translit(s: str) -> str:
    return "".join(_TRANSLIT.get(ch, ch) for ch in s.lower())


def load_rules(path: Optional[str]) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.is_file():
        return ""
    return p.read_text(encoding="utf-8")


def lift_query(
    query: str,
    category: Optional[str],
    known_rules: set[tuple[str, int]],
) -> str:
    if not category or not query:
        return query
    for cat, pat, build in _LIFT_PATTERNS:
        if cat != category:
            continue
        m = pat.match(query.strip())
        if not m:
            continue
        lifted = build(m)
        pred = lifted.split("(", 1)[0]
        arity = lifted.count(",") + 1 if "(" in lifted else 0
        if (pred, arity) in known_rules:
            return lifted
    return query


def discover_rule_predicates(rules_src: str) -> set[tuple[str, int]]:
    found: set[tuple[str, int]] = set()
    head_re = re.compile(
        r"^\s*([a-z][A-Za-z0-9_]*)\s*\(([^)]*)\)", re.MULTILINE
    )
    for m in head_re.finditer(rules_src or ""):
        functor = m.group(1)
        args = m.group(2).strip()
        arity = 0 if not args else args.count(",") + 1
        found.add((functor, arity))
    return found


__all__ = ["discover_rule_predicates", "lift_query", "load_rules"]
