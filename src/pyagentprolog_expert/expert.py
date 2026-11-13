"""Expert — экспертная система на графе знаний.

PyAgentProlog (Agent) — движок вывода (опционально).
nl2prolog (TextToProlog, DialogTurn) — NL→query и NL→facts (опционально).
Встроенный KnowledgeGraph — источник фактов.

Формат KB — граф знаний:
    node(Id, Props, Type).
    edge(Source, Target, Predicate).
    attribute(Entity, Name, Value).

Правила предметной области (Horn-клаузы: located_in/2, solution/1,
human_readable/2) хранятся в rules.pl и подгружаются в Agent на каждый
запрос вместе с _CONVENIENCE_RULES. KnowledgeGraph их не видит.

Схема vs данные:
  * graph.pl   — ДАННЫЕ: сущности, связи, свойства (label, alias_of,
                 solution-узлы).
  * rules.pl   — СХЕМА: как связывать факты.
Expert не знает ни одной сущности домена в коде.

Архитектура импортов:
  * `prolog` (PyAgentProlog) — лениво, на первом query().
    `import prolog` занимает 10-15 с (numba/numpy/interpreter).
  * `nl2prolog` — лениво, на первом ask()/assert_nl().
    `import nl2prolog` + TextToProlog() — ещё 5-15 с.
  * `import pyagentprolog_expert` <0.2 с; `Expert()` <0.01 с.

Использование:
    e = Expert(graph=g, rules_file="rules.pl")   # <0.01 с
    qr = e.query("edge(X, 'a', 'b').")            # +10-15 с при первом
    ans = e.ask("Кто директор?")                  # +5-15 с при первом
    e.warmup_nl()                                  # явная загрузка NLP
"""
from __future__ import annotations

import contextlib
import re
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .graph import KnowledgeGraph
from .humanize import humanize_vars
from .rules_engine import (
    discover_rule_predicates,
    lift_query,
    load_rules,
)
from .session import NullSession, Session


# =====================================================================
# Lazy imports
# =====================================================================
_Agent: Any = None
_AGENT_OK: Optional[bool] = None
_AGENT_LOCK = threading.Lock()

_TextToProlog: Any = None
_DialogTurn: Any = None
_NL2PROLOG_OK: Optional[bool] = None
_NL2PROLOG_LOCK = threading.Lock()


def _ensure_agent() -> bool:
    """Lazy import `prolog.agent.Agent`. Возвращает True, если доступен."""
    global _Agent, _AGENT_OK
    if _AGENT_OK is not None:
        return _AGENT_OK
    with _AGENT_LOCK:
        if _AGENT_OK is not None:
            return _AGENT_OK
        try:
            from prolog.agent import Agent as _A
            _Agent = _A
            _AGENT_OK = True
        except ImportError:
            _Agent = None
            _AGENT_OK = False
        return _AGENT_OK


def _ensure_nl2prolog() -> bool:
    """Lazy import `nl2prolog`. Возвращает True, если доступен."""
    global _TextToProlog, _DialogTurn, _NL2PROLOG_OK
    if _NL2PROLOG_OK is not None:
        return _NL2PROLOG_OK
    with _NL2PROLOG_LOCK:
        if _NL2PROLOG_OK is not None:
            return _NL2PROLOG_OK
        try:
            from nl2prolog import DialogTurn, TextToProlog
            _TextToProlog = TextToProlog
            _DialogTurn = DialogTurn
            _NL2PROLOG_OK = True
        except ImportError:
            _TextToProlog = None
            _DialogTurn = None
            _NL2PROLOG_OK = False
        return _NL2PROLOG_OK


# =====================================================================
# Convenience rules — добавляются в Agent на каждый запрос
# =====================================================================
_CONVENIENCE_RULES = """
% --- convenience rules (added by Expert) ---
node(Id, Type) :- node(Id, _, Type).
edge(S, T) :- edge(S, T, _).

% condition_check/1 — true if the condition holds in the graph.
% Domain-neutral; used by ask_interactive() for _missing_conditions().
condition_check(triplet(P, S, O)) :- edge(S, O, P).
condition_check(attr(N, A)) :- attribute(N, A, _).
condition_check(fact(F)) :- node(F, _, _).
"""

_SOLUTION_LIMIT = 1000

# Валидный атом — совпадает с graph._VALID_ATOM.
_VALID_ATOM_RE = re.compile(r"^[a-z][A-Za-z0-9_]*$")
_RESERVED_ATOMS = {"is", "mod", "div", "rem", "xor", "not"}

# Регексы для разбора triplet/attr/fact в _missing_conditions()
# и _add_triplet_fallback(). Принимают аргументы как в кавычках, так
# и без — `findall(C, condition(C), Cs)` возвращает уже развёрнутый
# аргумент, часто без кавычек:
#     triplet(director, смирнова_анна, технопарк_тюмень)
_TRIPLET_RE = re.compile(
    r"triplet\(\s*['\"]?([^,()'\"]+?)['\"]?\s*,\s*"
    r"['\"]?([^,()'\"]+?)['\"]?\s*,\s*"
    r"['\"]?([^,()'\"]+?)['\"]?\s*\)"
)
_ATTR_RE = re.compile(
    r"attr\(\s*['\"]?([^,()'\"]+?)['\"]?\s*,\s*"
    r"['\"]?([^,()'\"]+?)['\"]?\s*\)"
)
_FACT_RE = re.compile(r"fact\(\s*['\"]?([^,()'\"]+?)['\"]?\s*\)")


# =====================================================================
# Результаты
# =====================================================================
@dataclass
class QueryResult:
    ok: bool
    query: str
    solutions: List[Dict[str, Any]] = field(default_factory=list)
    result: Optional[bool] = None
    error: Optional[str] = None
    lifted_from: Optional[str] = None

    @property
    def count(self) -> int:
        return len(self.solutions)


@dataclass
class AssertResult:
    ok: bool
    facts_src: str
    added: Dict[str, int] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class ExpertAnswer:
    text: str
    query_result: Optional[QueryResult] = None
    used_rules: List[str] = field(default_factory=list)
    category: Optional[str] = None


# =====================================================================
# Дедупликация решений
# =====================================================================
def _dedup_solutions(
    sols: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Убрать полные дубликаты биндингов.

    located_in/2 может найти несколько путей к одному X
    (например, «казань → татарстан → россия» и «казань → россия»),
    если в graph.pl есть прямые рёбра. Дедуплицируем для вывода.
    """
    seen: set[tuple] = set()
    out: List[Dict[str, Any]] = []
    for s in sols:
        key = tuple(sorted((k, str(v)) for k, v in s.items()))
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


# =====================================================================
# Expert
# =====================================================================
class Expert:
    def __init__(
        self,
        graph: Optional[KnowledgeGraph] = None,
        rules_file: Optional[str] = None,
        t2p: Optional[Any] = None,
        t2p_kwargs: Optional[dict] = None,
        debug: bool = False,
        semantic: bool = False,
        semantic_config: Optional[dict] = None,
        session: Optional[Session] = None,
        preload_nl: bool = False,
    ) -> None:
        # Без _require: pyagentprolog проверяется лениво в query(),
        # nl2prolog — в ask()/assert_nl(). Это делает импорт и
        # Expert() быстрыми (<0.1 с).
        self.graph = graph if graph is not None else KnowledgeGraph()
        self.debug = debug
        self.session = session or NullSession()

        self.rules_src = self._normalize_query_atoms(
            load_rules(rules_file))
        self._known_rules = discover_rule_predicates(self.rules_src)

        # Кэш human_readable: attribute(Id, 'label', L) из графа
        self._label_cache: Dict[str, Optional[str]] = {}

        # Ленивая инициализация NLP
        self.t2p = t2p
        self._t2p_kwargs: Dict[str, Any] = dict(t2p_kwargs or {})
        self.dlg = None
        self._nl_ready = False
        self._nl_lock = threading.Lock()

        self._last_answer: Optional[ExpertAnswer] = None
        self._last_missing_inner: Optional[str] = None
        self._semantic_active = False

        if semantic:
            self.enable_semantic(semantic_config or {})

        if preload_nl and _ensure_nl2prolog():
            threading.Thread(
                target=self._ensure_nl, daemon=True,
            ).start()

    # ------------------------------------------------------------------
    # Ленивая инициализация NLP
    # ------------------------------------------------------------------
    def _ensure_nl(self) -> None:
        """Загрузить TextToProlog и DialogTurn при первом NL-вызове."""
        if self._nl_ready:
            return
        with self._nl_lock:
            if self._nl_ready:
                return
            if not _ensure_nl2prolog():
                return
            has_agent = _ensure_agent()
            try:
                if self.t2p is None:
                    self.t2p = _TextToProlog(**self._t2p_kwargs)
                if has_agent:
                    self.dlg = _DialogTurn(
                        t2p=self.t2p, agent_factory=_Agent)
            except Exception as e:
                if self.debug:
                    print(f"[Expert] nl2prolog init: {e}")
            self._nl_ready = True

    def warmup_nl(self) -> float:
        """Явно загрузить NLP-модели. Возвращает затраченное время (с).

        Использование в UI:
            elapsed = e.warmup_nl()
            print(f"NLP loaded in {elapsed:.2f}s")
        """
        import time
        t0 = time.perf_counter()
        self._ensure_nl()
        return time.perf_counter() - t0

    # ------------------------------------------------------------------
    # Нормализация кавычек
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_query_atoms(query: str) -> str:
        """Снять кавычки с валидных атомов в Prolog-запросе.

        `'label'` → `label`, `'director'` → `director`,
        но `'петров_петр'` остаётся `'петров_петр'` (кириллица — не
        валидный атом без кавычек по _VALID_ATOM).

        Зачем: `KnowledgeGraph.to_prolog()` пишет валидные атомы без
        кавычек, а пользователь может писать `'label'` в запросе.
        PyAgentProlog сравнивает атомы по строке: `'label'` ≠ `label`.
        Нормализация выравнивает обе стороны.
        """
        if not query:
            return query
        out: List[str] = []
        i = 0
        n = len(query)
        while i < n:
            ch = query[i]
            if ch != "'":
                out.append(ch)
                i += 1
                continue
            j = i + 1
            while j < n:
                if query[j] == "\\" and j + 1 < n:
                    j += 2
                    continue
                if query[j] == "'":
                    break
                j += 1
            if j >= n:
                out.append(query[i:])
                break
            inner = query[i + 1:j]
            if (
                inner
                and _VALID_ATOM_RE.match(inner)
                and inner not in _RESERVED_ATOMS
            ):
                out.append(inner)
            else:
                out.append(query[i:j + 1])
            i = j + 1
        return "".join(out)

    # ------------------------------------------------------------------
    # Сборка программы для Agent
    # ------------------------------------------------------------------
    def _program(self) -> str:
        return (
            f"{self.graph.to_prolog()}\n"
            f"{self.rules_src}\n"
            f"{_CONVENIENCE_RULES}"
        )

    def _new_agent(self) -> Any:
        _ensure_agent()
        return _Agent(self._program(), context={})

    # ------------------------------------------------------------------
    # Prolog-запрос
    # ------------------------------------------------------------------
    def query(
        self,
        prolog: str,
        *,
        category: Optional[str] = None,
        lift: bool = True,
    ) -> QueryResult:
        original = (prolog or "").strip()
        if not original:
            return QueryResult(
                ok=False, query="", error="пустой запрос")

        if not _ensure_agent():
            return QueryResult(
                ok=False, query=original,
                error="pyagentprolog не установлен: "
                      "pip install pyagentprolog",
            )

        original = self._normalize_query_atoms(original)
        if not original.endswith("."):
            original += "."

        lifted_from: Optional[str] = None
        final = original.rstrip(".")
        if lift and category:
            lifted = lift_query(
                final, category, self._known_rules)
            if lifted != final:
                lifted_from = original
                final = lifted
        final_dot = final + "."

        try:
            agent = self._new_agent()
        except Exception as e:
            return QueryResult(
                ok=False, query=final_dot,
                error=f"agent: {e}", lifted_from=lifted_from,
            )

        sols: List[Dict[str, Any]] = []
        try:
            for item in agent.stream(final_dot):
                if isinstance(item, dict) and "error" in item:
                    return QueryResult(
                        ok=False, query=final_dot,
                        error=str(item["error"]),
                        lifted_from=lifted_from,
                    )
                if item is True:
                    return QueryResult(
                        ok=True, query=final_dot,
                        result=True, lifted_from=lifted_from,
                    )
                if item is False:
                    return QueryResult(
                        ok=True, query=final_dot,
                        result=False, lifted_from=lifted_from,
                    )
                if isinstance(item, dict):
                    sols.append(item)
                if len(sols) >= _SOLUTION_LIMIT:
                    break
        except Exception as e:
            return QueryResult(
                ok=False, query=final_dot,
                error=str(e), lifted_from=lifted_from,
            )

        deduped = _dedup_solutions(sols)
        return QueryResult(
            ok=True, query=final_dot,
            solutions=deduped,
            result=bool(deduped),
            lifted_from=lifted_from,
        )

    # ------------------------------------------------------------------
    # NL → ответ
    # ------------------------------------------------------------------
    def ask(
        self,
        nl: str,
        *,
        top_k: int = 1,
        category: Optional[str] = None,
        use_dialog: bool = True,
    ) -> ExpertAnswer:
        if not _ensure_nl2prolog():
            raise RuntimeError(
                "nl2prolog не установлен: "
                "pip install \"pyagentprolog-expert[nl]\""
            )
        self._ensure_nl()
        if not nl or not nl.strip():
            return ExpertAnswer(text="✗ Пустой вопрос.")

        query_src: str = ""
        if use_dialog and self.dlg is not None:
            try:
                result, _ = self.dlg.ask(self.graph, nl)
            except Exception as e:
                return ExpertAnswer(text=f"✗ dialog: {e}")

            if not isinstance(result, dict):
                return ExpertAnswer(
                    text="✗ dialog: неожиданный результат")
            if result.get("error"):
                return ExpertAnswer(
                    text=f"✗ dialog: {result['error']}")
            if result.get("solutions") is not None:
                return self._answer_from_solutions(result, nl)

            query_src = (result.get("query") or "").strip()
            if result.get("is_question") is False:
                facts = result.get("facts_extracted", "")
                ar = self.assert_facts_src(facts)
                text = (
                    f"✓ Утверждение принято: "
                    f"+{ar.added.get('nodes', 0)} узлов, "
                    f"+{ar.added.get('edges', 0)} рёбер, "
                    f"+{ar.added.get('attributes', 0)} атрибутов."
                )
                ans = ExpertAnswer(text=text)
                self._last_answer = ans
                return ans
        else:
            if self.t2p is None:
                return ExpertAnswer(
                    text="✗ TextToProlog недоступен")
            try:
                _, query_src = self.t2p.parse(
                    nl, strict=True,
                    facts_from_questions=False,
                )
            except Exception as e:
                return ExpertAnswer(text=f"✗ nl2prolog: {e}")

        if not query_src:
            return ExpertAnswer(
                text=("⚠️ Вопрос не распознан парсером. "
                      "Попробуйте переформулировать."),
            )

        qr = self.query(query_src, category=category)
        text = self._format_query_result(qr)
        ans = ExpertAnswer(
            text=text, query_result=qr, category=category,
        )
        self._last_answer = ans
        return ans

    def _answer_from_solutions(
        self, result: dict, nl: str,
    ) -> ExpertAnswer:
        sols = _dedup_solutions(result.get("solutions") or [])
        q = result.get("query") or ""
        qr = QueryResult(
            ok=True, query=q, solutions=sols,
            result=bool(sols),
        )
        ans = ExpertAnswer(
            text=self._format_query_result(qr), query_result=qr)
        self._last_answer = ans
        return ans

    # ------------------------------------------------------------------
    # Человекочитаемое представление — attribute(Id, 'label', L)
    # ------------------------------------------------------------------
    def _describe_identifier(self, ident: str) -> str:
        if not ident:
            return ident
        if ident in self._label_cache:
            cached = self._label_cache[ident]
            if cached:
                return cached
            return humanize_vars(ident).replace("_", " ")

        label: Optional[str] = None
        try:
            safe = str(ident).replace(
                "\\", "\\\\").replace("'", "\\'")
            qr = self.query(
                f"attribute('{safe}', label, X).", lift=False)
            if qr.ok and qr.solutions:
                raw = qr.solutions[0].get("X")
                if raw is not None and str(raw).strip():
                    label = str(raw)
        except Exception:
            label = None

        self._label_cache[ident] = label
        if label:
            return label
        return humanize_vars(ident).replace("_", " ")

    def _format_query_result(self, qr: QueryResult) -> str:
        if not qr.ok:
            return f"✗ Ошибка: {qr.error}"
        if qr.result is True and not qr.solutions:
            return "✓ Истина."
        if not qr.solutions:
            return ("Нет решений.\n"
                    "💡 Уточните вопрос или добавьте факты.")
        lines = []
        for i, sol in enumerate(qr.solutions, 1):
            parts = []
            for k, v in sol.items():
                if isinstance(v, str):
                    v = self._describe_identifier(v)
                parts.append(f"{k} = {v}")
            lines.append(f"[{i}] " + ", ".join(parts))
        head = (
            f"✓ {qr.count} решение(й):" if qr.count > 1
            else "✓ Решение:"
        )
        return head + "\n" + "\n".join(lines)

    # ------------------------------------------------------------------
    # NL-утверждение → граф
    # ------------------------------------------------------------------
    def assert_nl(self, nl: str) -> AssertResult:
        if not _ensure_nl2prolog():
            raise RuntimeError(
                "nl2prolog не установлен: "
                "pip install \"pyagentprolog-expert[nl]\""
            )
        self._ensure_nl()
        if not nl or not nl.strip():
            return AssertResult(
                ok=False, facts_src="", error="пустой ввод")
        if self.t2p is None:
            return AssertResult(
                ok=False, facts_src="",
                error="TextToProlog недоступен")
        try:
            facts_src, _ = self.t2p.parse(
                nl, strict=True, facts_from_questions=True)
        except Exception as e:
            return AssertResult(
                ok=False, facts_src="", error=str(e))
        return self.assert_facts_src(facts_src)

    def assert_facts_src(self, facts_src: str) -> AssertResult:
        if not facts_src or not facts_src.strip():
            return AssertResult(
                ok=True, facts_src="",
                added={"nodes": 0, "edges": 0, "attributes": 0},
            )
        try:
            other = KnowledgeGraph.from_prolog(facts_src)
        except Exception as e:
            return AssertResult(
                ok=False, facts_src=facts_src, error=str(e))
        stats = self.graph.merge(other)
        return AssertResult(
            ok=True, facts_src=facts_src,
            added={
                "nodes": stats["added_nodes"],
                "edges": stats["added_edges"],
                "attributes": stats["added_attributes"],
            },
        )

    # ------------------------------------------------------------------
    # Интерактивный опрос
    # ------------------------------------------------------------------
    def ask_interactive(self, nl, *, top_k=3, max_turns=10):
        if not _ensure_nl2prolog():
            raise RuntimeError(
                "nl2prolog не установлен: "
                "pip install \"pyagentprolog-expert[nl]\"")
        self._ensure_nl()

        ans = self.ask(nl, top_k=top_k, use_dialog=False)
        ans_text = ans.text
        if ans.query_result and ans.query_result.result:
            return ans_text
        if isinstance(self.session, NullSession):
            return ans_text

        for _ in range(max_turns):
            missing = self._missing_conditions()
            if not missing:
                if ans.query_result is None:
                    return (
                        f"{ans_text}\n\n"
                        "ℹ️ NL-парсер не распознал фразу как вопрос. "
                        "Все условия решения уже выполнены. "
                        "Попробуйте задать прямой вопрос, например: "
                        "«Кто директор технопарка Тюмень?»."
                    )
                return ans_text

            reply = self.session.ask_user(missing[0])
            if reply is None:
                return ans_text

            r = self.assert_nl(reply)
            added_any = (
                r.added.get("edges", 0)
                + r.added.get("nodes", 0)
                + r.added.get("attributes", 0)
            ) > 0

            if not added_any and self._last_missing_inner:
                reply_low = reply.strip().lower()
                if reply_low in ("да", "yes", "верно", "true", "1"):
                    self._add_triplet_fallback(
                        self._last_missing_inner)
                    added_any = True

            if added_any:
                ans = self.ask(nl, top_k=top_k, use_dialog=False)
                if ans.query_result and ans.query_result.result:
                    return ans.text
                ans_text = ans.text

        return ans_text

    def _add_triplet_fallback(self, inner: str) -> None:
        """Fallback: добавить triplet/attr/fact в граф.

        `inner` может быть в кавычках или без — pyagentprolog через
        `findall` возвращает строки без кавычек.
        """
        inner = inner.strip()
        m = _TRIPLET_RE.match(inner)
        if m:
            pred, s, o = m.groups()
            self.assert_facts_src(
                f"edge('{s}', '{o}', '{pred}').\n")
            return
        m = _ATTR_RE.match(inner)
        if m:
            entity, attr = m.groups()
            self.assert_facts_src(
                f"attribute('{entity}', '{attr}', 'true').\n")
            return
        m = _FACT_RE.match(inner)
        if m:
            self.assert_facts_src(
                f"node('{m.group(1)}', [], concept).\n")

    def _missing_conditions(self) -> List[str]:
        """Невыполненные условия из solution/1-СХЕМЫ в rules.pl.

        Данные solution — node(S, [], solution) и рёбра
        edge(S, Target, 'target'), edge(S, Person, 'director')
        в graph.pl. Здесь только схема-обёртка.
        """
        if not self.rules_src:
            return []
        qr = self.query(
            "findall(C, (solution(_), condition(C)), Cs).")
        if not qr.ok or not qr.solutions:
            return []
        conds = qr.solutions[0].get("Cs")
        if not isinstance(conds, list):
            return []
        missing: List[str] = []
        self._last_missing_inner = None
        for c in conds:
            inner = self._strip_condition(str(c))
            if not inner:
                continue
            check = self.query(f"condition_check({inner}).")
            if not check.result:
                if self._last_missing_inner is None:
                    self._last_missing_inner = inner
                missing.append(self._condition_to_nl(inner))
        return missing

    @staticmethod
    def _strip_condition(c: str) -> Optional[str]:
        """Достать аргумент условия.

        `findall(C, condition(C), Cs)` возвращает уже РАЗВЁРНУТЫЙ аргумент
        (`triplet(...)`, `attr(...)`, `fact(...)`), а не `condition(...)`.
        Поэтому обрабатываем оба варианта.
        """
        c = c.strip()
        for prefix in ("condition(", "not_condition("):
            if c.startswith(prefix) and c.endswith(")"):
                return c[len(prefix):-1].strip()
        # Уже развёрнуто findall'ом
        if c.startswith(("triplet(", "attr(", "fact(")) and c.endswith(")"):
            return c
        return None

    def _condition_to_nl(self, inner: str) -> str:
        """NL-шаблон для доопроса. Домен-нейтральный."""
        inner = inner.strip()
        m = _TRIPLET_RE.match(inner)
        if m:
            pred, s, o = m.groups()
            return (
                f"Верно ли, что «{self._describe_identifier(s)}» "
                f"— {pred} «{self._describe_identifier(o)}»?"
            )
        m = _ATTR_RE.match(inner)
        if m:
            entity, attr = m.groups()
            return (
                f"Верно ли, что у "
                f"«{self._describe_identifier(entity)}» "
                f"есть «{attr}»?"
            )
        m = _FACT_RE.match(inner)
        if m:
            return f"Верно ли, что «{m.group(1)}»?"
        return f"Верно ли, что {inner}?"

    # ------------------------------------------------------------------
    # why()
    # ------------------------------------------------------------------
    def why(self) -> str:
        if self._last_answer is None:
            return ("Пока нет ни одного ответа. "
                    "Задайте вопрос эксперту.")
        ans = self._last_answer
        qr = ans.query_result
        lines: List[str] = []
        if qr is not None:
            lines.append(f"Запрос: {qr.query}")
            if qr.lifted_from:
                lines.append(f"Исходный (L1): {qr.lifted_from}")
                lines.append(
                    f"Применён query-lifting → "
                    f"{qr.query.strip()}")
            if qr.error:
                lines.append(f"Ошибка: {qr.error}")
            elif qr.result is True:
                lines.append("Результат: истина")
            elif qr.result is False:
                lines.append("Результат: ложь")
            else:
                lines.append(f"Решений: {qr.count}")
            for i, s in enumerate(qr.solutions[:10], 1):
                parts = []
                for k, v in s.items():
                    if isinstance(v, str):
                        v = self._describe_identifier(v)
                    parts.append(f"{k}={v}")
                lines.append(f"  [{i}] " + ", ".join(parts))
        if ans.category:
            lines.append(f"Категория: {ans.category}")
        lines.append("")
        lines.append("Источники истины:")
        lines.append(f"  • граф: {self.graph.summary()}")
        lines.append(
            f"  • rules.pl: "
            f"{'загружен' if self.rules_src else 'пуст'}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Semantic
    # ------------------------------------------------------------------
    def enable_semantic(
        self, config: Optional[dict] = None,
    ) -> bool:
        try:
            import prolog.embedding_unify as eu
        except ImportError:
            return False
        cfg = config or {}
        try:
            eu.semantic_on(
                backend=cfg.get("backend", "st"),
                model=cfg.get("model"),
                threshold=cfg.get("threshold", 0.75),
                local_dir=cfg.get("local_dir"),
                st_device=cfg.get("st_device"),
                st_verbose=cfg.get("st_verbose", False),
                text_prefix=cfg.get("text_prefix"),
            )
            self._semantic_active = True
            return True
        except Exception as e:
            if self.debug:
                print(f"[SEMANTIC] {e}")
            self._semantic_active = False
            return False

    def disable_semantic(self) -> None:
        try:
            import prolog.embedding_unify as eu
            eu.semantic_off()
        except Exception:
            pass
        self._semantic_active = False

    def semantic_status(self) -> dict:
        try:
            import prolog.embedding_unify as eu
        except ImportError:
            return {
                "enabled": False, "available": False,
                "reason": "prolog.embedding_unify недоступен",
            }
        if not self._semantic_active:
            return {"enabled": False, "available": True}
        u = eu.semantic_get_unifier()
        if u is None:
            return {"enabled": False, "available": True}
        return {
            "enabled": True, "available": True,
            "backend": getattr(u, "backend", None),
            "threshold": getattr(u, "threshold", None),
            "stats": dict(getattr(u, "stats", {})),
        }

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self._last_answer = None
        self._last_missing_inner = None
        self._label_cache.clear()
        if self.dlg is not None:
            with contextlib.suppress(Exception):
                self.dlg.reset()


__all__ = [
    "AssertResult",
    "Expert",
    "ExpertAnswer",
    "QueryResult",
]