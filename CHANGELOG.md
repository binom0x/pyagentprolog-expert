- Команды: `!!why`, `!!assert`, `!!graph`, `!!rules`, `!!reset`,
`!!quit` / `!!exit` / `:q`.
- `!!assert` требует `[nl]`; остальные команды работают без него.

#### Примеры и данные
- `rules.pl.example` — **только схема** (см. §Design ниже):
`located_in/2`, `techpark_in_russia/1`, `alias/2`,
`human_readable/2`, `solution/1` + `condition/1`,
`without_director/1`.
- `py.typed` — маркер PEP 561 (аннотации типов).

#### Тесты
- `tests/test_graph.py` — встроенный `KnowledgeGraph`: CRUD, merge,
`from_prolog`/`to_prolog`, `generic_filter`, roundtrip.
- `tests/test_expert_basic.py` — `query`, `why`, `label` через
`attribute/3`, `human_readable/2`/`alias/2`/`solution/1` как схемы,
fallback `_describe_identifier`.
- `tests/test_lifting.py` — лифтинг `transitive`, gating по
`discover_rule_predicates`, отключение без `category`.
- `tests/test_assert.py` — `assert_facts_src`, идемпотентность,
игнорирование правил, `label` как `attribute/3`, `alias_of` как ребро.
- `tests/test_humanize.py` — снятие `_<N>`-суффиксов.
- `tests/test_rules_engine.py` — `load_rules`, `discover_rule_predicates`,
`lift_query` (с gating и без).
- `tests/test_cli.py` — `pa-expert --help`, `!!quit`.
- `tests/test_kg_editor_compat.py` — **опционально**:
`pytest.importorskip("kg_editor")`, проверка duck-typing-совместимости.
CI его не требует.
- `tests/test_no_domain_in_rules.py` — **контракт**: `rules.pl` не
содержит доменных фактов (`human_readable/2`, `alias/2`, `solution/1`
без `:-`); имена сущностей — только в `graph.pl`.

#### CI
- `.github/workflows/ci.yml` — матрица `os × python × extras`,
отдельные job'ы:
- `test` (`extras=nl`, `extras=all`) — полный набор, кроме slow
  и `kg_editor`;
- `test_core_only` (`[dev]` без `[nl]`) — core работает без NL;
- `test_with_kg_editor` (`continue-on-error: true`) — compat-тесты,
  если `kg-editor` случайно установлен;
- `build` — `python -m build` + `twine check`.

### Added

- `Expert._normalize_query_atoms(query)` — снятие кавычек с валидных
  атомов в Prolog-запросе (и в `rules.pl` при загрузке). Кириллица
  остаётся в кавычках — как в `KnowledgeGraph.to_prolog()`.

### Changed

- `Expert._describe_identifier()` читает `attribute(Id, 'label', L)`
из графа, а не `human_readable/2`-факты из `rules.pl`. Fallback —
`humanize_vars(Id).replace('_', ' ')`.
- `Expert._format_query_result()` подставляет `label` в solutions
через `_describe_identifier` — `text` в `ExpertAnswer` показывает
`Петров Пётр`, а не `петров_петр`.
- `Expert.why()` использует тот же `_describe_identifier` для биндингов.
- `rules.pl.example` содержит **только схему**:
- `human_readable(Id, Label) :- attribute(Id, 'label', Label).`
- `alias(Short, Full) :- edge(Short, Full, 'alias_of').`
- `solution(S) :- node(S, _, solution).`
- `condition(triplet('директор', P, Org)) :- edge(S, Org, 'target'),
  edge(S, P, 'director'), solution(S).`
Доменные факты (`label`, `alias`, `solution`-узлы) — в `graph.pl`.
- `_hr_cache` переименован в `_label_cache` — точнее отражает
семантику (кэш `label`, а не `human_readable/2`).

### Removed

- `kg-editor` из `dependencies` и `optional-dependencies`.
**`kg-editor` не является зависимостью** пакета — ни обязательной,
ни опциональной. Связь с редактором — только через файл `graph.pl`.
- `[kg-editor]` extra.
- `kg-editor` из `[all]` extra.
- Жёсткий импорт `from kg_editor.graph_model import KnowledgeGraph`
в `expert.py`, `cli.py`, `graph.py`.
- Проверка `_KG_OK` в `Expert.__init__` — `KnowledgeGraph` встроен.

### Fixed

- `Expert` больше не падает с `ImportError`, если `kg-editor`
не установлен.
- `Expert._describe_identifier()` не делает лишних запросов
`human_readable/2` — читает `attribute/3` с кэшем.
- `test_no_domain_in_rules.py` гарантирует, что доменные данные
не «просочатся» в `rules.pl` при будущих правках.
- **`_normalize_query_atoms`** — снятие кавычек с валидных атомов
  (`'label'` → `label`, `'alias_of'` → `alias_of`) в `query()` **и**
  в `rules_src` при загрузке. Без этого `human_readable/2`, `alias/2`,
  `condition/1` не срабатывали: `'alias_of'` в `rules.pl` ≠ `alias_of`
  в `graph.to_prolog()`. Кириллица (`'петров_петр'`, `'находиться_в'`)
  остаётся в кавычках.
- **CLI на Windows** — `sys.stdout.reconfigure(encoding="utf-8")`
  в `cli.py::main`, чтобы `--help` и ответы с кириллицей не падали
  с `UnicodeEncodeError` на `cp1251`.
- **`tests/test_cli.py`** — `subprocess.run(..., encoding="utf-8",
  input=str)` вместо `text=True` + `input=bytes`. На Windows
  `text=True` декодирует `cp1252`; `input=bytes` при `encoding=` даёт
  `TypeError: write() argument must be str, not bytes`.
- **`tests/test_graph.py::test_from_prolog_roundtrip`** — сравнение
  `from_prolog(to_prolog(from_prolog(src)))` с `from_prolog(src)`,
  а не `to_prolog == src`: `from_prolog` авто-создаёт узлы для `edge/3`.
- **`tests/test_graph.py::test_merge_additive`** — `skipped_nodes=2`
  (a и b авто-созданы в обоих графах), а не 1.
- **`tests/test_lifting.py::test_lift_transitive`** — проверка
  `{казань, россия}` в решениях, а не позиции `solutions[0]`
  (порядок `located_in/2` — прямой факт, потом транзитивный).

### Security

- Изменений нет. Замечания:
- `Expert` не выполняет непроверенный код из `graph.pl`/`rules.pl`
  вне `Agent` (PyAgentProlog).
- `Session` не даёт доступа к файловой системе/сети — только
  очереди ввода/вывода.
- `pa-expert` читает только файлы, переданные через `--graph`/`--rules`.

### Deprecated

- Нет. Первый релиз — публичного API для депрекации ещё нет.

---

## Design — обоснование ключевых решений

Раздел фиксирует архитектурные принципы, чтобы будущие изменения
не нарушили контракт.

### `kg-editor` не зависимость

| Было (ранее в разработке) | Стало |
|---|---|
| `kg-editor` в `dependencies` | нет |
| `[kg-editor]` extra | нет |
| `kg-editor` в `[all]` | нет |
| `from kg_editor.graph_model import KnowledgeGraph` | `from .graph import KnowledgeGraph` |

**Почему:** в продакшене экспертная система работает с готовым
`graph.pl`, редактора там нет. Связь редактор ↔ эксперт — **через файл**,
не через импорт Python-модуля.

**Совместимость с `kg_editor.KnowledgeGraph` — бесплатно, через
duck-typing:** `Expert` вызывает только `graph.to_prolog()` и
`graph.merge(other)`. Если у пользователя уже есть `kg_editor`-граф —
он передаётся в `Expert(graph=...)` без установки пакета.

### `nl2prolog` — опция (`[nl]`)

| API | Без `[nl]` | С `[nl]` |
|---|---|---|
| `Expert.query(...)` | ✅ | ✅ |
| `Expert.query(..., category=...)` | ✅ | ✅ |
| `Expert.assert_facts_src(...)` | ✅ | ✅ |
| `Expert.why()` | ✅ | ✅ |
| `Expert.ask(...)` | ❌ `RuntimeError` | ✅ |
| `Expert.assert_nl(...)` | ❌ `RuntimeError` | ✅ |
| `Expert.ask_interactive(...)` | ❌ `RuntimeError` | ✅ |
| CLI `pa-expert` (кроме `!!assert`) | ✅ | ✅ |

**Почему:** `query`/`assert_facts_src` — «чистый Prolog поверх графа
и правил», не требуют NL-парсера. `nl2prolog` — тяжёлая зависимость
(natasha, pymorphy3), её отсутствие не должно блокировать базовый
сценарий.

### Схема vs данные

| Что | Где | Пример |
|---|---|---|
| Факты о сущностях | `graph.pl` | `node/3`, `edge/3`, `attribute/3` |
| `label` сущности | `graph.pl` | `attribute('петров_петр', 'label', 'Петров Пётр')` |
| `alias` short→full | `graph.pl` | `edge('петров', 'петров_петр', 'alias_of')` |
| `solution`-узлы | `graph.pl` | `node('назначить_петрова', [], solution)` + рёбра |
| Правила вывода | `rules.pl` | `located_in/2`, `techpark_in_russia/1` |
| Схемы `alias/2`, `human_readable/2`, `solution/1` | `rules.pl` | правила-обёртки над `attribute/3`, `edge/3`, `node/3` |
| Словарь типов/предикатов (опционально) | `schema.pl` | `valid_node_type/1`, `valid_edge_predicate/1` |

**Почему:** если знание — это факт о конкретной сущности, оно в
`graph.pl` (редактируется в `kg-editor`, приходит из NL-импорта).
Если правило применимо к любой сущности — оно в `rules.pl`.
`Expert` в коде не знает ни одной сущности домена.

Принцип из §9.1 «Документации nl2prolog»: *«если знание можно записать
как факт `kb.pl`, как алиас в KB, или как контекст в `dialog.py` —
оно не должно быть в `text_to_prolog.py`»*. То же верно для `Expert`.

### Свежий `Agent` на каждый запрос

**Почему:** мутации (`assertz`/`retract`) внутри `Agent` живут только
в рамках одного запроса. Источник истины — `Expert.graph`. `assert_nl` /
`assert_facts_src` идут через `KnowledgeGraph.merge`, следующий `ask` /
`query` увидит изменения, потому что `_new_agent()` перечитывает
`graph.to_prolog()`.

### Query-lifting с gating

`lift_query` лифтит L1→L2/L3 **только если** целевой предикат определён
в `rules.pl` (проверка через `discover_rule_predicates`). Иначе запрос
остаётся L1 — и `Agent` вернёт решения по фактам графа, а не пустоту
по несуществующему предикату.

---

## Совместимость версий

| Версия `pyagentprolog-expert` | Python | `pyagentprolog` | `nl2prolog` (опция) | `kg-editor` |
|---|---|---|---|---|
| 1.0.x | 3.10–3.12 | >=1.0.1 | >=1.0.2 (`[nl]`) | **не требуется** |

### Гарантии публичного API (SemVer)

- **`__version__`** — строго SemVer.
- **`Expert`** — публичные методы (`ask`, `query`, `assert_nl`,
`assert_facts_src`, `ask_interactive`, `why`, `reset`,
`enable_semantic`, `disable_semantic`, `semantic_status`) не удаляются
и не меняют сигнатуры без major-bump.
- **`KnowledgeGraph`** — API (`add_*`, `remove_*`, `merge*`,
`to_prolog`, `from_prolog`, `summary`) стабилен; расширяется только
добавлением.
- **`QueryResult` / `AssertResult` / `ExpertAnswer`** — новые поля
только с дефолтами (обратная совместимость по `dataclass`).
- **Формат `graph.pl`** — `node/3`, `edge/3`, `attribute/3` стабилен;
расширения — только через новые предикаты (см. «Формат графа знаний
на Prolog» §7).
- **CLI `pa-expert`** — команды не переименовываются; новые —
добавляются.

---

## Ссылки

- [README.md](README.md) — руководство пользователя и API.
- [Документация пакета nl2prolog](../nl2prolog/README.md) — NL-парсер.
- [Полное руководство по PyAgentProlog](../pyagentprolog/README.md) —
движок вывода.
- [Формат графа знаний на Prolog](../kg-editor/docs/format.md) —
контракт формата.
- [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
- [Semantic Versioning](https://semver.org/).

---

[Unreleased]: https://github.com/andrey-vorfolomeev/pyagentprolog-expert/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/andrey-vorfolomeev/pyagentprolog-expert/releases/tag/v0.1.0