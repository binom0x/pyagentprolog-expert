"""rules_engine — загрузка правил, discovery, lifting."""
from pyagentprolog_expert import (
    discover_rule_predicates,
    lift_query,
    load_rules,
)


def test_load_missing():
    assert load_rules(None) == ""
    assert load_rules("/no/such/file.pl") == ""


def test_load_existing(tmp_path):
    p = tmp_path / "rules.pl"
    p.write_text("located_in(X, Y) :- edge(X, Y, 'in').\n")
    assert "located_in" in load_rules(str(p))


def test_discover():
    src = (
        "located_in(X, Y) :- edge(X, Y, 'находиться_в').\n"
        "techpark_in_russia(T) :- node(T, _, technopark).\n"
        "alias('a', 'b').\n"
    )
    preds = discover_rule_predicates(src)
    assert ("located_in", 2) in preds
    assert ("techpark_in_russia", 1) in preds
    assert ("alias", 2) in preds


def test_lift_gated_by_rules():
    known = {("located_in", 2)}
    lifted = lift_query(
        "edge('a', X, 'находиться_в')", "transitive", known)
    assert "located_in" in lifted

    lifted2 = lift_query(
        "edge('a', X, 'находиться_в')", "transitive", set())
    assert "edge(" in lifted2


def test_lift_no_category():
    known = {("located_in", 2)}
    q = "edge('a', X, 'находиться_в')"
    assert lift_query(q, None, known) == q
