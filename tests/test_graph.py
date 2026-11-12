"""Встроенный KnowledgeGraph — базовые тесты."""
import pytest

from pyagentprolog_expert import KnowledgeGraph


def test_empty():
    g = KnowledgeGraph()
    assert g.summary() == {"nodes": 0, "edges": 0, "attributes": 0}
    assert g.to_prolog() == ""


def test_add_node():
    g = KnowledgeGraph()
    g.add_node("apple", "org")
    assert "apple" in g.nodes
    assert g.nodes["apple"].type == "org"


def test_add_node_upsert():
    g = KnowledgeGraph()
    g.add_node("apple", "concept", {"weight": "0.5"})
    g.add_node("apple", "org")          # тип перезаписан
    assert g.nodes["apple"].type == "org"
    assert g.nodes["apple"].props == {"weight": "0.5"}   # props сохранены


def test_add_edge_creates_nodes():
    g = KnowledgeGraph()
    g.add_edge("a", "b", "owns")
    assert "a" in g.nodes and "b" in g.nodes
    assert len(g.edges) == 1


def test_remove_node_cascade():
    g = KnowledgeGraph()
    g.add_edge("a", "b", "owns")
    g.add_attribute("a", "name", "A")
    g.remove_node("a")
    assert "a" not in g.nodes
    assert len(g.edges) == 0
    assert len(g.attributes) == 0


def test_from_prolog_roundtrip():
    """from_prolog(to_prolog(from_prolog(src))) == from_prolog(src).

    Полный roundtrip `to_prolog == src` невозможен: from_prolog
    авто-создаёт узлы для edge/3 (iphone из edge(apple, iphone, releases)),
    и to_prolog их сериализует. Это часть контракта.
    """
    src = (
        "node(apple, [], org).\n"
        "edge(apple, iphone, releases).\n"
        "attribute(iphone, release_year, '2022').\n"
    )
    g1 = KnowledgeGraph.from_prolog(src)
    g2 = KnowledgeGraph.from_prolog(g1.to_prolog())
    assert g1.summary() == g2.summary()
    assert g1.to_prolog() == g2.to_prolog()
    # Явно: авто-созданный iphone сериализуется
    assert "node(iphone, [], concept)." in g1.to_prolog()


def test_from_prolog_ignores_rules():
    src = (
        "node(apple, [], org).\n"
        "grandparent(X, Z) :- parent(X, Y), parent(Y, Z).\n"
        "located_in(X, Y) :- edge(X, Y, 'находиться_в').\n"
    )
    g = KnowledgeGraph.from_prolog(src)
    assert g.summary()["nodes"] == 1
    assert "grandparent" not in g.to_prolog()


def test_merge_additive():
    """merge аддитивен: узлы/рёбра/атрибуты не перезаписываются.

    `b` авто-создаётся в обоих графах через edge(a, b, owns), поэтому
    skipped_nodes=2 (a и b), а не 1.
    """
    g1 = KnowledgeGraph.from_prolog(
        "node(a, [], org).\nedge(a, b, owns).\n"
    )
    g2 = KnowledgeGraph.from_prolog(
        "node(a, [], concept).\nnode(c, [], org).\nedge(a, b, owns).\n"
    )
    stats = g1.merge(g2)
    # a уже есть, b авто-создан в обоих → skipped_nodes=2
    # c новый → added_nodes=1
    assert stats["added_nodes"] == 1
    assert stats["skipped_nodes"] == 2
    # (a,b,owns) уже есть → skipped_edges=1
    assert stats["added_edges"] == 0
    assert stats["skipped_edges"] == 1
    assert g1.nodes["a"].type == "org"  # a не перезаписан


def test_quoted_cyrillic():
    g = KnowledgeGraph()
    g.add_node("ООО «Ромашка»", "org")
    src = g.to_prolog()
    assert "'ООО «Ромашка»'" in src
    g2 = KnowledgeGraph.from_prolog(src)
    assert "ООО «Ромашка»" in g2.nodes


def test_generic_filter_off_by_default():
    """Готовый граф уже валиден — фильтр по умолчанию не отбрасывает."""
    g = KnowledgeGraph()
    g.add_node("очень", "concept")   # прошло
    assert "очень" in g.nodes


def test_generic_filter_custom():
    g = KnowledgeGraph(generic_filter=lambda w: w == "очень")
    with pytest.raises(ValueError):
        g.add_node("очень")
    g.add_node("apple")   # ok
