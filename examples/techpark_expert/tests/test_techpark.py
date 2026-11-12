"""Эталонные вопросы по технопаркам."""
import pytest

from pyagentprolog_expert import Expert, KnowledgeGraph


@pytest.fixture
def expert():
    g = KnowledgeGraph.from_prolog(open("graph.pl", encoding="utf-8").read())
    return Expert(graph=g, rules_file="rules.pl")


@pytest.mark.prolog
def test_director(expert):
    qr = expert.query("director_of('технопарк_саратов', X).")
    assert qr.ok
    assert qr.solutions == [{"X": "петров_петр"}]


@pytest.mark.prolog
def test_located_in_transitive(expert):
    qr = expert.query("located_in('технопарк_казань', X).")
    xs = {s["X"] for s in qr.solutions}
    assert "казань" in xs
    assert "татарстан" in xs
    assert "россия" in xs


@pytest.mark.prolog
def test_techpark_in_russia(expert):
    qr = expert.query("techpark_in_russia(T).")
    ts = {s["T"] for s in qr.solutions}
    assert "технопарк_саратов" in ts
    assert "технопарк_казань" in ts
    assert "технопарк_новосибирск" in ts
    assert "технопарк_тюмень" in ts


@pytest.mark.prolog
def test_without_director(expert):
    qr = expert.query("without_director(T).")
    ts = {s["T"] for s in qr.solutions}
    assert "технопарк_тюмень" in ts
    assert "технопарк_саратов" not in ts


@pytest.mark.prolog
def test_lift_transitive(expert):
    qr = expert.query(
        "edge('технопарк_казань', X, 'находиться_в').",
        category="transitive",
    )
    assert qr.lifted_from is not None
    xs = {s["X"] for s in qr.solutions}
    assert "россия" in xs


@pytest.mark.prolog
def test_human_readable(expert):
    qr = expert.query("attribute('петров_петр', label, L).")
    assert qr.solutions[0]["L"] == "Петров Пётр Иванович"


@pytest.mark.prolog
def test_alias(expert):
    qr = expert.query("alias('петров', F).")
    assert qr.solutions[0]["F"] == "петров_петр"


@pytest.mark.prolog
def test_format_uses_label(expert):
    qr = expert.query("director_of('технопарк_саратов', X).")
    text = expert._format_query_result(qr)
    assert "Петров Пётр Иванович" in text
    assert "петров_петр" not in text


@pytest.mark.prolog
@pytest.mark.nl
def test_ask_director(expert):
    ans = expert.ask("Кто директор технопарка Саратов?", use_dialog=False)
    assert "Петров" in ans.text


@pytest.mark.prolog
@pytest.mark.nl
def test_assert_control(expert):
    before = expert.graph.summary()["edges"]
    r = expert.assert_nl("Смирнова Анна контролирует технопарк Тюмень")
    if r.ok:
        assert expert.graph.summary()["edges"] >= before