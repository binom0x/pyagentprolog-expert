"""Query-lifting: L1 → L2/L3 по category."""
import pytest

from pyagentprolog_expert import Expert, KnowledgeGraph


@pytest.mark.prolog
def test_lift_transitive(expert, demo_graph):
    demo_graph.add_edge("технопарк_казань", "россия", "находиться_в")
    qr = expert.query(
        "edge('технопарк_казань', X, 'находиться_в').",
        category="transitive",
    )
    assert qr.ok
    assert qr.lifted_from is not None
    assert "located_in" in qr.query
    # located_in/2 даёт и прямой факт (казань), и транзитивный (россия)
    xs = {s["X"] for s in qr.solutions}
    assert "казань" in xs
    assert "россия" in xs


@pytest.mark.prolog
def test_no_lift_when_rule_missing():
    """category=transitive, но located_in/2 нет в rules.pl."""
    g = KnowledgeGraph()
    g.add_edge("a", "b", "находиться_в")
    e = Expert(graph=g, rules_file=None)
    qr = e.query(
        "edge('a', X, 'находиться_в').", category="transitive")
    assert qr.lifted_from is None
    assert "edge(" in qr.query


@pytest.mark.prolog
def test_lift_disabled_by_default(expert, demo_graph):
    """Без category — никакого лифтинга."""
    demo_graph.add_edge("технопарк_казань", "россия", "находиться_в")
    qr = expert.query(
        "edge('технопарк_казань', X, 'находиться_в').")
    assert qr.lifted_from is None
    assert "edge(" in qr.query
