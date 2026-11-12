"""Контракт: rules.pl содержит только СХЕМУ, не доменные факты.

Доменные данные (label, alias, solution, …) — в graph.pl.
Проверяем через разбор rules.pl из фикстуры demo_rules.
"""
import re
from pathlib import Path

import pytest

# Доменные факты, которые НЕ должны встречаться в rules.pl
_DOMAIN_FACT_PATTERNS = (
    # human_readable/2 как факт: human_readable('x', 'y').  (без :-)
    re.compile(
        r"human_readable\s*\(\s*'[^']+'\s*,\s*'[^']*'\s*\)\s*\.",
    ),
    # alias/2 как факт: alias('x', 'y').  (без :-)
    re.compile(
        r"alias\s*\(\s*'[^']+'\s*,\s*'[^']+'\s*\)\s*\.",
    ),
    # solution/1 как факт: solution('x').  (без :-)
    re.compile(
        r"solution\s*\(\s*'[^']+'\s*\)\s*\.",
    ),
)


def _read_rules_src(rules_path: str) -> str:
    return Path(rules_path).read_text(encoding="utf-8")


@pytest.mark.parametrize("pattern", _DOMAIN_FACT_PATTERNS)
def test_no_domain_fact_in_rules(demo_rules, pattern):
    """В rules.pl не должно быть доменных ФАКТОВ (только СХЕМА с :-)."""
    src = _read_rules_src(demo_rules)
    for m in pattern.finditer(src):
        # Факт = нет ':-' до конца клаузы. Схема = есть ':-'.
        # Простая эвристика: ищем ':-' в той же строке или следующих
        # до '.'; если нет — это факт.
        start = m.start()
        end = m.end()
        line_start = src.rfind("\n", 0, start) + 1
        line_end = src.find("\n", end)
        if line_end == -1:
            line_end = len(src)
        line = src[line_start:line_end]
        assert ":-" in line, (
            f"Доменный факт в rules.pl: {line.strip()!r}\n"
            f"Данные домена должны быть в graph.pl "
            f"(attribute/edge/node), а в rules.pl — только СХЕМА."
        )


def test_rules_only_schemas(demo_rules):
    """rules.pl содержит нужные схемы и не содержит доменных фактов."""
    src = _read_rules_src(demo_rules)

    # Схемы должны быть
    assert "located_in(X, Y) :- edge" in src
    assert "human_readable(Id, Label) :- attribute" in src
    assert "alias(Short, Full) :- edge" in src
    assert "solution(S) :- node" in src

    # Доменных фактов быть не должно
    for pattern in _DOMAIN_FACT_PATTERNS:
        for m in pattern.finditer(src):
            line_start = src.rfind("\n", 0, m.start()) + 1
            line_end = src.find("\n", m.end())
            if line_end == -1:
                line_end = len(src)
            line = src[line_start:line_end]
            assert ":-" in line, (
                f"Доменный факт в rules.pl: {line.strip()!r}"
            )


def test_rules_does_not_contain_entity_names(demo_rules):
    """В rules.pl не должно быть конкретных имён сущностей как фактов."""
    src = _read_rules_src(demo_rules)
    # 'петров_петр', 'технопарк_саратов', 'россия' — только в graph.pl
    forbidden = [
        "петров_петр", "иванов_иван",
        "технопарк_саратов", "технопарк_казань",
    ]
    # Разрешаем 'россия' в схеме techpark_in_russia/1 — это домен
    # в схеме, но допустимо: предикат назван по домену.
    for name in forbidden:
        # Ищем как ФАКТ (в кавычках, без ':-' в строке)
        pattern = re.compile(
            rf"['\"]{re.escape(name)}['\"]\s*[,)]"
        )
        for m in pattern.finditer(src):
            line_start = src.rfind("\n", 0, m.start()) + 1
            line_end = src.find("\n", m.end())
            if line_end == -1:
                line_end = len(src)
            line = src[line_start:line_end]
            assert ":-" in line or "#" in line or "%" in line, (
                f"Имя сущности {name!r} в rules.pl вне схемы: "
                f"{line.strip()!r}"
            )
