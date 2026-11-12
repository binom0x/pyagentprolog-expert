"""Общие фикстуры для тестов pyagentprolog-expert."""
import pytest

from pyagentprolog_expert import Expert, KnowledgeGraph


@pytest.fixture
def demo_graph():
    """Граф без доменных фактов в rules.pl.

    Все данные (label, alias_of, solution) — в графе.
    """
    g = KnowledgeGraph()

    # узлы
    g.add_node("технопарк_саратов", "technopark")
    g.add_node("технопарк_казань", "technopark")
    g.add_node("петров_петр", "person")
    g.add_node("иванов_иван", "person")
    g.add_node("россия", "place")
    g.add_node("саратов", "place")
    g.add_node("казань", "place")

    # рёбра
    g.add_edge("петров_петр", "технопарк_саратов", "директор")
    g.add_edge("иванов_иван", "технопарк_казань", "директор")
    g.add_edge("технопарк_саратов", "саратов", "находиться_в")
    g.add_edge("технопарк_казань", "казань", "находиться_в")
    g.add_edge("саратов", "россия", "находиться_в")
    g.add_edge("казань", "россия", "находиться_в")

    # alias_of — данные, не факт rules.pl
    g.add_edge("петров", "петров_петр", "alias_of")
    g.add_edge("иванов", "иванов_иван", "alias_of")

    # solution — узел + рёбра, не факт rules.pl
    g.add_node("назначить_петрова", "solution")
    g.add_edge("назначить_петрова", "технопарк_саратов", "target")
    g.add_edge("назначить_петрова", "петров_петр", "director")

    # label — attribute/3, не human_readable/2
    g.add_attribute("петров_петр", "label", "Петров Пётр")
    g.add_attribute("иванов_иван", "label", "Иванов Иван")
    g.add_attribute("технопарк_саратов", "label", "Технопарк Саратов")
    g.add_attribute("технопарк_казань", "label", "Технопарк Казань")
    g.add_attribute("россия", "label", "Россия")

    return g


@pytest.fixture
def demo_rules(tmp_path):
    """rules.pl — ТОЛЬКО СХЕМА. Никаких доменных фактов."""
    p = tmp_path / "rules.pl"
    p.write_text(
        "% --- транзитивное замыкание ---\n"
        "located_in(X, Y) :- edge(X, Y, 'находиться_в').\n"
        "located_in(X, Y) :- edge(X, Z, 'находиться_в'), "
        "located_in(Z, Y).\n"
        "\n"
        "% --- список по типу ---\n"
        "techpark_in_russia(T) :-\n"
        "    node(T, _, technopark),\n"
        "    located_in(T, 'россия').\n"
        "\n"
        "% --- alias: схема, данные — edge(Short, Full, 'alias_of') ---\n"
        "alias(Short, Full) :- edge(Short, Full, 'alias_of').\n"
        "\n"
        "% --- human_readable: схема, данные — attribute(Id, 'label', L) ---\n"
        "human_readable(Id, Label) :- attribute(Id, 'label', Label).\n"
        "\n"
        "% --- solution: схема, данные — node(S, [], solution) + рёбра ---\n"
        "solution(S) :- node(S, _, solution).\n"
        "\n"
        "condition(triplet('директор', P, Org)) :-\n"
        "    edge(S, Org, 'target'),\n"
        "    edge(S, P, 'director'),\n"
        "    solution(S).\n",
        encoding="utf-8",
    )
    return str(p)


@pytest.fixture
def expert(demo_graph, demo_rules):
    return Expert(graph=demo_graph, rules_file=demo_rules)
