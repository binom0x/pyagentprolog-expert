"""Базовые тесты Expert."""
import pytest

from pyagentprolog_expert import Expert, KnowledgeGraph


@pytest.mark.prolog
def test_query_edge(expert):
    qr = expert.query("edge(X, 'технопарк_саратов', 'директор').")
    assert qr.ok
    assert qr.count == 1
    assert qr.solutions[0]["X"] == "петров_петр"


@pytest.mark.prolog
def test_query_true(expert):
    qr = expert.query("node('технопарк_саратов', _, technopark).")
    assert qr.ok
    assert qr.result is True


@pytest.mark.prolog
def test_query_false(expert):
    qr = expert.query("edge(X, 'нет_такого', _).")
    assert qr.ok
    assert qr.result is False


@pytest.mark.prolog
def test_empty_query(expert):
    qr = expert.query("")
    assert not qr.ok
    assert "пустой" in qr.error


@pytest.mark.prolog
def test_why_before_any(expert):
    assert "Пока нет" in expert.why()


@pytest.mark.prolog
def test_expert_default_graph():
    """Expert без graph создаёт пустой встроенный KnowledgeGraph."""
    e = Expert()
    assert isinstance(e.graph, KnowledgeGraph)
    assert e.graph.summary()["nodes"] == 0


@pytest.mark.prolog
def test_expert_no_kg_editor_needed():
    """Пакет работает без установленного kg-editor."""
    import pyagentprolog_expert
    assert hasattr(pyagentprolog_expert, "KnowledgeGraph")


@pytest.mark.prolog
def test_label_via_attribute(expert):
    """label — attribute/3 графа, а не human_readable/2 в rules.pl."""
    qr = expert.query("attribute('петров_петр', 'label', L).")
    assert qr.ok
    assert qr.solutions[0]["L"] == "Петров Пётр"


@pytest.mark.prolog
def test_human_readable_schema(expert):
    """human_readable/2 — СХЕМА в rules.pl, читает attribute/3."""
    qr = expert.query("human_readable('петров_петр', L).")
    assert qr.ok
    assert qr.solutions[0]["L"] == "Петров Пётр"


@pytest.mark.prolog
def test_alias_schema(expert):
    """alias/2 — СХЕМА в rules.pl, читает edge(_, _, 'alias_of')."""
    qr = expert.query("alias('петров', F).")
    assert qr.ok
    assert qr.solutions[0]["F"] == "петров_петр"


@pytest.mark.prolog
def test_solution_schema(expert):
    """solution/1 — СХЕМА, читает node(S, _, solution)."""
    qr = expert.query("solution(S).")
    assert qr.ok
    sols = {s["S"] for s in qr.solutions}
    assert "назначить_петрова" in sols


@pytest.mark.prolog
def test_format_result_uses_label(expert):
    """_format_query_result подставляет label вместо ID."""
    # nl2prolog может не установить связь 'технопарк Саратов' → технопарк_саратов
    # без alias. Проверяем напрямую через query.
    qr = expert.query("edge(X, 'технопарк_саратов', 'директор').")
    text = expert._format_query_result(qr)
    assert "Петров Пётр" in text
    assert "петров_петр" not in text


@pytest.mark.prolog
def test_describe_identifier_fallback(expert):
    """Без label — fallback humanize + подчёркивания → пробелы."""
    expert.graph.add_node("без_лейбла", "concept")
    # attribute(Id, 'label', L) не задан — fallback
    assert expert._describe_identifier("без_лейбла") == "без лейбла"
