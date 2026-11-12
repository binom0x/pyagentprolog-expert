"""CLI — smoke-тесты."""
import os
import subprocess
import sys


def _run_cli(args, input_text=None):
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    # cli.py на Windows делает sys.stdout.reconfigure(encoding="utf-8"),
    # поэтому дочерний процесс пишет UTF-8. Декодируем тоже UTF-8.
    # encoding="utf-8" → input должен быть str (subprocess сам закодирует),
    # а не bytes — иначе TypeError: write() argument must be str, not bytes.
    return subprocess.run(
        [sys.executable, "-m", "pyagentprolog_expert.cli", *args],
        input=input_text,          # str, а не .encode("utf-8")
        capture_output=True,
        encoding="utf-8",
        timeout=30,
        env=env,
    )


def test_cli_help():
    r = _run_cli(["--help"])
    assert r.returncode == 0, r.stderr
    assert "graph" in r.stdout or "rules" in r.stdout


def test_cli_quit(tmp_path):
    """Пустой запуск, сразу !!quit."""
    graph = tmp_path / "graph.pl"
    graph.write_text("node(a, [], org).\n", encoding="utf-8")
    r = _run_cli(["--graph", str(graph)], input_text="!!quit\n")
    assert r.returncode == 0, r.stderr
    assert "graph" in r.stdout
