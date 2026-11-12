"""humanize — снятие _<N>-суффиксов переменных."""
from pyagentprolog_expert import (
    humanize_vars,
    is_var_like,
    strip_var_suffix,
)


def test_strip_suffix():
    assert strip_var_suffix("Лицо_693") == "Лицо"
    assert strip_var_suffix("Сделка_12") == "Сделка"
    assert strip_var_suffix("X_5") == "X"
    assert strip_var_suffix("без_суффикса") == "без_суффикса"


def test_humanize_alias():
    assert humanize_vars("Лицо_693") == "Лицо"


def test_is_var_like():
    assert is_var_like("Лицо_693")
    assert is_var_like("X_5")
    assert not is_var_like("Лицо")
    assert not is_var_like("apple")
