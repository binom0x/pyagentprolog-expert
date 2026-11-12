# pyagentprolog-expert

An expert system on a knowledge graph:
**PyAgentProlog** (inference engine) + **nl2prolog** (NL→query and NL→facts, optional).
**`kg-editor` is not required** — `KnowledgeGraph` is bundled with the package.

- The knowledge base is a Prolog-format knowledge graph: `node/3`, `edge/3`, `attribute/3`.
- Domain rules (`located_in/2`, `solution/1`, `human_readable/2`, …) live separately
  in `rules.pl` and are never serialised into the graph.
- NL questions and NL assertions — via `nl2prolog` (optional dependency).
- Low-level Prolog queries (`Expert.query`) work **without** `nl2prolog`.
- `kg_editor.KnowledgeGraph` compatibility is free, via duck-typing;
  `kg-editor` itself is **not** listed as a dependency.

---

## Table of contents

1. [Installation](#1-installation)
2. [Dependencies](#2-dependencies)
3. [Quick start](#3-quick-start)
4. [Knowledge-base format](#4-knowledge-base-format)
5. [Public API](#5-public-api)
6. [Query-lifting](#6-query-lifting)
7. [Dialog mode and coref](#7-dialog-mode-and-coref)
8. [Semantic unification](#8-semantic-unification)
9. [CLI](#9-cli)
10. [Compatibility with kg-editor](#10-compatibility-with-kg-editor)
11. [Architecture](#11-architecture)
12. [Extension](#12-extension)
13. [Diagnostics](#13-diagnostics)
14. [Development](#14-development)
15. [License](#15-license)

---

## 1. Installation

### Production (expert only)

```bash
pip install pyagentprolog-expert           # core: query / assert_facts_src
pip install "pyagentprolog-expert[nl]"     # + ask() / assert_nl()
pip install "pyagentprolog-expert[all]"    # + semantic
```

`kg-editor` is **not installed** — the editor/expert link is through a file
(`graph.pl`): the editor saves it, the expert reads it. See §10.

### From source

```bash
git clone https://github.com/andrey-vorfolomeev/pyagentprolog-expert.git
cd pyagentprolog-expert
pip install -e ".[nl,dev]"
```

### Requirements

- Python 3.10+
- `pyagentprolog` (installed automatically)
- `nl2prolog` — optional (`[nl]`)
- `sentence-transformers` — optional (`[semantic]`)

---

## 2. Dependencies

| Package | Required | What it gives you |
|---|---|---|
| `pyagentprolog` | **yes** | `Agent`, `stream` — the inference engine |
| `nl2prolog` | optional (`[nl]`) | `TextToProlog`, `DialogTurn` → `ask()` / `assert_nl()` |
| `sentence-transformers` | optional (`[semantic]`) | semantic unification |

**`kg-editor` is not required.** The expert works with a ready-made
`graph.pl` via the bundled `KnowledgeGraph` (see `graph.py`). If you already
have code using `kg_editor.KnowledgeGraph`, it will fit as `graph=...` in
`Expert` without installing the package (duck-typing: `Expert` only calls
`graph.to_prolog()` and `graph.merge(other)`).

### What works without extras

| API | Without `[nl]` | With `[nl]` |
|---|---|---|
| `Expert.query(prolog)` | ✅ | ✅ |
| `Expert.query(prolog, category=...)` | ✅ | ✅ |
| `Expert.assert_facts_src(src)` | ✅ | ✅ |
| `Expert.why()` | ✅ | ✅ |
| `Expert.reset()` | ✅ | ✅ |
| `Expert.ask(nl)` | ❌ `RuntimeError` | ✅ |
| `Expert.assert_nl(nl)` | ❌ `RuntimeError` | ✅ |
| `Expert.ask_interactive(nl)` | ❌ `RuntimeError` | ✅ |
| CLI `pa-expert` (everything except `!!assert`) | ✅ | ✅ |
| CLI `!!assert` | ❌ message | ✅ |

---

## 3. Quick start

### 3.1. Minimal example

```python
from pyagentprolog_expert import Expert, KnowledgeGraph

# 1. Load a ready-made graph
g = KnowledgeGraph.from_prolog(open("graph.pl", encoding="utf-8").read())

# 2. Create the expert (rules.pl is optional)
e = Expert(graph=g, rules_file="rules.pl")

# 3. Prolog query — works without nl2prolog
qr = e.query("edge(X, 'technopark_saratov', 'director').")
print(qr.solutions)
# [{'X': 'petrov_petr'}]

# 4. NL question — requires [nl]
ans = e.ask("Who is the director of the Saratov technopark?")
print(ans.text)
# ✓ Solution:
# [1] X = Petrov Petr Ivanovich

# 5. NL assertion → graph (additive) — requires [nl]
e.assert_nl("Elon Musk owns Tesla")

# 6. Explanation
print(e.why())
```

### 3.2. Building a graph from scratch

```python
from pyagentprolog_expert import Expert, KnowledgeGraph

g = KnowledgeGraph()
g.add_node("technopark_saratov", "technopark")
g.add_node("petrov_petr", "person")
g.add_edge("petrov_petr", "technopark_saratov", "director")
g.add_attribute("technopark_saratov", "founded_year", "2015")
g.add_attribute("petrov_petr", "label", "Petrov Petr Ivanovich")

e = Expert(graph=g)
print(e.query("edge('petrov_petr', X, 'director').").solutions)
# [{'X': 'technopark_saratov'}]
```

### 3.3. Query with lifting

```python
qr = e.query(
    "edge('technopark_kazan', X, 'located_in')",
    category="transitive",
)
# L1: edge('technopark_kazan', X, 'located_in')
# L2: located_in('technopark_kazan', X)   ← rules.pl applied
print(qr.solutions)      # [{'X': 'russia'}]
print(qr.lifted_from)    # "edge('technopark_kazan', X, 'located_in')."
```

### 3.4. CLI

```bash
pa-expert --graph graph.pl --rules rules.pl
```

```
[pa-expert] graph: {'nodes': 2, 'edges': 1, 'attributes': 0}
[pa-expert] rules: loaded
Commands: !!why, !!assert, !!graph, !!rules, !!reset, !!quit

> Who is the director of the Saratov technopark?
✓ Solution:
[1] X = Petrov Petr Ivanovich

> !!why
Query: edge(X, 'technopark_saratov', 'director').
Result: true
  [1] X=Petrov Petr Ivanovich

Sources of truth:
  • graph: {'nodes': 2, 'edges': 1, 'attributes': 0}
  • rules.pl: loaded
```

---

## 4. Knowledge-base format

### 4.1. Graph (`graph.pl`) — source of facts

```prolog
node(Id, Props, Type).              % node
edge(Source, Target, Predicate).    % edge
attribute(Entity, Name, Value).     % attribute (value is always a string)
```

Example:

```prolog
node('technopark_saratov', [], technopark).
node('petrov_petr', [], person).
node('technopark_kazan', [], technopark).
node('russia', [], place).
edge('petrov_petr', 'technopark_saratov', 'director').
edge('technopark_kazan', 'russia', 'located_in').
attribute('technopark_saratov', 'founded_year', '2015').
attribute('petrov_petr', 'label', 'Petrov Petr Ivanovich').
```

Serialisation rules (compatible with `kg-editor` and `nl2prolog`):

- `Id`, `Type`, `Predicate`, `Name` — without quotes if they are a valid atom
  (`[a-z][A-Za-z0-9_]*`), otherwise `'...'`.
- `Value` — **always** single-quoted, even numbers (`'2022'`).
- Compound IDs (`technopark_saratov`) are valid atoms, unquoted.
- Non-ASCII, spaces, uppercase — quoted.

### 4.2. Rules (`rules.pl`) — inference schema

`rules.pl` contains **only the schema** — rules applicable to any domain.
All domain facts (`label`, `alias`, `solution`, specific types) live in `graph.pl`.

```prolog
% Transitive closure
located_in(X, Y) :- edge(X, Y, 'located_in').
located_in(X, Y) :- edge(X, Z, 'located_in'), located_in(Z, Y).

% List by type
technopark_in_russia(T) :-
    node(T, _, technopark),
    located_in(T, 'russia').

% alias/2 — SCHEMA; data is edge(Short, Full, 'alias_of') in graph.pl
alias(Short, Full) :- edge(Short, Full, 'alias_of').

% human_readable/2 — SCHEMA; data is attribute(Id, 'label', L) in graph.pl
human_readable(Id, Label) :- attribute(Id, 'label', Label).

% solution/1 + condition/1 — SCHEMA; data is solution nodes + edges
solution(S) :- node(S, _, solution).
condition(triplet('director', P, Org)) :-
    edge(S, Org, 'target'),
    edge(S, P, 'director'),
    solution(S).
```

**Rules never enter the graph.** `KnowledgeGraph.from_prolog` silently
ignores them (per the "Knowledge Graph Format on Prolog" contract §2.6).
`Expert` loads `rules.pl` into `Agent` separately, per request.

### 4.3. Schema vs. data

| What | Where | Example |
|---|---|---|
| Entity facts | `graph.pl` | `node/3`, `edge/3`, `attribute/3` |
| Entity `label` | `graph.pl` | `attribute('petrov_petr', 'label', 'Petrov Petr Ivanovich')` |
| `alias` short→full | `graph.pl` | `edge('petrov', 'petrov_petr', 'alias_of')` |
| `solution` nodes | `graph.pl` | `node('appoint_petrov', [], solution)` + edges |
| Inference rules | `rules.pl` | `located_in/2`, `technopark_in_russia/1` |
| Schemas `alias/2`, `human_readable/2`, `solution/1` | `rules.pl` | wrappers over `attribute/3`, `edge/3`, `node/3` |

**Rule of thumb:** if a piece of knowledge is a fact about a particular entity,
it belongs in `graph.pl`; if a rule applies to any entity — it belongs in `rules.pl`.
`Expert` doesn't know any domain entities in code.

### 4.4. Program assembly contract for `Agent`

On each request, `Expert` creates a **fresh** `Agent` from the string:

```
graph.to_prolog()       # facts: node/3, edge/3, attribute/3
+ rules_src             # Horn clauses from rules.pl
+ _CONVENIENCE_RULES    # node/2, edge/2 — abbreviations
```

```prolog
node(Id, Type) :- node(Id, _, Type).
edge(S, T) :- edge(S, T, _).
```

Mutations (`assertz`/`retract`) inside a query **do not survive** the
query and never affect the graph. The source of truth is `Expert.graph`.

> A step-by-step guide to building a knowledge base (text → facts,
> common mistakes, recipes, migration from the old `Expert`) is in
> the separate document **"Expert Guide and Knowledge-Base Authoring"**.

---

## 5. Public API

### 5.1. `Expert`

```python
from pyagentprolog_expert import Expert

e = Expert(
    graph=None,               # KnowledgeGraph | None → empty
    rules_file=None,          # path to rules.pl
    t2p=None,                 # custom TextToProlog
    debug=False,
    semantic=False,           # enable semantics
    semantic_config=None,     # dict for enable_semantic
    session=None,             # Session | NullSession
)
```

#### `ask(nl, *, top_k=1, category=None, use_dialog=True) -> ExpertAnswer`

NL question → answer from the graph. Requires `[nl]`.

```python
ans = e.ask("Who is the director of the Saratov technopark?")
print(ans.text)
# ✓ Solution:
# [1] X = Petrov Petr Ivanovich

# With query-lifting
ans = e.ask("Which country is the Kazan technopark in?", category="transitive")
```

`use_dialog=True` uses `DialogTurn` (coref/ellipsis). If `use_dialog=False`,
`TextToProlog.parse` is used directly, stateless.

#### `query(prolog, *, category=None, lift=True) -> QueryResult`

Low-level Prolog query. Works **without** `[nl]`.

```python
qr = e.query("edge(X, 'technopark_saratov', 'director').")
if qr.ok:
    for sol in qr.solutions:
        print(sol["X"])

# With lifting
qr = e.query(
    "edge('technopark_kazan', X, 'located_in')",
    category="transitive",
)
print(qr.lifted_from)   # original L1
```

#### `assert_nl(nl) -> AssertResult`

NL assertion → extract facts → merge into the graph (additive). Requires `[nl]`.

```python
r = e.assert_nl("Elon Musk owns Tesla")
print(r.ok, r.added)
# True {'nodes': 2, 'edges': 1, 'attributes': 0}
```

#### `assert_facts_src(facts_src) -> AssertResult`

Add Prolog facts to the graph. Works **without** `[nl]`.

```python
r = e.assert_facts_src(
    "node('new_org', [], org).\n"
    "edge('new_org', 'technopark_saratov', 'partner').\n"
)
```

#### `why() -> str`

Explanation of the last answer.

```python
print(e.why())
# Query: edge(X, 'technopark_saratov', 'director').
# Result: true
#   [1] X=Petrov Petr Ivanovich
#
# Sources of truth:
#   • graph: {'nodes': 2, 'edges': 1, 'attributes': 0}
#   • rules.pl: loaded
```

#### `ask_interactive(nl, *, top_k=3, max_turns=10) -> str`

Clarification loop via `Session`. Requires `[nl]` and `Session`.

```python
from pyagentprolog_expert import Session

sess = Session()
e = Expert(graph=g, rules_file="rules.pl", session=sess)

# In the UI thread:
sess.poll()          # read questions
sess.send("yes")     # send answer
```

#### `reset() -> None`

Reset the last answer and caches. The graph is **not** touched.

#### Semantics

```python
e.enable_semantic({"model": "...", "threshold": 0.82})
e.disable_semantic()
print(e.semantic_status())
```

### 5.2. `KnowledgeGraph`

Full API — in `graph.py`. The essentials:

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
g.merge(other)                  # additive
g.merge_from_prolog(text)       # convenience wrapper
g.summary()                     # {'nodes': N, 'edges': N, 'attributes': N}
```

### 5.3. Result types

```python
@dataclass
class QueryResult:
    ok: bool
    query: str
    solutions: List[Dict[str, Any]]
    result: Optional[bool]          # True/False for ground queries
    error: Optional[str]
    lifted_from: Optional[str]      # original L1 if lifting occurred

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

`nl2prolog` emits **only L1 queries** (`edge/attribute/node/alias`).
Domain rules (`located_in/2`, `technopark_in_russia/1`) are L2/L3.
`Expert.query(category=...)` lifts L1→L2/L3 **if**:

1. the category matches one of the `rules_engine._LIFT_PATTERNS` entries;
2. the target predicate is **defined** in `rules.pl`
   (checked via `discover_rule_predicates`).

Otherwise the query stays L1 — `Agent` returns solutions from graph facts.

| Category | L1 | L2/L3 |
|---|---|---|
| `transitive` | `edge('X', Y, 'located_in')` | `located_in('X', Y)` |
| `list` | `edge(X, 'russia', 'located_in')` | `technopark_in_russia(X)` |

```python
# Without rules.pl located_in/2 — lifting is not applied
e = Expert(graph=g, rules_file=None)
qr = e.query("edge('a', X, 'located_in').", category="transitive")
print(qr.lifted_from)   # None — lifting did not fire
print(qr.query)         # edge('a', X, 'located_in').
```

### Adding lift patterns

`rules_engine._LIFT_PATTERNS` is a tuple of `(category, regex, builder)`.
Add your own:

```python
# in rules_engine.py
_LIFT_PATTERNS += (
    (
        "ownership",
        re.compile(r"^edge\('(?P<s>[^']+)',\s*X,\s*'owns'\)$"),
        lambda m: f"owns_transitively('{m.group('s')}', X)",
    ),
)
```

---

## 7. Dialog mode and coref

`Expert.ask(..., use_dialog=True)` uses `nl2prolog.DialogTurn`:

- **coreference**: "him/her/it" → `last_entity`;
- **ellipsis**: "And Kazan?" → substitutes `last_query`;
- **pending question**: if no answer, `DialogTurn` remembers the question
  and waits for clarification via `Session`.

```python
e.ask("Who is the director of the Saratov technopark?")
# ✓ Solution: [1] X = Petrov Petr Ivanovich

e.ask("How old is he?")
# DialogTurn._resolve_coreference substitutes 'petrov_petr'
```

### Disabling the dialog

```python
ans = e.ask("Who is the director?", use_dialog=False)
# Direct TextToProlog.parse(strict=True, facts_from_questions=False)
```

---

## 8. Semantic unification

Optional, on top of `PyAgentProlog.embedding_unify`.

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

Install: `pip install "pyagentprolog-expert[semantic]"`.

---

## 9. CLI

```bash
pa-expert --graph graph.pl --rules rules.pl [--debug]
```

| Command | Action |
|---|---|
| `<any text>` | `Expert.ask(text)` |
| `!!why` | explanation of the last answer |
| `!!assert` | NL assertion (interactive input) |
| `!!graph` | `graph.summary()` |
| `!!rules` | whether `rules.pl` is loaded |
| `!!reset` | `Expert.reset()` |
| `!!quit` / `!!exit` / `:q` | exit |

`!!assert` requires `[nl]`. The other commands work without `[nl]`.

---

## 10. Compatibility with kg-editor

The editor ↔ expert link is **through the file** `graph.pl`:

```
┌─────────────────┐   save    ┌──────────┐   read    ┌──────────────┐
│  kg-editor UI   │ ────────► │ graph.pl │ ────────► │ Expert       │
│  (editor)       │           └──────────┘           │ (production) │
└─────────────────┘                                  └──────────────┘
```

`kg-editor` is **not a dependency** of `pyagentprolog-expert`:

- not in `dependencies`;
- not in `optional-dependencies`;
- not imported by `graph.py`, `expert.py`, or `cli.py`.

### Duck-typing

If you **already have** code using `kg_editor.KnowledgeGraph`, it works as
`graph=...` without installing the package — `Expert` only calls
`graph.to_prolog()` and `graph.merge(other)`:

```python
from kg_editor.graph_model import KnowledgeGraph as KGEditor  # if installed
from pyagentprolog_expert import Expert

g = KGEditor.from_prolog(open("graph.pl").read())
e = Expert(graph=g)   # kg-editor is not needed in Expert's dependencies
```

`kg_editor.KnowledgeGraph.merge` accepts any object with `.nodes`, `.edges`,
`.attributes` — so the bundled `pyagentprolog_expert.KnowledgeGraph`
also fits.

### Compatibility test

`tests/test_kg_editor_compat.py` is skipped if `kg_editor` is not installed
(`pytest.importorskip`). CI does not require it.

---

## 11. Architecture

```
                    ┌──────────────────────────────┐
                    │  Expert                      │
                    │                              │
  NL question ─────►│  ask(nl)                     │
                    │    ├─ DialogTurn (coref)     │──► query: edge(...)
                    │    ├─ lift_query (category)  │
                    │    ├─ KnowledgeGraph ────────┼──► facts: node/edge/attr
                    │    ├─ rules.pl ──────────────┼──► rules: located_in/2 …
                    │    └─ Agent (fresh) ─────────┼──► solutions
                    │                              │
  NL assertion ────►│  assert_nl(nl)               │
                    │    ├─ TextToProlog.parse()   │──► facts_src
                    │    └─ graph.merge(...)       │──► graph
                    │                              │
  Prolog query ────►│  query(prolog)               │
                    │    └─ Agent (fresh)          │──► solutions
                    └──────────────────────────────┘
```

Package files:

| File | Role |
|---|---|
| `graph.py` | bundled `KnowledgeGraph` (API-compatible with `kg-editor`) |
| `expert.py` | `Expert`, `QueryResult`, `AssertResult`, `ExpertAnswer` |
| `rules_engine.py` | `load_rules`, `lift_query`, `discover_rule_predicates` |
| `humanize.py` | strip `_<N>` variable suffixes |
| `session.py` | `Session`, `NullSession` for `ask_interactive` |
| `cli.py` | `pa-expert` REPL |

---

## 12. Extension

### 12.1. Domain rules

All domain rules go in `rules.pl`, without touching the code.
Example — `src/pyagentprolog_expert/rules.pl.example`:

```bash
python -c "import pyagentprolog_expert, os; \
  print(os.path.dirname(pyagentprolog_expert.__file__))"
# → copy rules.pl.example from there to your rules.pl
```

### 12.2. Custom `TextToProlog`

```python
from pyagentprolog_expert import Expert

class MyT2P:
    def parse(self, text, **kwargs):
        return "", "edge(X, 'obj', 'pred')"

e = Expert(graph=g, t2p=MyT2P())
ans = e.ask("...")
```

### 12.3. Custom `generic_filter` for `KnowledgeGraph`

By default the bundled `KnowledgeGraph` does **not** filter (a ready-made
graph is already valid). If you build a graph via `Expert.assert_nl` and
want to drop service words, pass a filter:

```python
from pyagentprolog_expert import Expert, KnowledgeGraph

def my_filter(w: str) -> bool:
    return w in {"very", "this", "and"}

g = KnowledgeGraph(generic_filter=my_filter)
e = Expert(graph=g)
```

### 12.4. Your own lift patterns

See §6.

### 12.5. `label` for human-readable output

`Expert._describe_identifier` reads `attribute(Id, 'label', L)` from the
graph. Fallback — `humanize_vars(Id).replace('_', ' ')`.
There are no `human_readable/2` facts in `rules.pl` — only the **schema**:

```prolog
human_readable(Id, Label) :- attribute(Id, 'label', Label).
```

---

## 13. Diagnostics

### 13.1. `why()`

Explanation of the last answer: query, `lifted_from`, bindings,
`graph.summary()`, status of `rules.pl`.

### 13.2. `debug=True`

```python
e = Expert(graph=g, debug=True)
```

Prints `nl2prolog` and semantics initialisation, and internal errors.

### 13.3. Environment check

```python
import pyagentprolog_expert
print(pyagentprolog_expert.__version__)

try:
    import nl2prolog
    print("nl2prolog:", nl2prolog.__version__)
except ImportError:
    print("nl2prolog: not installed (ask/assert_nl unavailable)")

try:
    import prolog
    print("pyagentprolog: ok")
except ImportError:
    print("pyagentprolog: not installed")
```

### 13.4. Common errors

| Symptom | Cause | Fix |
|---|---|---|
| `RuntimeError: nl2prolog is not installed` | `ask()` without `[nl]` | `pip install "pyagentprolog-expert[nl]"` |
| `RuntimeError: pyagentprolog is not installed` | no `pyagentprolog` | `pip install pyagentprolog` |
| "No solutions" on a non-empty graph | case mismatch (`apple` ≠ `Apple`), lemma (`releases` ≠ `release`) | check `graph.to_prolog()` |
| Lifting does not fire | predicate missing in `rules.pl` | add `located_in/2` to `rules.pl` |
| `✗ Error: agent: …` | syntax error in `rules.pl` | run `pa-expert --debug` |
| `✗ dialog: …` | `nl2prolog.DialogTurn` fails to initialise | `pip install --force-reinstall "nl2prolog[ru]"` |
| `why()` shows IDs instead of labels | missing `attribute(Id, 'label', L)` | add it to `graph.pl` |

---

## 14. Development

```bash
# Install
pip install -e ".[nl,dev]"

# Tests (all except slow and kg_editor)
pytest -q -m "not slow and not kg_editor"

# Core only (without [nl])
pytest -q -m "not nl and not slow and not kg_editor"

# kg-editor compat only (if installed)
pip install kg-editor>=5.14
pytest -q tests/test_kg_editor_compat.py

# Lint
ruff check src tests
mypy src

# Build
python -m build
twine check dist/*
```

### Structure

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
    ├── test_kg_editor_compat.py
    └── test_no_domain_in_rules.py
```

### CI matrix

| Job | What it checks |
|---|---|
| `test (extras=nl)` | full suite except slow and kg_editor |
| `test (extras=all)` | + semantic |
| `test_core_only` | `[dev]` without `[nl]` — core works |
| `test_with_kg_editor` | compat tests, `continue-on-error: true` |
| `build` | `python -m build` + `twine check` |

---

## 15. License

MIT
