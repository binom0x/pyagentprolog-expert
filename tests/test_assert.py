"""NL/Prooflog-утверждения → граф."""
import pytest


@pytest.mark.prolog
def test_assert_facts_adds_nodes(expert):
    before = expert.graph.summary()["nodes"]
    r = expert.assert_facts_src(
        "node('new_org', [], org).\n"
        "edge('new_org', 'технопарк_саратов', 'партнёр').\n"
    )
    assert r.ok
    assert r.added["nodes"] == 1
    assert r.added["edges"] == 1
    assert expert.graph.summary()["nodes"] == before + 1


@pytest.mark.prolog
def test_assert_idempotent(expert):
    src = "node('new_org', [], org)."
    r1 = expert.assert_facts_src(src)
    r2 = expert.assert_facts_src(src)
    assert r1.added["nodes"] == 1
    assert r2.added["nodes"] == 0


@pytest.mark.prolog
def test_assert_empty(expert):
    r = expert.assert_facts_src("")
    assert r.ok
    assert r.added == {"nodes": 0, "edges": 0, "attributes": 0}


@pytest.mark.prolog
def test_assert_ignores_rules(expert):
    """Horn-клаузы в facts_src игнорируются KnowledgeGraph."""
    before = expert.graph.summary()
    r = expert.assert_facts_src(
        "node('a', [], org).\n"
        "grandparent(X, Z) :- parent(X, Y), parent(Y, Z).\n"
    )
    assert r.ok
    assert r.added["nodes"] == 1
    after = expert.graph.summary()
    assert after["nodes"] == before["nodes"] + 1


@pytest.mark.prolog
def test_assert_label_as_attribute(expert):
    """label добавляется как attribute/3, не как human_readable/2."""
    r = expert.assert_facts_src(
        "node('new_org', [], org).\n"
        "attribute('new_org', 'label', 'Новая организация').\n"
    )
    assert r.ok
    assert r.added["attributes"] == 1
    # Проверяем через attribute/3
    qr = expert.query("attribute('new_org', 'label', L).")
    assert qr.solutions[0]["L"] == "Новая организация"


@pytest.mark.prolog
def test_assert_alias_of_edge(expert):
    """alias_of — ребро, не факт rules.pl."""
    r = expert.assert_facts_src(
        "edge('ромашка', 'ООО «Ромашка»', 'alias_of').\n"
    )
    assert r.ok
    assert r.added["edges"] == 1
    # alias/2-схема из rules.pl видит это ребро
    qr = expert.query("alias('ромашка', F).")
    assert qr.solutions[0]["F"] == "ООО «Ромашка»"
