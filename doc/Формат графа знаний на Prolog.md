# Формат графа знаний на Prolog: техническое описание

Ниже — полное описание формата, который использует Knowledge Graph Editor (`node/3`, `edge/3`, `attribute/3`), и способов вывода/запросов на нём средствами Prolog (PyAgentProlog как движок). Документ опирается на текущий код `graph_model.py`, `app.py` и контракт с `nl2prolog._to_graph_program`.

---

## 1. Назначение и место в архитектуре

### 1.1. Роль формата

Формат — **единственный контракт** между тремя слоями:

| Слой | Что делает с форматом |
|---|---|
| `kg_editor.KnowledgeGraph` (`graph_model.py`) | Хранит в памяти, сериализует (`to_prolog`), десериализует (`from_prolog`), сливает (`merge`) |
| `nl2prolog` | Генерирует факты из NL-текста (`parse()` → `facts_src`), генерирует запросы (`extract_query()` → `query_src`) |
| `PyAgentProlog` (`prolog.agent.Agent`) | Исполняет запросы поверх фактов; возвращает `solutions` (биндинги переменных) |

Формат **стабилен** с v5.9 и не менялся ни в одном релизе до v5.14 включительно. Любое изменение — breaking change для всех трёх слоёв и для сохранённых `.pl`-файлов.

### 1.2. Что формат **не** описывает

- **Типы узлов** (`concept`, `person`, `org`, …) — это свободные атомы в третьем аргументе `node/3`. Никакой схемы/валидации на уровне Prolog нет.
- **Семантику предикатов** (`owns`, `produces`, `releases`) — это свободные атомы в третьем аргументе `edge/3`. Никакого словаря/онтологии на уровне Prolog нет.
- **Атрибуты** — плоские тройки `(entity, name, value)`, без вложенности и без типов значений (всё строки).
- **Правила предметной области** — формат допускает произвольные Horn-клаузы (см. §5), но редактор их не генерирует и не валидирует; он только **не ломает** их при `from_prolog`/`to_prolog`? — нет, ломает: `from_prolog` игнорирует всё, кроме `node/3`, `edge/3`, `attribute/3` (см. §2.6).

---

## 2. Базовые предикаты формата

### 2.1. `node/3` — узел

```prolog
node(Id, Props, Type).
```

| Аргумент | Тип | Семантика | Ограничения |
|---|---|---|---|
| `Id` | атом или `'...'` | Уникальный идентификатор узла | Непустой; не служебное слово (см. §3.2); `[a-z][A-Za-z0-9_]*` → без кавычек |
| `Props` | список `[k=v, ...]` или `[]` | Произвольные свойства узла | Ключи — атомы; значения — строки в `'...'` |
| `Type` | атом или `'...'` | Тип узла | Свободный атом; по умолчанию `concept` |

**Примеры:**

```prolog
node(apple, [], org).
node('российская_федерация', [], place).       % compound-ID — валидный атом, без кавычек
node('тихий_океан', [], place).                % compound-ID
node('ООО «Ромашка»', [inn='1234567890'], org). % кириллица + пробелы → в кавычках
node(x_1, [weight='0.5'], concept).            % props
```

**Инварианты:**
- `Id` уникален в графе. `add_node` с существующим `Id` **обновляет** `Type` и **дополняет** `Props` (не перезаписывает целиком).
- `Props` может быть пустым списком `[]`.
- `Type` может отсутствовать — тогда используется `concept`.

### 2.2. `edge/3` — ребро

```prolog
edge(Source, Target, Predicate).
```

| Аргумент | Тип | Семантика | Ограничения |
|---|---|---|---|
| `Source` | атом или `'...'` | Источник (id узла) | Непустой; не служебное слово; узел создаётся автоматически, если нет |
| `Target` | атом или `'...'` | Цель (id узла) | То же |
| `Predicate` | атом или `'...'` | Метка связи | Непустой; **не** фильтруется `generic_filter` |

**Примеры:**

```prolog
edge(apple, iphone, releases).
edge(elon_musk, spacex, owns).
edge('регулятор', 'лицензия', 'выдавать').     % кириллица → в кавычках
edge('технопарк_москва', 'москва', 'находиться_в').
```

**Инварианты:**
- Рёбра **направленные**. Обратное ребро — отдельный факт.
- `Predicate` — свободный атом; лемматизация — ответственность `nl2prolog`, не формата.
- Дубликаты `(Source, Target, Predicate)` **не создаются** `add_edge`; но в файле могут быть — `from_prolog` их сохранит (дедуп только в `merge`, см. §4.5).
- `Source`/`Target`, которых нет в графе, создаются как `node(..., [], concept)`.

### 2.3. `attribute/3` — атрибут

```prolog
attribute(Entity, Name, Value).
```

| Аргумент | Тип | Семантика | Ограничения |
|---|---|---|---|
| `Entity` | атом или `'...'` | Id узла-владельца | Непустой; не служебное слово; узел создаётся автоматически |
| `Name` | атом или `'...'` | Имя атрибута | Непустое; **не** фильтруется `generic_filter` |
| `Value` | **всегда** `'...'` | Значение | Строка; кавычки обязательны |

**Примеры:**

```prolog
attribute(iphone, release_year, '2022').
attribute(spacex, industry, 'aerospace').
attribute('документ_1863', 'срок', '2022-12-31').
attribute('российская_федерация', 'код', 'RU').
```

**Инварианты:**
- `Value` — **всегда** строка в одинарных кавычках, даже если это число (`'2022'`, не `2022`).
- `Name` — свободный атом; `ATTR_LABEL_NOUNS` (в `nl2prolog`) — это эвристика парсера, не ограничение формата.
- Атрибуты **не** дедуплицируются `add_attribute`; дедуп только в `merge` (по полному ключу `(entity, name, value)`).

### 2.4. Что **не** входит в базовый формат

| Конструкция | Почему не входит |
|---|---|
| `alias/2`, `belongs_to/2`, `requirement/3` | Roadmap (P1.3, P1.6, P2.4); сегодня — только `edge/3` |
| `type_hierarchy/2` (наследование типов) | Нет; тип — плоский атом в `node/3` |
| `weight/2` для рёбер | Нет; вес ребра можно положить в `node/3`-props, но не в `edge/3` |
| Отрицание, дизъюнкция | Только через правила (см. §5) |
| Модальность (`must`, `may`) | Roadmap P2.4; сегодня — через `edge/3` с предикатом `must`/`may` |

### 2.5. Каноническая сериализация (`to_prolog`)

`KnowledgeGraph.to_prolog()` пишет факты в порядке:

1. Все `node/3` (в порядке вставки в `dict`).
2. Все `edge/3` (в порядке вставки в `list`).
3. Все `attribute/3` (в порядке вставки в `list`).

**Правила кавычек (`_atom`):**

```python
_VALID_ATOM = re.compile(r"^[a-z][A-Za-z0-9_]*$")
_RESERVED_ATOMS = {"is", "mod", "div", "rem", "xor", "not"}

def _atom(s):
    return s if _VALID_ATOM.match(s) and s not in _RESERVED_ATOMS else _quote(s)
```

То есть:
- `apple`, `elon_musk`, `российская_федерация` (нижний регистр + `_` + цифры) → **без кавычек**.
- `Apple`, `ООО Ромашка`, `is`, `x-1` (верхний регистр, пробелы, зарезервированные, дефисы) → **в кавычках**.
- `Value` в `attribute/3` — **всегда** в кавычках (`_quote`).

**Пример полного файла:**

```prolog
node(apple, [], org).
node(iphone, [], thing).
node(smartphone, [], concept).
node(elon_musk, [], person).
node(spacex, [], org).
edge(apple, iphone, releases).
edge(apple, smartphone, produces).
edge(elon_musk, spacex, owns).
attribute(iphone, release_year, '2022').
attribute(spacex, industry, 'aerospace').
```

### 2.6. Каноническая десериализация (`from_prolog`)

`KnowledgeGraph.from_prolog(text)`:

1. Режет текст на клаузы по `.` на верхнем уровне скобок (учёт строк, комментариев `%`, `/* */`).
2. Для каждой клаузы матчит `^([a-z][A-Za-z0-9_]*)\s*\((.*)\)$`.
3. Обрабатывает **только** `node/3`, `edge/3`, `attribute/3`:
   - `node/3` → `add_node(id, type, props)`
   - `node/2` → `add_node(id, type)` (совместимость)
   - `node/1` → `add_node(id)` (совместимость)
   - `edge/3` → `add_edge(src, tgt, pred)`
   - `attribute/3` → `add_attribute(entity, name, value)`
4. **Всё остальное молча игнорируется** — правила, `alias/2`, `belongs_to/2`, произвольные Horn-клаузы.

**Важное следствие:** если пользователь вставил в «📥 Импорт из Prolog» правила (`owns(X, Y) :- ...`), они **не сохранятся** в графе. Для запросов правила добавляются отдельно через `_CONVENIENCE_RULES` (см. §5.1) — но **не** через `from_prolog`.

**Толерантность к ошибкам:** каждое `add_*` в `_apply_clause` обёрнуто в `try/except`; битая клауза пропускается, остальные обрабатываются. Это важно для merge (см. §4.5).

---

## 3. Ограничения на атомы

### 3.1. Синтаксис атома (ISO Prolog, упрощённый)

Атом без кавычек:
```
lowercase_letter ( letter | digit | _ )*
```

- Первый символ — строчная латинская буква `a–z`.
- Далее — латинские буквы (оба регистра), цифры, `_`.
- Кириллица, пробелы, дефисы, точки, `/`, `:` — **только в кавычках**.

Атом в кавычках:
```
'...'
```
- Внутри — любые символы, кроме неэкранированных `'` и `\`.
- Экранирование: `\'` → `'`, `\\` → `\`.

### 3.2. `generic_filter` — что **нельзя** сделать узлом

`graph_model._default_generic_filter` (v5.12, 3-уровневый fallback: `local noise.py` → `nl2prolog.noise` → disabled):

```python
def _default_generic_filter(w):
    if not w: return True
    if _is_service_word is None: return False      # фильтр отключён
    if '_' in w: return False                      # compound-ID разрешены
    for lang in ('ru', 'en'):
        if _is_service_word(w, lang): return True
    return False
```

**Правила:**

| Случай | Результат |
|---|---|
| Пустая строка | `True` (фильтруется) |
| `_is_service_word is None` (нет `noise.py` и нет `nl2prolog`) | `False` (разрешает всё) |
| `'_' in w` (compound-ID) | `False` (**не** фильтруется, даже если первый компонент — служебное слово) |
| `is_service_word(w, 'ru')` или `(w, 'en')` | `True` |
| Иначе | `False` |

**Следствия для формата:**

- `node(очень, [], concept).` — `add_node` бросит `ValueError`.
- `node('российская_федерация', [], place).` — пройдёт (compound-ID).
- `node('ООО «Ромашка»', [], org).` — пройдёт, если `ООО` не служебное (обычно нет).
- `edge(apple, iphone, releases).` — `Source`/`Target` проверяются, `Predicate` — нет (можно `edge(a, b, очень)`).
- `attribute(apple, очень, 'true').` — `Entity` проверяется, `Name` — нет.

**Правило:** `generic_filter` — защита от мусора в `Id` и `Source`/`Target`, а не валидатор формата. Предикаты и имена атрибутов — на совести пользователя.

### 3.3. `_RESERVED_ATOMS`

`is`, `mod`, `div`, `rem`, `xor`, `not` — даже если валидны синтаксически, при сериализации **всегда** в кавычках (`_atom`). Это защита от конфликта с ISO-операторами Prolog.

При `from_prolog` они принимаются как обычные атомы — но при повторной записи получат кавычки.

---

## 4. Семантика операций над графом

### 4.1. `add_node` — upsert

```python
def add_node(self, node_id, node_type="concept", props=None):
    if not node_id: raise ValueError
    if self._generic_filter(node_id): raise ValueError
    if node_id in self.nodes:
        self.nodes[node_id].type = node_type      # перезапись типа
        if props: self.nodes[node_id].props.update(props)  # дополнение props
    else:
        self.nodes[node_id] = Node(node_id, node_type, dict(props or {}))
    return self.nodes[node_id]
```

- Существующий узел: **тип перезаписывается**, **props дополняются** (не заменяются).
- Несуществующий: создаётся.

### 4.2. `add_edge` — append с автосозданием

```python
def add_edge(self, source, target, predicate):
    if not (source and target and predicate): raise ValueError
    if self._generic_filter(source): raise ValueError
    if self._generic_filter(target): raise ValueError
    if source not in self.nodes: self.add_node(source)
    if target not in self.nodes: self.add_node(target)
    self.edges.append(Edge(source, target, predicate))
```

- Автосоздаёт `Source`/`Target` как `node(..., [], concept)`, если их нет.
- **Не** дедуплицирует — повторный вызов добавит дубликат.

### 4.3. `add_attribute` — append с автосозданием

```python
def add_attribute(self, entity, name, value):
    if not (entity and name): raise ValueError
    if self._generic_filter(entity): raise ValueError
    if entity not in self.nodes: self.add_node(entity)
    self.attributes.append(Attribute(entity, name, value))
```

- `Value` может быть пустой строкой (не проверяется).
- **Не** дедуплицирует.

### 4.4. `remove_node` — каскадное удаление

```python
def remove_node(self, node_id):
    if node_id not in self.nodes: return False
    del self.nodes[node_id]
    self.edges = [e for e in self.edges if e.source != node_id and e.target != node_id]
    self.attributes = [a for a in self.attributes if a.entity != node_id]
```

Удаляет узел **и все** инцидентные рёбра, **и все** атрибуты с этим `entity`.

### 4.5. `merge(other)` — аддитивное слияние (v5.14)

```python
def merge(self, other):
    stats = {"added_nodes": 0, "skipped_nodes": 0,
             "added_edges": 0, "skipped_edges": 0,
             "added_attributes": 0, "skipped_attributes": 0}
    # Узлы: только отсутствующие; существующие не трогаются
    for nid, n in other.nodes.items():
        if nid in self.nodes: stats["skipped_nodes"] += 1; continue
        try: self.add_node(nid, n.type, n.props); stats["added_nodes"] += 1
        except: stats["skipped_nodes"] += 1
    # Рёбра: дедуп по (src, tgt, pred)
    existing = {(e.source, e.target, e.predicate) for e in self.edges}
    for e in other.edges:
        key = (e.source, e.target, e.predicate)
        if key in existing: stats["skipped_edges"] += 1; continue
        try: self.add_edge(...); existing.add(key); stats["added_edges"] += 1
        except: stats["skipped_edges"] += 1
    # Атрибуты: дедуп по (entity, name, value)
    ...
```

**Семантика:**

| Аспект | Поведение |
|---|---|
| Узлы | Добавляются только отсутствующие. Тип и props существующих **не меняются**. |
| Рёбра | Дедуп по `(source, target, predicate)`. |
| Атрибуты | Дедуп по `(entity, name, value)`. Разные `value` при том же `(entity, name)` — оба останутся. |
| `generic_filter` | Применяется к входящим (`add_node` бросит → `skipped_*`). |
| Ошибки по элементу | `try/except` + `skipped_*`, цикл не прерывается. |

### 4.6. Инварианты графа

| Инвариант | Гарантия |
|---|---|
| `Id` уникален | `dict` по `Id` |
| `edge.Source` и `edge.Target` есть в `nodes` | `add_edge` автосоздаёт; `from_prolog` тоже |
| `attribute.Entity` есть в `nodes` | `add_attribute` автосоздаёт |
| `Id` не служебное слово | `generic_filter` в `add_node` / `add_edge` / `add_attribute` |
| Compound-ID (`'_' in w`) разрешён | `_default_generic_filter` п.3 |

Нарушение инварианта возможно **только** прямой мутацией полей (`g.nodes[x] = ...`) — API это не разрешает.

---

## 5. Способы вывода (запросов) на графе

### 5.1. Движок и «удобные правила»

Движок — **PyAgentProlog** (`prolog.agent.Agent`). На каждый запрос создаётся **свежий** агент:

```python
src = g.to_prolog() + _CONVENIENCE_RULES
agent = Agent(src, context={})
for item in agent.stream(q):
    ...
```

`_CONVENIENCE_RULES` (добавляются **только** в рантайме запроса, не сохраняются в граф):

```prolog
% --- convenience rules (добавлены редактором) ---
node(Id, Type) :- node(Id, _, Type).
edge(S, T) :- edge(S, T, _).
```

**Зачем:** `node/2` и `edge/2` — сокращения. `node(apple, T)` работает без указания `Props`; `edge(S, T)` — без указания предиката.

**Важно:** эти правила **не** сериализуются в `.pl` (в `to_prolog()` их нет) и **не** попадают в `Prolog source` в UI. Они добавляются только в строку `src`, которую получает `Agent`.

### 5.2. Базовые запросы

#### 5.2.1. `node/2`, `node/3`

```prolog
% Все узлы с типами
node(Id, Type).

% Тип конкретного узла
node(apple, T).
% → T = org

% Все узлы типа person
node(X, person).
% → X = elon_musk

% Полная форма (с props) — в обход convenience rules
node(apple, Props, Type).
% → Props = [], Type = org

% Узлы с непустыми props
node(Id, Props, _), Props \= [].
```

#### 5.2.2. `edge/2`, `edge/3`

```prolog
% Все рёбра (source, target)
edge(S, T).

% Все рёбра с предикатом
edge(S, T, owns).
% → S = elon_musk, T = spacex

% Исходящие рёбра узла
edge(apple, X, _).
% → X = iphone ; X = smartphone

% Входящие рёбра узла
edge(X, iphone, _).
% → X = apple

% Конкретное ребро
edge(apple, iphone, releases).
% → true
```

#### 5.2.3. `attribute/3`

```prolog
% Все атрибуты
attribute(E, N, V).

% Атрибуты конкретной сущности
attribute(iphone, N, V).
% → N = release_year, V = '2022'

% Значение конкретного атрибута
attribute(iphone, release_year, V).
% → V = '2022'

% Поиск по значению
attribute(E, N, 'aerospace').
% → E = spacex, N = industry

% Числовое сравнение (значения — строки, нужен atom_number/2)
attribute(iphone, release_year, V), atom_number(V, Year), Year > 2020.
% → V = '2022', Year = 2022
```

### 5.3. Соединение (join) фактов

```prolog
% Кто владеет организациями, производящими смартфоны?
edge(Owner, Org, owns),
edge(Org, smartphone, produces).
% → Owner = elon_musk? Нет — apple производит smartphone, но владелец apple не задан.
% → Решений нет (пусто).

% Все рёбра между узлами типа org и thing
node(S, org), node(T, thing), edge(S, T, _).
% → S=apple, T=iphone
```

**Правило:** join — стандартный Prolog. Никаких ограничений, кроме лимита решений (`_SOLUTION_LIMIT = 1000`).

### 5.4. Отрицание

```prolog
% Узлы, у которых нет исходящих рёбер
node(X, _), \+ edge(X, _, _).

% Узлы без атрибутов
node(X, _), \+ attribute(X, _, _).

% Рёбра без петель
edge(A, B, _), \+ (A = B).
```

**Правило:** `\+` — negation as failure. Работает на ground-целях; на переменных может давать неожиданные результаты (стандартное поведение Prolog).

### 5.5. Агрегация: `findall/3`, `setof/3`, `bagof/3`

```prolog
% Все цели рёбер apple
findall(X, edge(apple, X, _), L).
% → L = [iphone, smartphone]

% Все узлы типа org
findall(X, node(X, org), L).
% → L = [apple, spacex]

% Все предикаты, использованные в графе
setof(P, S^T^edge(S, T, P), Ps).
% → Ps = [owns, produces, releases]

% Количество узлов
findall(X, node(X, _), L), length(L, N).
% → N = 5

% Количество рёбер
findall(_, edge(_, _, _), L), length(L, N).
% → N = 3

% Степень узла (исходящие + входящие)
findall(X, (edge(apple, X, _) ; edge(X, apple, _)), L), length(L, D).
% → D = 3 (iphone, smartphone, с учётом дублей — см. ниже)
```

**Осторожно:** `findall` **не** дедуплицирует. Для дедупа — `setof` или `sort/2`:

```prolog
findall(X, (edge(apple, X, _) ; edge(X, apple, _)), L0),
sort(L0, L).
```

### 5.6. Рекурсивные запросы (транзитивное замыкание)

Формат **допускает** рекурсивные правила в рантайме запроса. Но `_CONVENIENCE_RULES` их не добавляет — нужно **дописывать в `query_in`** через `assertz` или включать в `src` (см. §5.7).

**Пример: транзитивное замыкание по `edge/3`**

```prolog
% В query_in:
assertz((reachable(X, Y) :- edge(X, Y, _))),
assertz((reachable(X, Y) :- edge(X, Z, _), reachable(Z, Y))),
findall(Y, reachable(apple, Y), L).
```

**Осторожно:** `assertz` в PyAgentProlog живёт **только в рамках одного запроса** (свежий агент на каждый вызов). Это **не** мутация графа — `g.to_prolog()` не меняется.

**Альтернатива — без `assertz`:** использовать `findall` + рекурсию на стороне Python (обход `g.edges`). Для графа знаний это часто проще и предсказуемее.

### 5.7. Сложные запросы с правилами в `src`

Если правил много и они переиспользуются — можно **дописать их в `src`** перед созданием агента. Но это требует правки `h_query` (сейчас `_graph_to_program` жёстко = `g.to_prolog() + _CONVENIENCE_RULES`).

**Пример (потребует патча `h_query`):**

```python
def h_query(g, text, extra_rules=""):
    src = g.to_prolog() + _CONVENIENCE_RULES + extra_rules
    agent = Agent(src, context={})
    ...
```

**Правило:** правила в `extra_rules` — **только** Horn-клаузы, не факты. Факты — в `g`.

### 5.8. Ограничения движка (PyAgentProlog)

| Ограничение | Значение | Как обойти |
|---|---|---|
| Лимит решений | `_SOLUTION_LIMIT = 1000` | Уменьшить кардинальность запроса (`node/3` + фильтр вместо `edge/2`) |
| Мутации (`assertz`/`retract`) | Живут **только** в рамках одного запроса | Не пытаться «сохранить» правило в граф — `g.to_prolog()` не меняется |
| `node/2`, `edge/2` | Работают только благодаря `_CONVENIENCE_RULES` | Если их убрать из `src` — запросы `node(X, T)` перестанут работать |
| Тип `Props` | `[k=v, ...]`; не унифицируется как обычный список без `=` | `member(k=v, Props)` работает; `member(K-V, Props)` — нет |
| Числа в `attribute/3` | Всегда строки | `atom_number(V, N)` для сравнения |
| Рекурсия | Поддерживается | Но `assertz` для правил — только в рамках запроса |

---

## 6. Примеры: от фактов к выводу

### 6.1. Полный граф

```prolog
node(apple, [], org).
node(iphone, [], thing).
node(smartphone, [], concept).
node(elon_musk, [], person).
node(spacex, [], org).
edge(apple, iphone, releases).
edge(apple, smartphone, produces).
edge(elon_musk, spacex, owns).
attribute(iphone, release_year, '2022').
attribute(spacex, industry, 'aerospace').
```

### 6.2. Запросы и результаты

| Запрос | Результат |
|---|---|
| `node(apple, T).` | `T = org` |
| `node(X, person).` | `X = elon_musk` |
| `edge(X, Y, owns).` | `X = elon_musk, Y = spacex` |
| `edge(apple, X, _).` | `X = iphone` ; `X = smartphone` |
| `edge(X, _, _), \+ (X = apple).` | `X = elon_musk` |
| `attribute(iphone, N, V).` | `N = release_year, V = '2022'` |
| `findall(X, edge(apple, X, _), L).` | `L = [iphone, smartphone]` |
| `findall(X, node(X, org), L).` | `L = [apple, spacex]` |
| `setof(P, S^T^edge(S, T, P), Ps).` | `Ps = [owns, produces, releases]` |
| `node(S, org), node(T, thing), edge(S, T, _).` | `S = apple, T = iphone` |
| `\+ edge(spacex, _, _).` | `true` (у spacex нет исходящих) |

### 6.3. Более сложный: «кто владеет организацией, производящей X?»

```prolog
edge(Owner, Org, owns),
edge(Org, Product, produces).
```

С текущим демо-графом — **пусто** (у `apple` нет владельца). Если добавить:

```prolog
edge(steve_jobs, apple, owns).
node(steve_jobs, [], person).
```

то запрос вернёт `Owner = steve_jobs, Org = apple, Product = smartphone`.

### 6.4. Транзитивное замыкание (через `assertz` в запросе)

```prolog
assertz((ancestor(X, Y) :- edge(X, Y, owns))),
assertz((ancestor(X, Y) :- edge(X, Z, owns), ancestor(Z, Y))),
findall(Y, ancestor(elon_musk, Y), L).
```

С демо-графом: `L = [spacex]`. Если добавить `edge(spacex, twitter, owns)`, то `L = [spacex, twitter]`.

---

## 7. Расширение формата (правила добавления)

### 7.1. Что можно добавлять без breaking change

| Что | Как | Обратная совместимость |
|---|---|---|
| Новый предикат (`alias/2`, `belongs_to/2`) | Через `edge/3` с предикатом `alias`/`belongs_to` | ✅ Старые `.pl` читаются, новые факты — просто `edge/3` |
| Новый тип узла (`document`, `law`) | Свободный атом в `node/3` | ✅ |
| Новый атрибут | `attribute/3` | ✅ |
| Правило предметной области | Добавить в `_CONVENIENCE_RULES` или в `extra_rules` | ✅ (не сериализуется в `.pl`) |

### 7.2. Что **нельзя** добавлять без breaking change

| Что | Почему |
|---|---|
| `node/4` (4-й аргумент) | `from_prolog` игнорирует; `to_prolog` не пишет |
| `edge/4` (вес ребра) | То же |
| Вложенные `Props` (`[k=[...]]`) | `_parse_props` не поддерживает |
| Типизированные `Value` (`attribute(e, n, 42)`) | `to_prolog` всегда кавычит; `from_prolog` парсит как строку |
| Правила в `.pl` | `from_prolog` их **молча выбросит** при повторном сохранении |

**Правило:** любой новый предикат — **только** через `node/3`, `edge/3`, `attribute/3`. Если нужен `alias/2` — это `edge(X, Y, alias)`.

### 7.3. Roadmap расширений (из хронологии)

| # | Расширение | Формат | Статус |
|---|---|---|---|
| P1.2 | `<документ> № <число>` | `node('постановление_1863', [], document)` + `edge` | TODO |
| P1.3 | `<АББРЕВИАТУРА> — <расшифровка>` | `edge('рф', 'российская_федерация', alias)` | TODO |
| P1.6 | Генитивный владелец | `edge(X, Y, belongs_to)` | TODO |
| P2.4 | Модальность | `edge(X, Y, must)` / `edge(X, Y, may)` | TODO |
| P3.1 | Merge-политики | Не формат, а API `merge` | TODO |

---

## 8. Диагностика и типичные ошибки

### 8.1. Ошибки сериализации

| Симптом | Причина | Решение |
|---|---|---|
| `ValueError: «очень» — служебное слово` | `add_node("очень")` | Использовать compound-ID (`очень_важный`) или отключить фильтр (`generic_filter=lambda w: False`) |
| `ValueError: source/target/predicate не могут быть пустыми` | Пустая строка в `add_edge` | Проверить входные данные |
| `ValueError: id узла пустой` | `add_node("")` | То же |

### 8.2. Ошибки парсинга `.pl`

| Симптом | Причина | Решение |
|---|---|---|
| Факты пропали после сохранения | В файле были правила (`f(X) :- ...`), `from_prolog` их выбросил | Хранить правила отдельно; в `.pl` — только факты |
| `attribute(e, n, 42)` → `value='42'` | `to_prolog` всегда кавычит | Ожидаемо; для чисел — `atom_number/2` в запросе |
| Кириллица без кавычек | `_VALID_ATOM` требует `[a-z]` в начале | Всегда кавычить кириллицу (`'регулятор'`) |
| `node(apple, [weight=0.5], concept)` | `Props` значение без кавычек | `_parse_props` берёт как есть; `to_prolog` запишет `weight='0.5'` |

### 8.3. Ошибки запросов

| Симптом | Причина | Решение |
|---|---|---|
| `node(X, T)` → ошибка | Нет `_CONVENIENCE_RULES` в `src` | Проверить `_graph_to_program` |
| `edge(X, Y, 'выдает')` не находит | Предикат в KB `'выдавать'` (лемматизированный) | Использовать лемму |
| `attribute(e, n, 2022)` не находит | `Value` — строка `'2022'` | `attribute(e, n, '2022')` или `atom_number` |
| Пустой результат при непустом графе | Регистрозависимость (`apple` ≠ `Apple`) | Проверить `to_prolog` |
| `assertz` «не сохраняется» | Мутации живут только в рамках запроса | Не пытаться сохранить правило в граф |

---

## 9. Сводка: что важно помнить

1. **Три предиката, ничего больше.** `node/3`, `edge/3`, `attribute/3`. Всё остальное — либо `_CONVENIENCE_RULES` в рантайме, либо игнорируется `from_prolog`.
2. **`Value` — всегда строка.** Даже числа. Для сравнения — `atom_number/2`.
3. **`Predicate` и `Name` — свободные атомы.** `generic_filter` их не проверяет.
4. **`Id` и `Source`/`Target` — проверяются `generic_filter`.** Compound-ID (`'_' in w`) разрешены.
5. **`node/2`, `edge/2` работают только благодаря `_CONVENIENCE_RULES`.** В `.pl` их нет.
6. **Правила в `.pl` не сохраняются.** `from_prolog` их выбрасывает. Для запросов — `_CONVENIENCE_RULES` + `assertz` в рамках запроса.
7. **`merge` аддитивен.** Существующие узлы не перезаписываются; дедуп по полному ключу.
8. **`to_prolog` кавычит всё, что не `[a-z][A-Za-z0-9_]*`.** Кириллица, пробелы, заглавные — в кавычках.
9. **`from_prolog` толерантен к ошибкам.** Битая клауза пропускается, остальные обрабатываются.
10. **Один запрос — один свежий агент.** Мутации (`assertz`) не влияют на граф и не переживают запрос.

---

*Документ описывает формат v5.14 (совместим с v5.9+). При добавлении новых предикатов через `edge/3` (P1.3, P1.6, P2.4) — дополнить §7.3. При изменении `_CONVENIENCE_RULES` — обновить §5.1 и §5.8.*