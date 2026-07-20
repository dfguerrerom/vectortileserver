import nox

PYTHON_VERSIONS = ["3.10", "3.11", "3.12"]


@nox.session(python=PYTHON_VERSIONS)
def tests(session: nox.Session) -> None:
    session.install("-e", ".[dev]")
    session.run("pytest", *session.posargs)


@nox.session(reuse_venv=True)
def lint(session: nox.Session) -> None:
    session.install("-e", ".[dev]")
    session.run("ruff", "check", "vectortileserver", "tests")
    session.run("black", "--check", "vectortileserver", "tests")
