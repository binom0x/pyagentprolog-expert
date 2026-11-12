"""Expert — экспертная система на графе знаний.

PyAgentProlog (Agent) — движок вывода.
nl2prolog (TextToProlog, DialogTurn) — NL→query и NL→facts (опция).
Встроенный KnowledgeGraph — источник фактов.

Формат KB — граф знаний:
    node(Id, Props, Type).
    edge(Source, Target, Predicate).
    attribute(Entity, Name, Value).

Правила предметной области (Horn-клаузы: located_in/2, solution/1,
human_readable/2) хранятся в rules.pl и подгружаются в Agent на каждый
запрос вместе с _CONVENIENCE_RULES. KnowledgeGraph их не видит.

Схема vs данные:
  * graph.pl   — ДАННЫЕ: конкретные сущности, их связи и свойства
                 (в т.ч. attribute(Id, 'label', L), edge(S, F, 'alias_of'),
                 node(S, [], solution) + рёбра solution).
  * rules.pl   — СХЕМА: как связывать факты (located_in/2,
                 human_readable/2, alias/2, solution/1/condition/1).
Expert не знает ни одной сущности домена в коде.
"""
from __future__ import annotations

import contextlib
import re
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

try:
    from prolog.agent import Agent
    _AGENT_OK = True
except ImportError:
    Agent = None
    _AGENT_OK = False

try:
    from nl2prolog import DialogTurn, TextToProlog
    _NL2PROLOG_OK = True
except ImportError:
    TextToProlog = None
    DialogTurn = None
    _NL2PROLOG_OK = False


_CONVENIENCE_RULES = """
% --- convenience rules (added by Expert) ---
node(Id, Type) :- node(Id, _, Type).
edge(S, T) :- edge(S, T, _).
"""

_SOLUTION_LIMIT = 1000


# Валидный атом — совпадает с graph._VALID_ATOM и _RESERVED_ATOMS.
# Используется в _normalize_query_atoms для снятия кавычек.
_VALID_ATOM_RE = re.compile(r"^[a-z][A-Za-z0-9_]*$")
_RESERVED_ATOMS = {"is", "mod", "div", "rem", "xor", "not"}


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


def _require(cond: bool, pkg: str, hint: str) -> None:
    if not cond:
        raise RuntimeError(f"{pkg} не установлен: {hint}")

def _dedup_solutions(sols: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Убрать полные дубликаты (одинаковые биндинги)."""
    seen: set[tuple] = set()
    out: List[Dict[str, Any]] = []
    for s in sols:
        key = tuple(sorted(
            (k, str(v)) for k, v in s.items()
        ))
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


class Expert:
    def __init__(
        self,
        graph: Optional[KnowledgeGraph] = None,
        rules_file: Optional[str] = None,
        t2p: Optional[Any] = None,
        debug: bool = False,
        semantic: bool = False,
        semantic_config: Optional[dict] = None,
        session: Optional[Session] = None,
    ) -> None:
        _require(_AGENT_OK, "pyagentprolog", "pip install pyagentprolog")

        self.graph = graph if graph is not None else KnowledgeGraph()
        self.debug = debug
        self.session = session or NullSession()

        self.rules_src = self._normalize_query_atoms(
            load_rules(rules_file))
        self._known_rules = discover_rule_predicates(self.rules_src)

        # Кэш человекочитаемых label'ов — по сущности.
        # Заполняется через attribute(Id, 'label', L) из графа.
        # Fallback — humanize_vars(Id).replace('_', ' ').
        self._label_cache: Dict[str, Optional[str]] = {}

        # NL-парсер и диалог — опциональны
        self.t2p = t2p
        self.dlg = None
        if _NL2PROLOG_OK:
            try:
                self.t2p = self.t2p or TextToProlog()
                self.dlg = DialogTurn(t2p=self.t2p, agent_factory=Agent)
            except Exception as e:
                if self.debug:
                    print(f"[Expert] nl2prolog init: {e}")

        self._last_answer: Optional[ExpertAnswer] = None
        self._semantic_active = False
        if semantic:
            self.enable_semantic(semantic_config or {})

    # ------------------------------------------------------------------
    # Нормализация кавычек в запросе
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_query_atoms(query: str) -> str:
        """Снять кавычки с валидных атомов в Prolog-запросе.

        `'label'` → `label`, `'director'` → `director`,
        но `'петров_петр'` остаётся `'петров_петр'` (кириллица — не
        валидный атом без кавычек по _VALID_ATOM).

        Зачем: `KnowledgeGraph.to_prolog()` пишет валидные атомы без
        кавычек (`attribute('петров_петр', label, 'Петров Пётр')`),
        а пользователь может писать `attribute('петров_петр', 'label', L)`.
        PyAgentProlog сравнивает атомы по строке: `'label'` ≠ `label` —
        и запрос не находит факт. Нормализация выравнивает обе стороны.
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
            # Одиночная кавычка — ищем закрывающую с учётом экранирования
            j = i + 1
            while j < n:
                if query[j] == "\\" and j + 1 < n:
                    j += 2
                    continue
                if query[j] == "'":
                    break
                j += 1
            if j >= n:
                # Незакрытая кавычка — оставляем как есть
                out.append(query[i:])
                break
            inner = query[i + 1:j]
            if (
                inner
                and _VALID_ATOM_RE.match(inner)
                and inner not in _RESERVED_ATOMS
            ):
                out.append(inner)          # снимаем кавычки
            else:
                out.append(query[i:j + 1])  # оставляем как есть
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
        return Agent(self._program(), context={})

    # ------------------------------------------------------------------
    # Низкоуровневый Prolog-запрос
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
            return QueryResult(ok=False, query="", error="пустой запрос")

        # Нормализация кавычек ДО лифтинга и передачи в Agent:
        # `attribute('x', 'label', L)` → `attribute('x', label, L)`.
        # Кириллица остаётся в кавычках.
        original = self._normalize_query_atoms(original)

        if not original.endswith("."):
            original += "."

        lifted_from: Optional[str] = None
        final = original.rstrip(".")
        if lift and category:
            lifted = lift_query(final, category, self._known_rules)
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

        return QueryResult(
            ok=True, query=final_dot,
            solutions=_dedup_solutions(sols),
            result=bool(sols),
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
        _require(_NL2PROLOG_OK, "nl2prolog",
                 "pip install \"pyagentprolog-expert[nl]\"")
        assert self.t2p is not None
        if not nl or not nl.strip():
            return ExpertAnswer(text="✗ Пустой вопрос.")

        query_src: str = ""
        if use_dialog and self.dlg is not None:
            try:
                result, _ = self.dlg.ask(self.graph, nl)
            except Exception as e:
                return ExpertAnswer(text=f"✗ dialog: {e}")

            if not isinstance(result, dict):
                return ExpertAnswer(text="✗ dialog: неожиданный результат")
            if result.get("error"):
                return ExpertAnswer(text=f"✗ dialog: {result['error']}")
            if result.get("solutions") is not None:
                return self._answer_from_solutions(result, nl)

            query_src = (result.get("query") or "").strip()
            if result.get("is_question") is False:
                facts = result.get("facts_extracted", "")
                ar = self.assert_facts_src(facts)
                text = (
                    f"✓ Утверждение принято: +{ar.added.get('nodes', 0)} "
                    f"узлов, +{ar.added.get('edges', 0)} рёбер, "
                    f"+{ar.added.get('attributes', 0)} атрибутов."
                )
                return ExpertAnswer(text=text)
        else:
            try:
                _, query_src = self.t2p.parse(
                    nl, strict=True, facts_from_questions=False)
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
        sols = result.get("solutions") or []
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
    # Человекочитаемое представление — через attribute/3 графа
    # ------------------------------------------------------------------
    def _describe_identifier(self, ident: str) -> str:
        """Человекочитаемое имя для идентификатора.

        Стратегия (в порядке приоритета):
          1. attribute(Id, 'label', L) из графа — данные домена,
             редактируются в kg-editor, приходят из graph.pl.
          2. humanize_vars(Id) — снять _<N>-суффикс PyAgentProlog.
          3. Заменить '_' на пробел.

        Никаких human_readable/2-фактов в rules.pl — там только
        СХЕМА `human_readable(I, L) :- attribute(I, 'label', L).`
        """
        if not ident:
            return ident
        if ident in self._label_cache:
            cached = self._label_cache[ident]
            if cached:
                return cached
            return humanize_vars(ident).replace("_", " ")

        # 1) attribute(Id, 'label', L) — данные графа.
        # query() сам нормализует `'label'` → `label`, что нужно,
        # чтобы совпасть с сериализацией graph.to_prolog().
        label: Optional[str] = None
        try:
            # Экранируем одинарные кавычки в идентификаторе
            safe = str(ident).replace("\\", "\\\\").replace("'", "\\'")
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
        # 2) fallback: humanize + подчёркивания → пробелы
        return humanize_vars(ident).replace("_", " ")

    def _format_query_result(self, qr: QueryResult) -> str:
        if not qr.ok:
            return f"✗ Ошибка: {qr.error}"
        if qr.result is True and not qr.solutions:
            return "✓ Истина."
        if not qr.solutions:
            return "Нет решений.\n💡 Уточните вопрос или добавьте факты."
        lines = []
        for i, sol in enumerate(qr.solutions, 1):
            parts = []
            for k, v in sol.items():
                if isinstance(v, str):
                    # человекочитаемое имя через attribute(…,'label',…)
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
        _require(_NL2PROLOG_OK, "nl2prolog",
                 "pip install \"pyagentprolog-expert[nl]\"")
        assert self.t2p is not None
        if not nl or not nl.strip():
            return AssertResult(
                ok=False, facts_src="", error="пустой ввод")
        try:
            facts_src, _ = self.t2p.parse(
                nl, strict=True, facts_from_questions=True)
        except Exception as e:
            return AssertResult(ok=False, facts_src="", error=str(e))
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
            return AssertResult(ok=False, facts_src=facts_src, error=str(e))
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
    # Интерактивный опрос (аналог старого backward-chaining loop)
    # ------------------------------------------------------------------
    def ask_interactive(
        self,
        nl: str,
        *,
        top_k: int = 3,
        max_turns: int = 10,
    ) -> str:
        if isinstance(self.session, NullSession):
            return self.ask(nl, top_k=top_k).text
        ans_text = ""
        for _ in range(max_turns):
            ans = self.ask(nl, top_k=top_k)
            ans_text = ans.text
            if ans.query_result and ans.query_result.result:
                return ans.text
            missing = self._missing_conditions()
            if not missing:
                return ans.text
            for cond_nl in missing:
                reply = self.session.ask_user(cond_nl)
                if reply is None:
                    return ans.text
                self.assert_nl(reply)
        return ans_text

    def _missing_conditions(self) -> List[str]:
        """Собрать невыполненные условия из solution/1-СХЕМЫ в rules.pl.

        Данные solution — узлы node(S, [], solution) и рёбра
        edge(S, Target, 'target'), edge(S, Person, 'director')
        в graph.pl. Здесь — только СХЕМА-обёртка.
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
        for c in conds:
            c_str = str(c)
            inner = self._strip_condition(c_str)
            if not inner:
                continue
            check = self.query(f"condition_check({inner}).")
            if not check.result:
                missing.append(self._condition_to_nl(inner))
        return missing

    @staticmethod
    def _strip_condition(c: str) -> Optional[str]:
        for prefix in ("condition(", "not_condition("):
            if c.startswith(prefix) and c.endswith(")"):
                return c[len(prefix):-1]
        return None

    def _condition_to_nl(self, inner: str) -> str:
        """Очень простой NL-шаблон для доопроса. Домен-нейтральный."""
        return f"Верно ли, что {inner.replace('_', ' ')}?"

    # ------------------------------------------------------------------
    # why()
    # ------------------------------------------------------------------
    def why(self) -> str:
        if self._last_answer is None:
            return "Пока нет ни одного ответа. Задайте вопрос эксперту."
        ans = self._last_answer
        qr = ans.query_result
        lines: List[str] = []
        if qr is not None:
            lines.append(f"Запрос: {qr.query}")
            if qr.lifted_from:
                lines.append(f"Исходный (L1): {qr.lifted_from}")
                lines.append(
                    f"Применён query-lifting → {qr.query.strip()}")
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
            f"  • rules.pl: {'загружен' if self.rules_src else 'пуст'}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Semantic (совместимость со старым Expert)
    # ------------------------------------------------------------------
    def enable_semantic(self, config: Optional[dict] = None) -> bool:
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
