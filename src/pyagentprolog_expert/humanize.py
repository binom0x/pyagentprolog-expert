"""humanize.py — человекочитаемое представление переменных PyAgentProlog.

PyAgentProlog при переименовании переменных в правилах добавляет суффикс
`_<N>`: `Лицо_693`, `Сделка_12`, `X_5`. Эти имена попадают в solutions и
выглядят шумно. Модуль снимает суффиксы.

Публичный API:
    strip_var_suffix(text) -> str
    humanize_vars(text) -> str        # алиас
    is_var_like(name) -> bool
"""
from __future__ import annotations

import re

_VAR_SUFFIX_RE = re.compile(r'\b([А-ЯЁA-Z][А-Яа-яЁёA-Za-z0-9]*)_(\d+)\b')
_VAR_LIKE_RE = re.compile(r'^[А-ЯЁA-Z][А-Яа-яЁёA-Za-z0-9]*_\d+$')


def strip_var_suffix(text: str) -> str:
    """Лицо_693 -> Лицо, Сделка_12 -> Сделка, X_5 -> X."""
    if not text:
        return text
    return _VAR_SUFFIX_RE.sub(r'\1', text)


def humanize_vars(text: str) -> str:
    """Алиас strip_var_suffix (совместимость со старым API)."""
    return strip_var_suffix(text)


def is_var_like(name: str) -> bool:
    """Похоже ли имя на переименованную Prolog-переменную (Лицо_693)."""
    return bool(name) and bool(_VAR_LIKE_RE.match(name))


__all__ = ["humanize_vars", "is_var_like", "strip_var_suffix"]
