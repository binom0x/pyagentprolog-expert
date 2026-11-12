# pyagentprolog-expert

Экспертная система на графе знаний:
**PyAgentProlog** (движок вывода) + **nl2prolog** (NL→query и NL→facts, опция).
**`kg-editor` не требуется** — `KnowledgeGraph` встроен в пакет.

- База знаний — граф знаний в формате Prolog: `node/3`, `edge/3`, `attribute/3`.
- Правила предметной области (`located_in/2`, `solution/1`, `human_readable/2` …)
  хранятся отдельно в `rules.pl` и не попадают в граф.
- NL-вопросы и NL-утверждения — через `nl2prolog` (опциональная зависимость).
- Низкоуровневый Prolog-запрос (`Expert.query`) работает **без** `nl2prolog`.
- Совместимость с `kg_editor.KnowledgeGraph` — бесплатно, через duck-typing;
  сам `kg-editor` в зависимостях **не** указан.

---

## Содержание

1. [Установка](#1-установка)
2. [Зависимости](#2-зависимости)
3. [Быстрый старт](#3-быстрый-старт)
4. [Формат базы знаний](#4-формат-базы-знаний)
5. [Публичный API](#5-публичный-api)
6. [Query-lifting](#6-query-lifting)
7. [Диалоговый режим и coref](#7-диалоговый-режим-и-coref)
8. [Семантическая унификация](#8-семантическая-унификация)
9. [CLI](#9-cli)
10. [Совместимость с kg-editor](#10-совместимость-с-kg-editor)
11. [Архитектура](#11-архитектура)
12. [Расширение](#12-расширение)
13. [Диагностика](#13-диагностика)
14. [Разработка](#14-разработка)
15. [Лицензия](#15-лицензия)

---

## 1. Установка

### Продакшен (только эксперт)

```bash
pip install pyagentprolog-expert           # core: query / assert_facts_src
pip install "pyagentprolog-expert[nl]"     # + ask() / assert_nl()
pip install "pyagentprolog-expert[all]"    # + semantic
```

`kg-editor` **не устанавливается** — связь с редактором идёт через файл
`graph.pl` (редактор сохраняет → эксперт читает). См. §10.

### Из исходников

```bash
git clone https://github.com/andrey-vorfolomeev/pyagentprolog-expert.git
cd pyagentprolog-expert
pip install -e ".[nl,dev]"
```

### Требования

- Python 3.10+
- `pyagentprolog` (устанавливается автоматически)
- `nl2prolog` — опционально (`[nl]`)
- `sentence-transformers` — опционально (`[semantic]`)

---

## 2. Зависимости

| Пакет | Обязателен | Что даёт |
|---|---|---|
| `pyagentprolog` | **да** | `Agent`, `stream` — движок вывода |
| `nl2prolog` | опция (`[nl]`) | `TextToProlog`, `DialogTurn` → `ask()` / `assert_nl()` |
| `sentence-transformers` | опция (`[semantic]`) | семантическая унификация |

**`kg-editor` не требуется.** Экспертная система работает с готовым
`graph.pl` через встроенный `KnowledgeGraph` (см. `graph.py`).
Если у вас уже есть код на `kg_editor.KnowledgeGraph` — он подойдёт
как `graph=...` в `Expert` без установки пакета (duck-typing:
`Expert` вызывает только `graph.to_prolog()` и `graph.merge(other)`).

### Что работает без опций

| API | Без `[nl]` | С `[nl]` |
|---|---|---|
| `Expert.query(prolog)` | ✅ | ✅ |
| `Expert.query(prolog, category=...)` | ✅ | ✅ |
| `Expert.assert_facts_src(src)` | ✅ | ✅ |
| `Expert.why()` | ✅ | ✅ |
| `Expert.reset()` | ✅ | ✅ |
| `Expert.ask(nl)` | ❌ `RuntimeError` | ✅ |
| `Expert.assert_nl(nl)` | ❌ `RuntimeError` | ✅ |
| `Expert.ask_interactive(nl)` | ❌ `RuntimeError` | ✅ |
| CLI `pa-expert` (всё, кроме `!!assert`) | ✅ | ✅ |
| CLI `!!assert` | ❌ сообщение | ✅ |

---

## 3. Быстрый старт

### 3.1. Минимальный пример

```python
from pyagentprolog_expert import Expert, KnowledgeGraph

# 1. Загрузить готовый граф
g = KnowledgeGraph.from_prolog(open("graph.pl", encoding="utf-8").read())

# 2. Создать эксперта (rules.pl опционален)
e = Expert(graph=g, rules_file="rules.pl")

# 3. Prolog-запрос — работает без nl2prolog
qr = e.query("edge(X, 'технопарк_саратов', 'директор').")
print(qr.solutions)
# [{'X': 'петров_петр'}]

# 4. NL-вопрос — требует [nl]
ans = e.ask("Кто директор технопарка Саратов?")
print(ans.text)
# ✓ Решение:
# [1] X = Петров Пётр

# 5. NL-утверждение → граф (аддитивно) — требует [nl]
e.assert_nl("Илон Маск владеет Tesla")

# 6. Объяснение
print(e.why())
```

### 3.2. Создание графа с нуля

```python
from pyagentprolog_expert import Expert, KnowledgeGraph

g = KnowledgeGraph()
g.add_node("технопарк_саратов", "technopark")
g.add_node("петров_петр", "person")
g.add_edge("петров_петр", "технопарк_саратов", "директор")
g.add_attribute("технопарк_саратов", "год_основания", "2015")

e = Expert(graph=g)
print(e.query("edge('петров_петр', X, 'директор').").solutions)
# [{'X': 'технопарк_саратов'}]
```

### 3.3. Запрос с query-lifting

```python
qr = e.query(
    "edge('технопарк_казань', X, 'находиться_в')",
    category="transitive",
)
# L1: edge('технопарк_казань', X, 'находиться_в')
# L2: located_in('технопарк_казань', X)   ← применён rules.pl
print(qr.solutions)      # [{'X': 'россия'}]
print(qr.lifted_from)    # "edge('технопарк_казань', X, 'находиться_в')."
```

### 3.4. CLI

```bash
pa-expert --graph graph.pl --rules rules.pl
```

```
[pa-expert] graph: {'nodes': 2, 'edges': 1, 'attributes': 0}
[pa-expert] rules: загружен
Команды: !!why, !!assert, !!graph, !!rules, !!reset, !!quit

> Кто директор технопарка Саратов?
✓ Решение:
[1] X = Петров Пётр

> !!why
Запрос: edge(X, 'технопарк_саратов', 'директор').
Результат: истина
  [1] X=Петров Пётр

Источники истины:
  • граф: {'nodes': 2, 'edges': 1, 'attributes': 0}
  • rules.pl: загружен
```

---

## 4. Формат базы знаний

### 4.1. Граф (`graph.pl`) — источник фактов

```prolog
node(Id, Props, Type).              % узел
edge(Source, Target, Predicate).    % ребро
attribute(Entity, Name, Value).     % атрибут (value — всегда строка)
```

Пример:

```prolog
node('технопарк_саратов', [], technopark).
node('петров_петр', [], person).
node('технопарк_казань', [], technopark).
node('россия', [], place).
edge('петров_петр', 'технопарк_саратов', 'директор').
edge('технопарк_казань', 'россия', 'находиться_в').
attribute('технопарк_саратов', 'год_основания', '2015').
```

Правила сериализации (совместимы с `kg-editor` и `nl2prolog`):

- `Id`, `Type`, `Predicate`, `Name` — без кавычек, если валидный атом
  (`[a-z][A-Za-z0-9_]*`), иначе `'...'`.
- `Value` — **всегда** в одинарных кавычках, даже числа (`'2022'`).
- Compound-ID (`технопарк_саратов`) — валидный атом, идёт без кавычек.
- Кириллица, пробелы, заглавные — в кавычках.

### 4.2. Правила (`rules.pl`) — схема вывода

`rules.pl` содержит **только схему** — правила, применимые к любой
предметной области. Все доменные факты (`label`, `alias`, `solution`,
конкретные типы) — в `graph.pl`.

```prolog
% Транзитивное замыкание
located_in(X, Y) :- edge(X, Y, 'находиться_в').
located_in(X, Y) :- edge(X, Z, 'находиться_в'), located_in(Z, Y).

% Список по типу
techpark_in_russia(T) :-
    node(T, _, technopark),
    located_in(T, 'россия').

% alias/2 — СХЕМА; данные — edge(Short, Full, 'alias_of') в graph.pl
alias(Short, Full) :- edge(Short, Full, 'alias_of').

% human_readable/2 — СХЕМА; данные — attribute(Id, 'label', L) в graph.pl
human_readable(Id, Label) :- attribute(Id, 'label', Label).

% solution/1 + condition/1 — СХЕМА; данные — узлы solution + рёбра
solution(S) :- node(S, _, solution).
condition(triplet('директор', P, Org)) :-
    edge(S, Org, 'target'),
    edge(S, P, 'director'),
    solution(S).
```

**Правила не попадают в граф.** `KnowledgeGraph.from_prolog` их молча
игнорирует. `Expert` подгружает `rules.pl` в `Agent` на каждый запрос.

### 4.3. Контракт сборки программы для Agent

На каждый запрос `Expert` создаёт **свежий** `Agent` из строки:

```
graph.to_prolog()       # факты: node/3, edge/3, attribute/3
+ rules_src             # Horn-клаузы из rules.pl
+ _CONVENIENCE_RULES    # node/2, edge/2 — сокращения
```

```prolog
node(Id, Type) :- node(Id, _, Type).
edge(S, T) :- edge(S, T, _).
```

Мутации (`assertz`/`retract`) внутри запроса **не переживают** запрос и
не влияют на граф. Источник истины — `Expert.graph`.

---

## 5. Публичный API

### 5.1. `Expert`

```python
from pyagentprolog_expert import Expert

e = Expert(
    graph=None,               # KnowledgeGraph | None → пустой
    rules_file=None,          # путь к rules.pl
    t2p=None,                 # кастомный TextToProlog
    debug=False,
    semantic=False,           # включить семантику
    semantic_config=None,     # dict для enable_semantic
    session=None,             # Session | NullSession
)
```

#### `ask(nl, *, top_k=1, category=None, use_dialog=True) -> ExpertAnswer`

NL-вопрос → ответ из графа. Требует `[nl]`.

```python
ans = e.ask("Кто директор технопарка Саратов?")
print(ans.text)
# ✓ Решение:
# [1] X = Петров Пётр

# С query-lifting
ans = e.ask("В какой стране технопарк Казань?", category="transitive")
```

`use_dialog=True` использует `DialogTurn` (coref/ellipsis). Если
`use_dialog=False` — прямой `TextToProlog.parse` без состояния.

#### `query(prolog, *, category=None, lift=True) -> QueryResult`

Низкоуровневый Prolog-запрос. Работает **без** `[nl]`.

```python
qr = e.query("edge(X, 'технопарк_саратов', 'директор').")
if qr.ok:
    for sol in qr.solutions:
        print(sol["X"])

# С лифтингом
qr = e.query(
    "edge('технопарк_казань', X, 'находиться_в')",
    category="transitive",
)
print(qr.lifted_from)   # исходный L1
```

#### `assert_nl(nl) -> AssertResult`

NL-утверждение → извлечь факты → merge в граф (аддитивно). Требует `[nl]`.

```python
r = e.assert_nl("Илон Маск владеет Tesla")
print(r.ok, r.added)
# True {'nodes': 2, 'edges': 1, 'attributes': 0}
```

#### `assert_facts_src(facts_src) -> AssertResult`

Добавить Prolog-факты в граф. Работает **без** `[nl]`.

```python
r = e.assert_facts_src(
    "node('new_org', [], org).\n"
    "edge('new_org', 'технопарк_саратов', 'партнёр').\n"
)
```

#### `why() -> str`

Объяснение последнего ответа.

```python
print(e.why())
# Запрос: edge(X, 'технопарк_саратов', 'директор').
# Результат: истина
#   [1] X=Петров Пётр
#
# Источники истины:
#   • граф: {'nodes': 2, 'edges': 1, 'attributes': 0}
#   • rules.pl: загружен
```

#### `ask_interactive(nl, *, top_k=3, max_turns=10) -> str`

Цикл доопроса через `Session`. Требует `[nl]` и `Session`.

```python
from pyagentprolog_expert import Session

sess = Session()
e = Expert(graph=g, rules_file="rules.pl", session=sess)

# В UI-потоке:
sess.poll()          # читать вопросы
sess.send("да")      # отправить ответ
```

#### `reset() -> None`

Сбросить последний ответ и кэши. Граф **не** трогается.

#### Семантика

```python
e.enable_semantic({"model": "...", "threshold": 0.82})
e.disable_semantic()
print(e.semantic_status())
```

### 5.2. `KnowledgeGraph`

Полный API — в `graph.py`. Ключевое:

```python
from pyagentprolog_expert import KnowledgeGraph

g = KnowledgeGraph.from_prolog(text)
g.to_prolog()
g.add_node(id, type="concept", props=None)
g.add_edge(src, tgt, pred)
g.add_attribute(entity, name, value)
g.remove_node(id)
g.remove_edge(idx)
g.remove_attribute(idx)
g.merge(other)                  # аддитивно
g.merge_from_prolog(text)       # обёртка
g.summary()                     # {'nodes': N, 'edges': N, 'attributes': N}
```

### 5.3. Результаты

```python
@dataclass
class QueryResult:
    ok: bool
    query: str
    solutions: List[Dict[str, Any]]
    result: Optional[bool]          # True/False для ground
    error: Optional[str]
    lifted_from: Optional[str]      # исходный L1, если был лифтинг

    @property
    def count(self) -> int: ...

@dataclass
class AssertResult:
    ok: bool
    facts_src: str
    added: Dict[str, int]           # {'nodes', 'edges', 'attributes'}
    error: Optional[str]

@dataclass
class ExpertAnswer:
    text: str
    query_result: Optional[QueryResult]
    used_rules: List[str]
    category: Optional[str]
```

---

## 6. Query-lifting

`nl2prolog` эмитит **только** L1-запросы (`edge/attribute/node/alias`).
Правила предметной области (`located_in/2`, `techpark_in_russia/1`) —
уровень L2/L3. `Expert.query(category=...)` лифтит L1→L2/L3, если:

1. категория совпадает с одним из шаблонов `rules_engine._LIFT_PATTERNS`;
2. целевой предикат **определён** в `rules.pl`
   (проверка через `discover_rule_predicates`).

Иначе запрос остаётся L1 — и `Agent` вернёт решения по фактам графа.

| Категория | L1 | L2/L3 |
|---|---|---|
| `transitive` | `edge('X', Y, 'находиться_в')` | `located_in('X', Y)` |
| `list` | `edge(X, 'россия', 'находиться_в')` | `techpark_in_russia(X)` |

```python
# Без rules.pl located_in/2 — лифтинг не применится
e = Expert(graph=g, rules_file=None)
qr = e.query("edge('a', X, 'находиться_в').", category="transitive")
print(qr.lifted_from)   # None — лифтинг не сработал
print(qr.query)         # edge('a', X, 'находиться_в').
```

### Расширение шаблонов

`rules_engine._LIFT_PATTERNS` — кортеж `(category, regex, builder)`.
Добавляйте свои:

```python
# в rules_engine.py
_LIFT_PATTERNS += (
    (
        "ownership",
        re.compile(r"^edge\('(?P<s>[^']+)',\s*X,\s*'владеть'\)$"),
        lambda m: f"owns_transitively('{m.group('s')}', X)",
    ),
)
```

---

## 7. Диалоговый режим и coref

`Expert.ask(..., use_dialog=True)` использует `nl2prolog.DialogTurn`:

- **coreference**: «ему/он/её» → `last_entity`;
- **ellipsis**: «А у Казани?» → подставляет `last_query`;
- **pending question**: если ответ не найден, `DialogTurn` запоминает
  вопрос и ждёт уточнения через `Session`.

```python
e.ask("Кто директор технопарка Саратов?")
# ✓ Решение: [1] X = Петров Пётр

e.ask("А сколько ему лет?")
# DialogTurn._resolve_coreference подставит 'петров_петр'
```

### Отключение диалога

```python
ans = e.ask("Кто директор?", use_dialog=False)
# Прямой TextToProlog.parse(strict=True, facts_from_questions=False)
```

---

## 8. Семантическая унификация

Опционально, поверх `PyAgentProlog.embedding_unify`.

```python
e = Expert(
    graph=g,
    semantic=True,
    semantic_config={
        "backend": "st",
        "model": "paraphrase-multilingual-mpnet",
        "local_dir": "D:/hf_embedding",
        "threshold": 0.82,
        "local_files_only": True,
        "hf_offline": True,
    },
)
print(e.semantic_status())
```

Установка: `pip install "pyagentprolog-expert[semantic]"`.

---

## 9. CLI

```bash
pa-expert --graph graph.pl --rules rules.pl [--debug]
```

| Команда | Действие |
|---|---|
| `<любой текст>` | `Expert.ask(text)` |
| `!!why` | объяснение последнего ответа |
| `!!assert` | NL-утверждение (интерактивный ввод) |
| `!!graph` | `graph.summary()` |
| `!!rules` | загружен ли `rules.pl` |
| `!!reset` | `Expert.reset()` |
| `!!quit` / `!!exit` / `:q` | выход |

`!!assert` требует `[nl]`. Остальные команды работают без `[nl]`.

---

## 10. Совместимость с kg-editor

Связь между редактором и экспертом — **через файл** `graph.pl`:

```
┌─────────────────┐   save    ┌──────────┐   read    ┌──────────────┐
│  kg-editor UI   │ ────────► │ graph.pl │ ────────► │ Expert       │
│  (редактор)     │           └──────────┘           │ (продакшен)  │
└─────────────────┘                                  └──────────────┘
```

`kg-editor` **не является зависимостью** `pyagentprolog-expert`:

- нет в `dependencies`;
- нет в `optional-dependencies`;
- не импортируется ни в `graph.py`, ни в `expert.py`, ни в `cli.py`.

### Duck-typing

Если у вас **уже есть** код на `kg_editor.KnowledgeGraph`, он работает
как `graph=...` без установки пакета — `Expert` вызывает только
`graph.to_prolog()` и `graph.merge(other)`:

```python
from kg_editor.graph_model import KnowledgeGraph as KGEditor  # если установлен
from pyagentprolog_expert import Expert

g = KGEditor.from_prolog(open("graph.pl").read())
e = Expert(graph=g)   # kg-editor в зависимостях Expert не нужен
```

`merge` в `kg_editor.KnowledgeGraph` принимает любой объект с
`.nodes`, `.edges`, `.attributes` — поэтому встроенный
`pyagentprolog_expert.KnowledgeGraph` тоже подходит.

### Тест совместимости

`tests/test_kg_editor_compat.py` пропускается, если `kg_editor`
не установлен (`pytest.importorskip`). CI его не требует.

---

## 11. Архитектура

```
                    ┌──────────────────────────────┐
                    │  Expert                      │
                    │                              │
  NL-вопрос ───────►│  ask(nl)                     │
                    │    ├─ DialogTurn (coref)     │──► query: edge(...)
                    │    ├─ lift_query (category)  │
                    │    ├─ KnowledgeGraph ────────┼──► facts: node/edge/attr
                    │    ├─ rules.pl ──────────────┼──► rules: located_in/2 …
                    │    └─ Agent (свежий) ────────┼──► solutions
                    │                              │
  NL-утверждение ──►│  assert_nl(nl)               │
                    │    ├─ TextToProlog.parse()   │──► facts_src
                    │    └─ graph.merge(...)       │──► graph
                    │                              │
  Prolog-запрос ───►│  query(prolog)               │
                    │    └─ Agent (свежий)         │──► solutions
                    └──────────────────────────────┘
```

Файлы пакета:

| Файл | Роль |
|---|---|
| `graph.py` | встроенный `KnowledgeGraph` (API-совместим с `kg-editor`) |
| `expert.py` | класс `Expert`, `QueryResult`, `AssertResult`, `ExpertAnswer` |
| `rules_engine.py` | `load_rules`, `lift_query`, `discover_rule_predicates` |
| `humanize.py` | снятие `_<N>`-суффиксов переменных |
| `session.py` | `Session`, `NullSession` для `ask_interactive` |
| `cli.py` | REPL `pa-expert` |

---

## 12. Расширение

### 12.1. Доменные правила

Все правила предметной области — в `rules.pl`, без правки кода.
Пример — `src/pyagentprolog_expert/rules.pl.example`:

```bash
python -c "import pyagentprolog_expert, os; \
  print(os.path.dirname(pyagentprolog_expert.__file__))"
# → скопируйте оттуда rules.pl.example в свой rules.pl
```

### 12.2. Кастомный `TextToProlog`

```python
from pyagentprolog_expert import Expert

class MyT2P:
    def parse(self, text, **kwargs):
        return "", "edge(X, 'obj', 'pred')"

e = Expert(graph=g, t2p=MyT2P())
ans = e.ask("...")
```

### 12.3. Кастомный `generic_filter` для `KnowledgeGraph`

По умолчанию встроенный `KnowledgeGraph` **не** фильтрует (готовый
граф уже валиден). Если строите граф через `Expert.assert_nl` и хотите
отсечь служебные слова — передайте фильтр:

```python
from pyagentprolog_expert import Expert, KnowledgeGraph

def my_filter(w: str) -> bool:
    return w in {"очень", "этот", "и"}

g = KnowledgeGraph(generic_filter=my_filter)
e = Expert(graph=g)
```

### 12.4. Свои шаблоны лифтинга

См. §6.

---

## 13. Диагностика

### 13.1. `why()`

Объяснение последнего ответа: запрос, `lifted_from`, биндинги,
`graph.summary()`, статус `rules.pl`.

### 13.2. `debug=True`

```python
e = Expert(graph=g, debug=True)
```

Печатает инициализацию `nl2prolog`, семантики, ошибки.

### 13.3. Проверка окружения

```python
import pyagentprolog_expert
print(pyagentprolog_expert.__version__)

try:
    import nl2prolog
    print("nl2prolog:", nl2prolog.__version__)
except ImportError:
    print("nl2prolog: не установлен (ask/assert_nl недоступны)")

try:
    import prolog
    print("pyagentprolog: ok")
except ImportError:
    print("pyagentprolog: не установлен")
```

### 13.4. Типичные ошибки

| Симптом | Причина | Решение |
|---|---|---|
| `RuntimeError: nl2prolog не установлен` | `ask()` без `[nl]` | `pip install "pyagentprolog-expert[nl]"` |
| `RuntimeError: pyagentprolog не установлен` | нет `pyagentprolog` | `pip install pyagentprolog` |
| `Нет решений` при непустом графе | регистр (`apple` ≠ `Apple`), лемма (`выдаёт` ≠ `выдавать`) | проверить `graph.to_prolog()` |
| Лифтинг не срабатывает | предикат не в `rules.pl` | добавить `located_in/2` в `rules.pl` |
| `✗ Ошибка: agent: …` | синтаксис в `rules.pl` | проверить `rules.pl` через `pa-expert --debug` |
| `✗ dialog: …` | `nl2prolog.DialogTurn` не инициализируется | `pip install --force-reinstall "nl2prolog[ru]"` |

---

## 14. Разработка

```bash
# Установка
pip install -e ".[nl,dev]"

# Тесты (все, кроме slow и kg_editor)
pytest -q -m "not slow and not kg_editor"

# Только core (без nl)
pytest -q -m "not nl and not slow and not kg_editor"

# Только compat с kg-editor (если установлен)
pip install kg-editor>=5.14
pytest -q tests/test_kg_editor_compat.py

# Линт
ruff check src tests
mypy src

# Сборка
python -m build
twine check dist/*
```

### Структура

```
pyagentprolog-expert/
├── pyproject.toml
├── README.md
├── CHANGELOG.md
├── LICENSE
├── src/pyagentprolog_expert/
│   ├── __init__.py
│   ├── _version.py
│   ├── graph.py
│   ├── expert.py
│   ├── humanize.py
│   ├── rules_engine.py
│   ├── session.py
│   ├── cli.py
│   ├── rules.pl.example
│   └── py.typed
└── tests/
    ├── conftest.py
    ├── test_graph.py
    ├── test_expert_basic.py
    ├── test_lifting.py
    ├── test_assert.py
    ├── test_humanize.py
    ├── test_rules_engine.py
    ├── test_cli.py
    └── test_kg_editor_compat.py
```

### CI-матрица

| Job | Что проверяет |
|---|---|
| `test (extras=nl)` | полный набор, кроме slow и kg_editor |
| `test (extras=all)` | + semantic |
| `test_core_only` | `[dev]` без `[nl]` — core работает |
| `test_with_kg_editor` | compat-тесты, `continue-on-error: true` |
| `build` | `python -m build` + `twine check` |

---

## 15. Лицензия

MIT. Автор — Andrey Vorfolomeev.

См. `LICENSE`.
