"""README install instructions must match how the SDK is actually distributed.

The SDK is not published on PyPI (https://pypi.org/pypi/jarvis-command-sdk/json is 404),
so the README must not tell users to ``pip install jarvis-command-sdk``; it must point at
the git repo instead.
"""

from pathlib import Path

README = Path(__file__).resolve().parent.parent / "README.md"


def _install_block() -> str:
    text = README.read_text(encoding="utf-8")
    start = text.index("## Installation")
    end = text.index("## ", start + 1)
    return text[start:end]


def test_readme_does_not_advertise_pypi_install():
    block = _install_block()
    assert "pip install jarvis-command-sdk" not in block


def test_readme_installs_from_git():
    block = _install_block()
    assert "git+https://github.com/alexberardi/jarvis-command-sdk.git" in block


def test_readme_notes_the_sdk_is_not_on_pypi():
    assert "not" in _install_block().lower() and "PyPI" in _install_block()
