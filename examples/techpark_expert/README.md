# Технопарки РФ — экспертная система

Демонстрационный пример `pyagentprolog-expert`: граф знаний + правила
вывода + NL-интерфейс.

## Установка

```bash
pip install "pyagentprolog-expert[nl]"
```

## Запуск

```bash
# Базовый пример
python demo.py

# Интерактивный опрос
python interactive.py

# CLI
python -m pyagentprolog_expert.cli --graph graph.pl --rules rules.pl
```

## Что демонстрирует

| Возможность | Где |
|---|---|
| Граф знаний | `graph.pl` |
| Правила вывода | `rules.pl` |
| Query-lifting | `demo.py` §5–6 |
| NL-вопросы | `demo.py` §9 |
| NL-утверждения | `demo.py` §10 |
| Интерактивный опрос | `interactive.py` |
| Объяснимость | `demo.py` §11 |
| CLI | `cli_demo.ps1` |
| Тесты | `tests/test_techpark.py` |

## Схема vs данные

- `graph.pl` — **данные**: узлы, рёбра, атрибуты, `label`, `alias_of`, `solution`.
- `rules.pl` — **схема**: `located_in/2`, `techpark_in_russia/1`, `alias/2`,
  `human_readable/2`, `solution/1`, `condition/1`.

`Expert` в коде не знает ни одной сущности домена.

---


## Что показывает

1. **`demo.py`** — за 30 секунд показывает 11 возможностей.
2. **`interactive.py`** — Expert задаёт вопросы, пользователь отвечает,
   факты добавляются в граф, `why()` объясняет.
3. **CLI** — `pa-expert --graph graph.pl --rules rules.pl` → `Кто директор технопарка Саратов?`
4. **`pytest`** — эталонные вопросы, регрессия.

---

## Расширение примера

| Что | Как |
|---|---|
| Новый технопарк | добавить `node/3`, `edge/3`, `attribute/3` в `graph.pl` |
| Новый регион | `node('новый_регион', [], region)` + `edge(..., 'находиться_в')` |
| Новое правило | добавить в `rules.pl` (например, `technopark_in_region/2`) |
| Новый query-lifting | `_LIFT_PATTERNS += (...)` в `rules_engine.py` |
| NL-вопросы | `expert.ask("...")` |
| NL-утверждения | `expert.assert_nl("...")` |

**Главное:** `graph.pl` меняется, `rules.pl` — только при новых **типах** правил. Данные домена — в графе, схема — в правилах.