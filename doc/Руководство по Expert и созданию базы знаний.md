# Руководство по `Expert` и созданию базы знаний

Документ состоит из двух частей:

- **Часть I** — руководство по API `Expert`: как создавать, как задавать вопросы, как строить объяснения, как расширять.
- **Часть II** — инструкция по созданию базы знаний: граф знаний (`graph.pl`) + правила (`rules.pl`), с примерами «от текста к фактам», типичными ошибками и рецептами.

Все примеры согласованы с принципом «схема vs данные»: доменные факты (`label`, `alias_of`, `solution`-узлы) — только в `graph.pl`; `rules.pl` — только схема вывода.

---

# Часть I. Руководство по `Expert`

## 1. Что такое `Expert`

`Expert` — это фасад над тремя компонентами:

| Компонент | Роль | Зависимость |
|---|---|---|
| `KnowledgeGraph` | источник **фактов** | встроен |
| `rules.pl` (Horn-клаузы) | источник **правил** | файл |
| `Agent` (PyAgentProlog) | **движок вывода** | `pyagentprolog` (обязателен) |
| `TextToProlog` / `DialogTurn` | **NL → query**, **NL → facts** | `nl2prolog` (опция) |

`Expert` **не** хранит правил в графе и **не** мутирует `Agent` между запросами. На каждый запрос собирается свежий `Agent` из строки:

```
graph.to_prolog() + rules_src + _CONVENIENCE_RULES
```

`_CONVENIENCE_RULES` — это два сокращения, которые всегда доступны в запросах:

```prolog
node(Id, Type) :- node(Id, _, Type).
edge(S, T) :- edge(S, T, _).
```

Поэтому `node(apple, T)` работает без указания `Props`, а `edge(S, T)` — без предиката.

**Принцип «схема vs данные»:** факты о сущностях — в `graph.pl`; правила вывода — в `rules.pl`. `Expert` в коде не знает ни одной сущности домена.

---

## 2. Создание `Expert`

### 2.1. Минимальный конструктор

```python
from pyagentprolog_expert import Expert, KnowledgeGraph

g = KnowledgeGraph.from_prolog(open("graph.pl", encoding="utf-8").read())
e = Expert(graph=g)
```

`rules.pl` не указан — `Expert` работает **только с фактами графа**. Запросы `edge/3`, `node/3`, `attribute/3` работают; правила предметной области (`located_in/2`, `solution/1`) — нет.

### 2.2. С правилами

```python
e = Expert(graph=g, rules_file="rules.pl")
```

`rules_file` — путь к файлу с Horn-клаузами. Он подгружается в `Agent` на каждый запрос вместе с фактами графа.

### 2.3. Пустой граф (создание с нуля)

```python
e = Expert()
e.graph.add_node("apple", "org")
e.graph.add_edge("apple", "iphone", "releases")
```

### 2.4. Кастомный `TextToProlog`

```python
from pyagentprolog_expert import Expert

class MyT2P:
    def parse(self, text, **kwargs):
        return "", "edge(X, 'obj', 'pred')"

e = Expert(graph=g, t2p=MyT2P())
```

Полезно для тестов и доменных парсеров. Интерфейс — `parse(text, **kwargs) -> (facts_str, query_str)`.

### 2.5. Сессия для интерактивного опроса

```python
from pyagentprolog_expert import Expert, Session

sess = Session()
e = Expert(graph=g, rules_file="rules.pl", session=sess)
```

`Session` нужен только для `ask_interactive()`. В остальных случаях — `NullSession` по умолчанию.

### 2.6. Отладка

```python
e = Expert(graph=g, rules_file="rules.pl", debug=True)
```

Печатает инициализацию `nl2prolog`, семантики и ошибки внутренних вызовов.

---

## 3. Низкоуровневый API: `query`

`query()` работает **без** `nl2prolog`. Это «чистый Prolog поверх графа + правил».

### 3.1. Простой запрос

```python
qr = e.query("edge('петров_петр', X, 'директор').")
if qr.ok:
    for sol in qr.solutions:
        print(sol["X"])
```

`QueryResult`:

| Поле | Значение |
|---|---|
| `ok` | `True`, если запрос выполнен без ошибок |
| `query` | финальный запрос (после лифтинга), с точкой |
| `solutions` | список биндингов `[{X: ...}, ...]` |
| `result` | `True`/`False` для ground-запросов (`edge(a, b, c)`) |
| `error` | текст ошибки |
| `lifted_from` | исходный L1-запрос, если был лифтинг |
| `count` | `len(solutions)` |

### 3.2. Ground-запрос

```python
qr = e.query("edge('петров_петр', 'технопарк_саратов', 'директор').")
print(qr.result)     # True
print(qr.solutions)  # []
```

### 3.3. Запрос с `findall`

```python
qr = e.query("findall(X, edge('петров_петр', X, _), L).")
print(qr.solutions)   # [{'L': ['технопарк_саратов']}]
```

### 3.4. Запрос с `\+`

```python
qr = e.query("node(X, _, person), \\+ edge(X, _, 'директор').")
```

### 3.5. Ошибки

```python
qr = e.query("edge(X, 'obj', 'pred'")     # без закрывающей скобки
print(qr.ok)      # False
print(qr.error)   # описание от Agent
```

### 3.6. Что НЕ работает в `query`

- **Мутации `assertz`/`retract`** — живут только в рамках запроса и не влияют на граф. Для добавления фактов используйте `assert_facts_src()` / `graph.merge()`.
- **Правила в запросе** (`(foo(X) :- bar(X)), foo(a)`) — синтаксически могут пройти, но правила в `src` не добавляются. Для правил — `rules.pl`.

---

## 4. NL-вопрос: `ask`

`ask()` требует `[nl]`. Если `nl2prolog` не установлен — `RuntimeError` с подсказкой.

### 4.1. Простой вопрос

```python
ans = e.ask("Кто директор технопарка Саратов?")
print(ans.text)
# ✓ Решение:
# [1] X = Петров Пётр
```

`ExpertAnswer`:

| Поле | Значение |
|---|---|
| `text` | человекочитаемый ответ (готов к печати в UI) |
| `query_result` | `QueryResult` (можно достать `solutions`) |
| `used_rules` | список использованных правил |
| `category` | переданная категория |

Обратите внимание: в `text` подставлен `label` (`Петров Пётр`), а не ID (`петров_петр`) — это `attribute(Id, 'label', L)` из графа.

### 4.2. С query-lifting

```python
ans = e.ask("В какой стране технопарк Казань?", category="transitive")
print(ans.text)
# ✓ Решение:
# [1] X = россия
```

Внутри: `nl2prolog` вернул L1 (`edge('технопарк_казань', X, 'находиться_в')`), `Expert` применил лифтинг → `located_in('технопарк_казань', X)` (если `located_in/2` определён в `rules.pl`).

### 4.3. Без диалога

```python
ans = e.ask("Кто директор?", use_dialog=False)
```

Отключает `DialogTurn` (coref/ellipsis). Полезно для stateless-сценариев.

### 4.4. Что делать, если `Нет решений`

1. `print(e.why())` — покажет запрос, `lifted_from`, `graph.summary()`, статус `rules.pl`.
2. Проверить регистр (`apple` ≠ `Apple`).
3. Проверить лемму (`выдаёт` ≠ `выдавать`).
4. Проверить, что нужный предикат определён в `rules.pl` (для лифтинга).
5. Проверить, что `label` задан через `attribute(Id, 'label', L)` — для человекочитаемого вывода.

### 4.5. Fallback без `[nl]`

Если `[nl]` не установлен — `ask()` бросит `RuntimeError`. Используйте `query()`:

```python
qr = e.query("edge(X, 'технопарк_саратов', 'директор').")
```

---

## 5. NL-утверждение: `assert_nl`

`assert_nl()` требует `[nl]`. Без него — `RuntimeError`.

```python
r = e.assert_nl("Илон Маск владеет Tesla")
print(r.ok, r.added)
# True {'nodes': 2, 'edges': 1, 'attributes': 0}
```

`assert_nl` делает **аддитивное** слияние: существующие узлы/рёбра/атрибуты не перезаписываются, дедуп по ключам.

### 5.1. Без `[nl]`: `assert_facts_src`

```python
r = e.assert_facts_src(
    "node('new_org', [], org).\n"
    "edge('new_org', 'технопарк_саратов', 'партнёр').\n"
)
```

Полезно для интеграции с внешними пайплайнами, которые сами генерируют Prolog-факты.

### 5.2. Что игнорируется

`KnowledgeGraph.from_prolog` читает **только** `node/3`, `edge/3`, `attribute/3`. Horn-клаузы в `facts_src` **молча выбрасываются**:

```python
r = e.assert_facts_src(
    "node('a', [], org).\n"
    "grandparent(X, Z) :- parent(X, Y), parent(Y, Z).\n"
)
# r.added['nodes'] == 1, правило grandparent/2 в граф не попало
```

Для правил — `rules.pl`.

---

## 6. Объяснение: `why`

```python
ans = e.ask("Кто директор технопарка Саратов?")
print(e.why())
```

Пример вывода:

```
Запрос: edge(X, 'технопарк_саратов', 'директор').
Результат: истина
  [1] X=Петров Пётр

Источники истины:
  • граф: {'nodes': 2, 'edges': 1, 'attributes': 0}
  • rules.pl: загружен
```

С лифтингом:

```
Запрос: located_in('технопарк_казань', X).
Исходный (L1): edge('технопарк_казань', X, 'находиться_в').
Применён query-lifting → located_in('технопарк_казань', X).
Результат: истина
  [1] X=россия

Источники истины:
  • граф: {'nodes': 4, 'edges': 3, 'attributes': 0}
  • rules.pl: загружен
```

В биндингах подставлен `label` (если задан через `attribute(Id, 'label', L)`); fallback — `humanize_vars(id).replace('_', ' ')`.

---

## 7. Интерактивный опрос: `ask_interactive`

`ask_interactive()` требует `[nl]` и `Session`.

```python
from pyagentprolog_expert import Expert, Session

sess = Session()
e = Expert(graph=g, rules_file="rules.pl", session=sess)

# UI-поток:
result = e.ask_interactive("Хочу назначить директора")
# Expert задаёт вопросы через sess.output_queue, читает из sess.input_queue
```

`Session`:

| Метод | Назначение |
|---|---|
| `ask_user(question)` | положить вопрос в `output_queue`, дождаться ответа из `input_queue` |
| `send(text)` | UI кладёт ответ пользователя в `input_queue` |
| `poll()` | UI читает `output_queue` |
| `stop()` | завершить сессию |

Алгоритм `ask_interactive`:

1. `ask(nl)` — первичный ответ.
2. Если решений нет — `_missing_conditions()` ищет невыполненные `condition/1` из `solution/1`-схемы в `rules.pl`.
3. Для каждого невыполненного — NL-вопрос через `Session.ask_user`.
4. NL-ответ → `assert_nl` → факты в граф.
5. Повтор `ask(nl)` до `max_turns` или до успеха.

**Данные `solution`** — узлы `node(S, [], solution)` и рёбра `edge(S, Target, 'target')`, `edge(S, Person, 'director')` в `graph.pl`. В `rules.pl` — только схема (см. Часть II §13.9).

---

## 8. Сброс и семантика

### 8.1. `reset()`

```python
e.reset()
```

Сбрасывает `_last_answer` и `dlg_state`, очищает `_label_cache`. Граф **не** трогается.

### 8.2. Семантика

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
e.disable_semantic()
```

Требует `[semantic]`. Семантика включается в `Agent` и влияет на унификацию атомов (`москва` ↔ `moscow`).

---

## 9. Query-lifting: как это работает

`nl2prolog` эмитит **только L1-запросы** (`edge/attribute/node/alias`). Правила предметной области — L2/L3.

`Expert.query(category=...)` лифтит L1→L2/L3, **если**:

1. `category` совпадает с одним из шаблонов `rules_engine._LIFT_PATTERNS`;
2. целевой предикат **определён** в `rules.pl` (проверка через `discover_rule_predicates`).

| Категория | L1 | L2/L3 |
|---|---|---|
| `transitive` | `edge('X', Y, 'находиться_в')` | `located_in('X', Y)` |
| `list` | `edge(X, 'россия', 'находиться_в')` | `techpark_in_russia(X)` |

Без `rules.pl` лифтинг не применяется — запрос остаётся L1 и идёт по фактам графа.

### 9.1. Расширение шаблонов

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

И добавить `owns_transitively/2` в `rules.pl`:

```prolog
owns_transitively(X, Y) :- edge(X, Y, 'владеть').
owns_transitively(X, Y) :- edge(X, Z, 'владеть'), owns_transitively(Z, Y).
```

---

## 10. Типичные сценарии

### 10.1. Продакшен: только факты

```python
e = Expert(graph=KnowledgeGraph.from_prolog(open("graph.pl").read()))
qr = e.query("edge(X, 'obj', 'pred').")
```

Без `rules.pl`, без `[nl]` — минимальный рантайм.

### 10.2. Продакшен + правила

```python
e = Expert(graph=g, rules_file="rules.pl")
qr = e.query("located_in('технопарк_казань', X).")     # напрямую
qr = e.query("edge('технопарк_казань', X, 'находиться_в').",
             category="transitive")                     # с лифтингом
```

### 10.3. NL-интерфейс

```python
e = Expert(graph=g, rules_file="rules.pl")   # [nl] установлен
ans = e.ask("Кто директор технопарка Саратов?")
print(ans.text)
```

### 10.4. Интеграция с редактором

```python
# редактор сохранил graph.pl
g = KnowledgeGraph.from_prolog(open("graph.pl").read())
e = Expert(graph=g, rules_file="rules.pl")
```

Связь — через файл, `kg-editor` в зависимостях **не** нужен.

---

# Часть II. Создание базы знаний

## 11. Общая картина

```
knowledge_base/
├── graph.pl        # факты: node/3, edge/3, attribute/3
└── rules.pl        # схема: Horn-клаузы
```

| Файл | Что содержит | Кто читает |
|---|---|---|
| `graph.pl` | факты о мире | `KnowledgeGraph.from_prolog` |
| `rules.pl` | схема вывода | `Agent` (напрямую) |

**Правило разделения:**

- **факт о сущности** → `graph.pl`;
- **правило вывода** → `rules.pl`.

Принцип из §9.1 «Документации nl2prolog»: *«если знание можно записать как факт `kb.pl`, как алиас в KB, или как контекст в `dialog.py` — оно не должно быть в `text_to_prolog.py`»*. То же верно для `Expert`: если знание — это факт о конкретной сущности, оно в `graph.pl`, не в `rules.pl` и не в коде.

---

## 12. Создание `graph.pl`

### 12.1. Три предиката

```prolog
node(Id, Props, Type).              % узел
edge(Source, Target, Predicate).    % направленное ребро
attribute(Entity, Name, Value).     % атрибут (Value — строка)
```

### 12.2. Правила именования

| Элемент | Валидный атом | В кавычках |
|---|---|---|
| `Id` | `apple`, `технопарк_саратов` | `'ООО «Ромашка»'`, `'Тихий океан'` |
| `Type` | `org`, `person`, `technopark` | `'Some Type'` |
| `Predicate` | `owns`, `находиться_в` | `'выдавать лицензию'` |
| `Name` | `release_year`, `год_основания` | `'Some Name'` |
| `Value` | — | **всегда** `'...'`, даже числа |

Валидный атом (без кавычек): `[a-z][A-Za-z0-9_]*`. Compound-ID (`технопарк_саратов`) — валидный атом, идёт без кавычек.

### 12.3. Типы узлов

Типы — **свободные атомы**. Типичные:

| Тип | Когда |
|---|---|
| `person` | люди |
| `org` / `organization` | организации |
| `place` / `loc` | места |
| `thing` / `product` | объекты, продукты |
| `event` | события |
| `concept` | абстракции |
| `document` | документы |
| `technopark` | доменный тип |
| `solution` | узел-решение для `ask_interactive` |

Рекомендуется единый словарь типов в проекте — но `Expert` его **не проверяет** (тип — просто атом).

### 12.4. Предикаты рёбер

Предикаты — **свободные атомы**. Лемматизируйте:

| Плохо | Хорошо |
|---|---|
| `выдаёт`, `выдает`, `выдал` | `выдавать` |
| `находится_в`, `находились_в` | `находиться_в` |
| `работает`, `работал` | `работать` |

`nl2prolog` уже лемматизирует — граф должен совпадать по леммам.

### 12.5. Пример: предметная область «технопарки»

```prolog
% --- узлы ---
node('технопарк_саратов', [], technopark).
node('технопарк_казань', [], technopark).
node('петров_петр', [], person).
node('иванов_иван', [], person).
node('россия', [], place).
node('саратов', [], place).
node('казань', [], place).
node('регулятор', [], org).

% --- рёбра ---
edge('петров_петр', 'технопарк_саратов', 'директор').
edge('иванов_иван', 'технопарк_казань', 'директор').
edge('технопарк_саратов', 'саратов', 'находиться_в').
edge('технопарк_казань', 'казань', 'находиться_в').
edge('саратов', 'россия', 'находиться_в').
edge('казань', 'россия', 'находиться_в').
edge('регулятор', 'технопарк_саратов', 'контролировать').

% --- FIO: alias как ребро ---
edge('петров', 'петров_петр', 'alias_of').
edge('иванов', 'иванов_иван', 'alias_of').

% --- label: человекочитаемое имя через attribute/3 ---
attribute('петров_петр', 'label', 'Петров Пётр').
attribute('иванов_иван', 'label', 'Иванов Иван').
attribute('технопарк_саратов', 'label', 'Технопарк Саратов').
attribute('технопарк_казань', 'label', 'Технопарк Казань').
attribute('россия', 'label', 'Россия').

% --- прочие атрибуты ---
attribute('технопарк_саратов', 'год_основания', '2015').
attribute('технопарк_казань', 'год_основания', '2017').
attribute('петров_петр', 'возраст', '45').
attribute('иванов_иван', 'возраст', '38').
```

### 12.6. Пример: организация

```prolog
node('apple', [], org).
node('iphone', [], product).
node('smartphone', [], concept).
node('steve_jobs', [], person).

edge('apple', 'iphone', 'releases').
edge('apple', 'smartphone', 'produces').
edge('steve_jobs', 'apple', 'owns').

attribute('apple', 'label', 'Apple Inc.').
attribute('iphone', 'label', 'iPhone').
attribute('steve_jobs', 'label', 'Стив Джобс').

attribute('iphone', 'release_year', '2022').
attribute('apple', 'industry', 'electronics').
```

### 12.7. Props узла

`Props` — плоские пары `k=v`, значения — строки:

```prolog
node('технопарк_саратов',
     [weight='0.5', region='саратовская_область'],
     technopark).
```

`Props` не участвуют в запросах по умолчанию (`node/2` их скрывает). Доступ — только через `node(Id, Props, Type)`:

```prolog
node(X, Props, _), member(weight=V, Props), V = '0.5'.
```

### 12.8. Атрибуты — всегда строки

```prolog
attribute('iphone', release_year, '2022').      % ✓
attribute('iphone', release_year, 2022).        % ✗ — 2022 не строка
```

Для числовых сравнений — `atom_number/2`:

```prolog
attribute('iphone', release_year, V), atom_number(V, Y), Y > 2020.
```

### 12.9. Метаданные и комментарии

```prolog
% Это комментарий
/* Многострочный
   комментарий */
node('apple', [], org).
```

`from_prolog` комментарии игнорирует.

### 12.10. `label` — человекочитаемое имя

`label` — это **атрибут** узла, а не правило:

```prolog
attribute('петров_петр', 'label', 'Петров Пётр').
attribute('технопарк_саратов', 'label', 'Технопарк Саратов').
```

`Expert._describe_identifier` читает `attribute(Id, 'label', L)` из графа; fallback — `humanize_vars(id).replace('_', ' ')`. Так `why()` и `text` в `ExpertAnswer` показывают «Петров Пётр», а не `петров_петр`.

**Почему не `human_readable('петров_петр', 'Петров Пётр')` в `rules.pl`:** это доменный факт, дублирующий `node/3`, и он расходится с `graph.pl` при обновлении. В `rules.pl` — только **схема** (см. §13.8).

### 12.11. `alias` — ребро `alias_of`

`alias` short→full — это **связь** между сущностями, а не свойство:

```prolog
edge('петров', 'петров_петр', 'alias_of').
edge('иванов', 'иванов_иван', 'alias_of').
```

`rules.pl` содержит схему `alias/2 :- edge(_, _, 'alias_of')` (см. §13.7). В `kg-editor` это редактируется как обычное ребро.

### 12.12. `solution` — узел типа `solution`

Решение (`назначить_петрова`) — это **сущность** графа:

```prolog
node('назначить_петрова', [], solution).
edge('назначить_петрова', 'технопарк_саратов', 'target').
edge('назначить_петрова', 'петров_петр', 'director').
```

`rules.pl` содержит схему `solution/1 :- node(S, _, solution)` и `condition/1` (см. §13.9). В `rules.pl` — никаких `solution('назначить_петрова') :- ...` как фактов.

---

## 13. Создание `rules.pl`

### 13.1. Что такое Horn-клауза

```prolog
head(Args) :- goal1, goal2, goal3.
```

Читается: «`head` истинно, если `goal1` И `goal2` И `goal3`».

Факт — клауза без тела:

```prolog
valid_node_type(technopark).
```

**В `rules.pl` — только схема.** Доменные факты (`label`, `alias_of`, `solution`-узлы) — в `graph.pl`. В `rules.pl` факты допустимы только для словаря (`valid_node_type/1`, `valid_edge_predicate/1`), но не для сущностей.

### 13.2. Три типа правил

| Тип | Что даёт | Пример |
|---|---|---|
| **вывод** | новые предикаты из фактов | `located_in/2` |
| **схема** | обёртки над `attribute/3`, `edge/3`, `node/3` | `human_readable/2`, `alias/2`, `solution/1` |
| **лифтинг** | L1→L2/L3 для `query(category=...)` | `located_in/2`, `techpark_in_russia/1` |

### 13.3. Вывод: транзитивное замыкание

```prolog
located_in(X, Y) :- edge(X, Y, 'находиться_в').
located_in(X, Y) :- edge(X, Z, 'находиться_в'), located_in(Z, Y).
```

Запрос:

```prolog
located_in('технопарк_казань', X).
% X = казань ; X = россия
```

### 13.4. Вывод: список по типу

```prolog
techpark_in_russia(T) :-
    node(T, _, technopark),
    located_in(T, 'россия').
```

Запрос:

```prolog
techpark_in_russia(X).
% X = 'технопарк_саратов' ; X = 'технопарк_казань'
```

### 13.5. Вывод: отрицание

```prolog
technopark_without_director(T) :-
    node(T, _, technopark),
    \+ edge(_, T, 'директор').
```

### 13.6. Вывод: агрегация

```prolog
count_technoparks_in_country(Country, N) :-
    findall(T, techpark_in_country(T, Country), Ts),
    length(Ts, N).

techpark_in_country(T, Country) :-
    node(T, _, technopark),
    located_in(T, Country).
```

### 13.7. Схема: `alias/2`

`alias/2` — **схема**, читает `edge(Short, Full, 'alias_of')` из графа:

```prolog
alias(Short, Full) :- edge(Short, Full, 'alias_of').
alias(Short, Full) :- attribute(Full, 'alias', Short).
```

Использование — в правиле или запросе:

```prolog
director_by_surname(Surname, Org) :-
    alias(Surname, FullName),
    edge(FullName, Org, 'директор').
```

Запрос:

```prolog
alias('петров', F).
% F = 'петров_петр'
```

**Почему не `alias('петров', 'петров_петр').` в `rules.pl`:** это доменный факт, дублирующий ребро `alias_of` в `graph.pl`. В `rules.pl` — только схема.

### 13.8. Схема: `human_readable/2`

`human_readable/2` — **схема**, читает `attribute(Id, 'label', L)` из графа:

```prolog
human_readable(Id, Label) :- attribute(Id, 'label', Label).
```

Использование — в запросе или в `Expert._describe_identifier` (fallback, если `_label_cache` пуст):

```prolog
edge(X, 'технопарк_саратов', 'директор'), human_readable(X, H).
% X = 'петров_петр', H = 'Петров Пётр'
```

**Почему не `human_readable('петров_петр', 'Петров Пётр').` в `rules.pl`:** это доменный факт. При 10 000 сущностей — 10 000 строк в `rules.pl`; при обновлении `graph.pl` — расхождение. В `rules.pl` — только схема.

### 13.9. Схема: `solution/1` + `condition/1`

`solution/1` и `condition/1` — **схема**, читают узлы типа `solution` и их рёбра из графа:

```prolog
solution(S) :- node(S, _, solution).

condition(triplet('директор', P, Org)) :-
    edge(S, Org, 'target'),
    edge(S, P, 'director'),
    solution(S).
```

Данные — в `graph.pl`:

```prolog
node('назначить_петрова', [], solution).
edge('назначить_петрова', 'технопарк_саратов', 'target').
edge('назначить_петрова', 'петров_петр', 'director').
```

`Expert._missing_conditions()` соберёт невыполненные `condition/1` и превратит их в NL-вопросы для `ask_interactive`.

**Почему не `solution('назначить_петрова') :- condition(...).` в `rules.pl`:** это доменный факт. Решение — сущность графа; его свойства (`target`, `director`) — рёбра.

### 13.10. Доменные предикаты для лифтинга

Любое правило из `rules.pl` доступно для лифтинга — добавьте шаблон в `rules_engine._LIFT_PATTERNS`:

```python
# rules_engine.py
_LIFT_PATTERNS += (
    (
        "ownership",
        re.compile(r"^edge\('(?P<s>[^']+)',\s*X,\s*'владеть'\)$"),
        lambda m: f"owns_transitively('{m.group('s')}', X)",
    ),
)
```

И правило в `rules.pl`:

```prolog
owns_transitively(X, Y) :- edge(X, Y, 'владеть').
owns_transitively(X, Y) :- edge(X, Z, 'владеть'), owns_transitively(Z, Y).
```

### 13.11. Ограничения `rules.pl`

`Agent` (PyAgentProlog) поддерживает подмножество ISO Prolog. **Не** работают:

| Конструкция | Альтернатива |
|---|---|
| `:- module(...)` | нет (плоское пространство) |
| `:- use_module(...)` | нет |
| `DCG` (`-->`) | ручное `append/3` |
| `:- op(...)` | нет |
| `catch/3`, `throw/1` | нет |
| `between/3`, `succ/2` | `findall` + `length` |
| `sort/2`, `msort/2` | `setof/3` |
| `read/1`, `open/3` | нет |
| `atom_length/2`, `atom_concat/3` | нет |
| CLP(FD) | нет |

Работают:

| Конструкция | Пример |
|---|---|
| `;` (дизъюнкция) | `(a(X) ; b(X))` |
| `->` (if-then) | `(X > 0 -> pos ; neg)` |
| `!` (cut) | `max(X, Y, X) :- X >= Y, !.` |
| `\+` (negation) | `\+ edge(X, _, _)` |
| `findall/3`, `setof/3`, `bagof/3` | стандарт |
| `append/3`, `member/2`, `length/2` | стандарт |
| `atom_number/2` | для чисел из строк |
| `write/1`, `nl/0` | отладка |

### 13.12. Полный `rules.pl.example`

```prolog
% rules.pl.example — СХЕМА вывода. НЕ факты домена.
%
% Здесь только правила, применимые к любой предметной области.
% Всё, что зависит от конкретной сущности (label, alias, solution,
% доменные типы), хранится в graph.pl как node/3, edge/3, attribute/3.

% ---------------------------------------------------------------------
% Транзитивное замыкание по 'находиться_в'
% ---------------------------------------------------------------------
located_in(X, Y) :- edge(X, Y, 'находиться_в').
located_in(X, Y) :- edge(X, Z, 'находиться_в'), located_in(Z, Y).

% ---------------------------------------------------------------------
% Список технопарков в стране (пример использования located_in/2)
% ---------------------------------------------------------------------
techpark_in_russia(T) :-
    node(T, _, technopark),
    located_in(T, 'россия').

% ---------------------------------------------------------------------
% alias/2 — СХЕМА. Данные — edge(Short, Full, 'alias_of') в graph.pl.
% ---------------------------------------------------------------------
alias(Short, Full) :- edge(Short, Full, 'alias_of').
alias(Short, Full) :- attribute(Full, 'alias', Short).

% ---------------------------------------------------------------------
% human_readable/2 — СХЕМА. Данные — attribute(Id, 'label', L) в graph.pl.
% ---------------------------------------------------------------------
human_readable(Id, Label) :- attribute(Id, 'label', Label).

% ---------------------------------------------------------------------
% solution/1 + condition/1 — СХЕМА для ask_interactive().
%
% Данные — узлы типа 'solution' и их рёбра в graph.pl:
%   node('назначить_петрова', [], solution).
%   edge('назначить_петрова', 'технопарк_саратов', 'target').
%   edge('назначить_петрова', 'петров_петр', 'director').
% ---------------------------------------------------------------------
solution(S) :- node(S, _, solution).

condition(triplet('директор', P, Org)) :-
    edge(S, Org, 'target'),
    edge(S, P, 'director'),
    solution(S).

% ---------------------------------------------------------------------
% Пример схемы отрицания (опционально)
% ---------------------------------------------------------------------
without_director(T) :-
    node(T, _, _),
    \+ edge(_, T, 'директор').
```

---

## 14. Сценарий «от текста к базе знаний»

### 14.1. Шаг 1. Собрать текст

Возьмите исходный документ (нормативку, статью, описание домена).

### 14.2. Шаг 2. NL-импорт в редактор (опционально)

Если используете `kg-editor`:

1. Откройте редактор.
2. NL-импорт → «📊 Факты».
3. Проверьте вкладку «🛡️ Отфильтровано».
4. Сохраните `graph.pl`.

Без редактора — используйте `nl2prolog` напрямую:

```python
from nl2prolog import TextToProlog

t2p = TextToProlog()
facts, _ = t2p.parse(open("doc.txt").read(), strict=True)
open("graph.pl", "w").write(facts)
```

### 14.3. Шаг 3. Проверить факты вручную

```python
from pyagentprolog_expert import KnowledgeGraph

g = KnowledgeGraph.from_prolog(open("graph.pl").read())
print(g.summary())
for n in g.nodes.values():
    print(n.id, n.type)
for e in g.edges:
    print(e.source, "->", e.target, f"[{e.predicate}]")
for a in g.attributes:
    print(a.entity, f"[{a.name}]", "=", a.value)
```

Типичные ошибки после NL-импорта:

| Симптом | Что делать |
|---|---|
| Лишние узлы-прилагательные | добавить в `generic_filter` или отредактировать `graph.pl` |
| Ошибки лемматизации | поправить предикат (`выдаёт` → `выдавать`) |
| Дубликаты с разным регистром | привести к нижнему регистру |
| Compound-ID разбит на два | склеить в `технопарк_саратов` |
| Нет `label` у сущности | добавить `attribute(Id, 'label', L)` |
| `alias` short→full в `rules.pl` | перенести в `graph.pl` как `edge(_, _, 'alias_of')` |

### 14.4. Шаг 4. Написать `rules.pl` — только схему

Определите:

1. **транзитивные** предикаты (`located_in/2`);
2. **списочные** предикаты (`techpark_in_russia/1`);
3. **схемы** `alias/2`, `human_readable/2`, `solution/1` + `condition/1`;
4. **схемы отрицания** (`without_director/1`).

**Не** добавляйте в `rules.pl`:
- `human_readable('петров_петр', 'Петров Пётр').`
- `alias('петров', 'петров_петр').`
- `solution('назначить_петрова') :- condition(...).`

Всё это — данные, они в `graph.pl`.

### 14.5. Шаг 5. Проверить запросы

```python
e = Expert(graph=g, rules_file="rules.pl")

# простой
print(e.query("edge('петров_петр', X, 'директор').").solutions)

# правило
print(e.query("located_in('технопарк_казань', X).").solutions)

# лифтинг
print(e.query(
    "edge('технопарк_казань', X, 'находиться_в').",
    category="transitive",
).solutions)

# NL
print(e.ask("В какой стране технопарк Казань?", category="transitive").text)
```

### 14.6. Шаг 6. Довести `why()`

```python
ans = e.ask("Кто директор технопарка Саратов?")
print(e.why())
```

Если `why()` показывает `X=петров_петр` вместо `Петров Пётр` — добавьте `attribute('петров_петр', 'label', 'Петров Пётр')` в `graph.pl`. **Не** добавляйте `human_readable('петров_петр', 'Петров Пётр')` в `rules.pl`.

---

## 15. Рецепты

### 15.1. FIO-развёртывание

**Проблема:** `nl2prolog` извлёк `петров`, в графе — `петров_петр`.

**Решение:** `edge('петров', 'петров_петр', 'alias_of')` в `graph.pl` + схема `alias/2` в `rules.pl`.

Использование:

```prolog
director_by_surname(S, Org) :-
    alias(S, Full),
    edge(Full, Org, 'директор').
```

### 15.2. Аббревиатуры

```prolog
edge('рф', 'российская_федерация', 'alias_of').
edge('ооо_ромашка', 'ООО «Ромашка»', 'alias_of').
```

### 15.3. Транзитивное замыкание

```prolog
part_of(X, Y) :- edge(X, Y, 'часть').
part_of(X, Y) :- edge(X, Z, 'часть'), part_of(Z, Y).
```

Запрос:

```prolog
part_of('деталь', X).
% все предки детали
```

### 15.4. Список по типу

```prolog
persons(X) :-
    node(X, _, person).

directors(X) :-
    node(X, _, person),
    edge(X, _, 'директор').
```

### 15.5. Отрицание

```prolog
technopark_without_director(T) :-
    node(T, _, technopark),
    \+ edge(_, T, 'директор').
```

### 15.6. Агрегация

```prolog
count_directors(Org, N) :-
    findall(P, edge(P, Org, 'директор'), Ps),
    length(Ps, N).
```

### 15.7. Числовые сравнения

```prolog
old_persons(X) :-
    node(X, _, person),
    attribute(X, 'возраст', V),
    atom_number(V, N),
    N > 60.
```

### 15.8. Рекурсивный обход

```prolog
ancestor(X, Y) :- edge(X, Y, 'родитель').
ancestor(X, Y) :- edge(X, Z, 'родитель'), ancestor(Z, Y).
```

Осторожно: без ограничения глубины может зациклиться на циклах. Для DAG — безопасно.

### 15.9. `label` для `why()`

```prolog
% В graph.pl:
attribute('петров_петр', 'label', 'Петров Пётр').
attribute('технопарк_саратов', 'label', 'Технопарк Саратов').
attribute('россия', 'label', 'Россия').

% В rules.pl — только схема:
human_readable(Id, Label) :- attribute(Id, 'label', Label).
```

### 15.10. Метаданные в `Props`

```prolog
node('технопарк_саратов',
     [weight='0.9', source='doc_1863'],
     technopark).
```

Запрос:

```prolog
node(X, Props, _), member(weight=W, Props), atom_number(W, V), V > 0.5.
```

### 15.11. `solution` для `ask_interactive`

```prolog
% В graph.pl:
node('назначить_петрова', [], solution).
edge('назначить_петрова', 'технопарк_саратов', 'target').
edge('назначить_петрова', 'петров_петр', 'director').

% В rules.pl — только схема:
solution(S) :- node(S, _, solution).
condition(triplet('директор', P, Org)) :-
    edge(S, Org, 'target'),
    edge(S, P, 'director'),
    solution(S).
```

---

## 16. Антипаттерны

| Антипаттерн | Почему плохо | Как правильно |
|---|---|---|
| Правила в `graph.pl` | `from_prolog` их выбросит | `rules.pl` |
| `human_readable('id', 'label').` в `rules.pl` | доменный факт, дублирует `node/3` | `attribute(Id, 'label', L)` в `graph.pl` + схема в `rules.pl` |
| `alias('short', 'full').` в `rules.pl` | доменный факт | `edge(Short, Full, 'alias_of')` в `graph.pl` + схема в `rules.pl` |
| `solution('name') :- ...` в `rules.pl` | доменный факт | `node(S, [], solution)` + рёбра в `graph.pl` + схема в `rules.pl` |
| `attribute(e, n, 2022)` | `Value` — строка | `attribute(e, n, '2022')` |
| Предикаты в словоформах (`выдаёт`) | не совпадут с леммой из `nl2prolog` | лемма (`выдавать`) |
| Кириллица без кавычек | `_VALID_ATOM` требует `[a-z]` | `'регулятор'` |
| Дубликаты рёбер | `add_edge` не дедуплицирует | дедуп вручную или `merge` |
| `assertz` для сохранения | не переживает запрос | `graph.merge` / `assert_facts_src` |
| Типы с пробелами (`'Some Type'`) | сложнее в запросах | `some_type` |
| `Props` с вложенностью | `_parse_props` не поддерживает | плоские пары |
| Доменные константы в `nl2prolog` | нарушает обобщаемость | `rules.pl` / `alias_of` |
| `located_in/2` в `nl2prolog` | нарушает слои | `rules.pl` + `category` |
| `human_readable/2`-факты в `rules.pl` | домен в коде | `attribute(Id, 'label', L)` в `graph.pl` |

---

## 17. Чек-лист перед публикацией базы знаний

### Граф (`graph.pl`)

- [ ] Все `Id` уникальны (нет двух `node('x', ...)` с разными типами).
- [ ] Все `edge.Source` и `edge.Target` есть в `nodes`.
- [ ] Все `attribute.Entity` есть в `nodes`.
- [ ] Кириллица, пробелы, заглавные — в кавычках.
- [ ] `Value` в `attribute/3` — строка в кавычках.
- [ ] Предикаты — леммы (`выдавать`, не `выдаёт`).
- [ ] Нет Horn-клауз (только `node/3`, `edge/3`, `attribute/3`).
- [ ] Типы — из единого словаря (даже если `Expert` не проверяет).
- [ ] `label` задан через `attribute(Id, 'label', L)` для ключевых сущностей.
- [ ] `alias_of` задан как `edge(Short, Full, 'alias_of')` для FIO/аббревиатур.
- [ ] `solution`-узлы заданы как `node(S, [], solution)` + рёбра `target`/`director`.

### Правила (`rules.pl`)

- [ ] Все предикаты определены (нет «висячих» вызовов).
- [ ] Нет `:- module`, `:- use_module`, DCG, `catch/3`, `between/3`, `sort/2`.
- [ ] **Нет доменных фактов**: `human_readable('id', 'label').`, `alias('short', 'full').`, `solution('name') :- ...` — всё это должно быть в `graph.pl`.
- [ ] Схемы `human_readable/2`, `alias/2`, `solution/1` + `condition/1` присутствуют.
- [ ] Правила для query-lifting (`located_in/2`, `techpark_in_russia/1`) — если используете `category=`.

### Интеграция

- [ ] `Expert(graph=g, rules_file="rules.pl")` создаётся без ошибок.
- [ ] `e.query("edge(X, 'obj', 'pred').").ok` — `True`.
- [ ] `e.ask("...")` возвращает осмысленный `text`.
- [ ] `e.why()` показывает `label`-имена, а не ID.
- [ ] `pa-expert --graph graph.pl --rules rules.pl` запускается.
- [ ] `test_no_domain_in_rules.py` проходит (если вы копировали тесты).

---

## 18. Полный пример: «технопарки»

### 18.1. `graph.pl`

```prolog
% --- узлы ---
node('технопарк_саратов', [], technopark).
node('технопарк_казань', [], technopark).
node('петров_петр', [], person).
node('иванов_иван', [], person).
node('россия', [], place).
node('саратов', [], place).
node('казань', [], place).
node('регулятор', [], org).
node('назначить_петрова', [], solution).
node('назначить_иванова', [], solution).

% --- рёбра ---
edge('петров_петр', 'технопарк_саратов', 'директор').
edge('иванов_иван', 'технопарк_казань', 'директор').
edge('технопарк_саратов', 'саратов', 'находиться_в').
edge('технопарк_казань', 'казань', 'находиться_в').
edge('саратов', 'россия', 'находиться_в').
edge('казань', 'россия', 'находиться_в').
edge('регулятор', 'технопарк_саратов', 'контролировать').

% --- FIO: alias как ребро ---
edge('петров', 'петров_петр', 'alias_of').
edge('иванов', 'иванов_иван', 'alias_of').

% --- solution: узел + рёбра ---
edge('назначить_петрова', 'технопарк_саратов', 'target').
edge('назначить_петрова', 'петров_петр', 'director').
edge('назначить_иванова', 'технопарк_казань', 'target').
edge('назначить_иванова', 'иванов_иван', 'director').

% --- label: человекочитаемое имя через attribute/3 ---
attribute('петров_петр', 'label', 'Петров Пётр').
attribute('иванов_иван', 'label', 'Иванов Иван').
attribute('технопарк_саратов', 'label', 'Технопарк Саратов').
attribute('технопарк_казань', 'label', 'Технопарк Казань').
attribute('россия', 'label', 'Россия').

% --- прочие атрибуты ---
attribute('технопарк_саратов', 'год_основания', '2015').
attribute('технопарк_казань', 'год_основания', '2017').
attribute('петров_петр', 'возраст', '45').
attribute('иванов_иван', 'возраст', '38').
```

### 18.2. `rules.pl` — только схема

```prolog
% --- транзитивное замыкание ---
located_in(X, Y) :- edge(X, Y, 'находиться_в').
located_in(X, Y) :- edge(X, Z, 'находиться_в'), located_in(Z, Y).

% --- список по типу ---
techpark_in_russia(T) :-
    node(T, _, technopark),
    located_in(T, 'россия').

% --- alias: схема, данные — edge(Short, Full, 'alias_of') ---
alias(Short, Full) :- edge(Short, Full, 'alias_of').

% --- human_readable: схема, данные — attribute(Id, 'label', L) ---
human_readable(Id, Label) :- attribute(Id, 'label', Label).

% --- solution: схема, данные — node(S, [], solution) + рёбра ---
solution(S) :- node(S, _, solution).

condition(triplet('директор', P, Org)) :-
    edge(S, Org, 'target'),
    edge(S, P, 'director'),
    solution(S).
```

### 18.3. Проверка

```python
from pyagentprolog_expert import Expert, KnowledgeGraph

g = KnowledgeGraph.from_prolog(open("graph.pl").read())
e = Expert(graph=g, rules_file="rules.pl")

# 1. Простой запрос
qr = e.query("edge(X, 'технопарк_саратов', 'директор').")
assert qr.solutions == [{"X": "петров_петр"}]

# 2. Правило
qr = e.query("located_in('технопарк_казань', X).")
assert {s["X"] for s in qr.solutions} == {"казань", "россия"}

# 3. Лифтинг
qr = e.query(
    "edge('технопарк_казань', X, 'находиться_в').",
    category="transitive",
)
assert qr.lifted_from is not None
assert {s["X"] for s in qr.solutions} == {"казань", "россия"}

# 4. Список
qr = e.query("techpark_in_russia(X).")
assert {s["X"] for s in qr.solutions} == {
    "технопарк_саратов", "технопарк_казань",
}

# 5. label через attribute/3
qr = e.query("attribute('петров_петр', 'label', L).")
assert qr.solutions[0]["L"] == "Петров Пётр"

# 6. human_readable — схема
qr = e.query("human_readable('петров_петр', L).")
assert qr.solutions[0]["L"] == "Петров Пётр"

# 7. alias — схема
qr = e.query("alias('петров', F).")
assert qr.solutions[0]["F"] == "петров_петр"

# 8. solution — схема
qr = e.query("solution(S).")
assert "назначить_петрова" in {s["S"] for s in qr.solutions}

# 9. NL (если [nl])
ans = e.ask("Кто директор технопарка Саратов?")
print(ans.text)
# ✓ Решение:
# [1] X = Петров Пётр

# 10. why()
print(e.why())
```

---

## 19. Миграция со старого `Expert`

Старый `Expert` использовал `true_condition/1`, `false_condition/1`, `user_condition/1`. Новый — только граф.

| Старый | Новый |
|---|---|
| `true_condition(triplet(p, s, o))` | `edge(s, o, p)` в `graph.pl` |
| `false_condition(...)` | **не нужно** — `\+ edge(...)` |
| `user_condition(...)` | `edge(...)` в графе (через `assert_nl`) |
| `derive/1` | правило в `rules.pl` |
| `solution/1` + `condition/1` | `solution/1` + `condition/1` в `rules.pl` + данные (`node(S, [], solution)` + рёбра) в `graph.pl` |
| `human_readable('id', 'label').` в `rules.pl` | `attribute(Id, 'label', L)` в `graph.pl` + схема `human_readable/2` в `rules.pl` |
| `internal_glossary/2` | `alias_of` + `label` в `graph.pl` + схемы в `rules.pl` |

Старые `true_condition`/`false_condition`/`user_condition` **не** читаются `KnowledgeGraph` — перенесите их в `graph.pl` как `edge/3` и `attribute/3`.

### 19.1. Автоматический перенос

```python
"""migrate_domain_facts.py — переносит доменные факты из rules.pl в graph.pl."""
import re
from pyagentprolog_expert import KnowledgeGraph

rules_src = open("rules.pl").read()
g = KnowledgeGraph.from_prolog(open("graph.pl").read())

# human_readable/2 → attribute/3
for m in re.finditer(
    r"human_readable\(\s*'([^']+)'\s*,\s*'([^']*)'\s*\)\s*\.",
    rules_src,
):
    g.add_attribute(m.group(1), "label", m.group(2))

# alias/2 → edge/3
for m in re.finditer(
    r"alias\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)\s*\.",
    rules_src,
):
    g.add_edge(m.group(1), m.group(2), "alias_of")

open("graph.pl", "w").write(g.to_prolog())
```

После переноса — заменить `human_readable/2` и `alias/2`-факты в `rules.pl` на схемы (§13.7, §13.8).

---

## 20. Что дальше

- **API-справочник** — `README.md` пакета.
- **Формат графа** — «Формат графа знаний на Prolog» §2–§7.
- **NL-парсер** — «Документация пакета nl2prolog» §4, §9.
- **Движок** — «Полное руководство по PyAgentProlog» §7, §17.
- **Редактор** — «KnowledgeGraph Editor — руководство пользователя» §5, §9.

Расширение под домен:

```python
# в своём коде
from pyagentprolog_expert.rules_engine import _LIFT_PATTERNS
import re
_LIFT_PATTERNS += (
    (
        "ownership",
        re.compile(r"^edge\('(?P<s>[^']+)',\s*X,\s*'владеть'\)$"),
        lambda m: f"owns_transitively('{m.group('s')}', X)",
    ),
)
```

и правило в `rules.pl`:

```prolog
owns_transitively(X, Y) :- edge(X, Y, 'владеть').
owns_transitively(X, Y) :- edge(X, Z, 'владеть'), owns_transitively(Z, Y).
```

**Помните:** `rules.pl` — только схема. Данные о сущностях — в `graph.pl`. `Expert` в коде не знает ни одной сущности домена.