from __future__ import annotations

from pathlib import Path

from branchnexus.git.repo_discovery import discover_repositories


def _init_repo(path: Path) -> None:
    (path / ".git").mkdir(parents=True)


def test_discovers_git_repositories_recursively(tmp_path: Path) -> None:
    repo_a = tmp_path / "a"
    repo_b = tmp_path / "nested" / "b"
    _init_repo(repo_a)
    _init_repo(repo_b)

    repos = discover_repositories(tmp_path)
    assert repos == sorted([repo_a.resolve(), repo_b.resolve()], key=lambda p: str(p).lower())


def test_ignores_common_large_directories(tmp_path: Path) -> None:
    repo_a = tmp_path / "ok"
    _init_repo(repo_a)
    ignored = tmp_path / "node_modules" / "lib"
    _init_repo(ignored)

    repos = discover_repositories(tmp_path)
    assert repo_a.resolve() in repos
    assert ignored.resolve() not in repos


def test_stops_descending_after_repo_root(tmp_path: Path) -> None:
    root_repo = tmp_path / "root"
    _init_repo(root_repo)
    nested_repo = root_repo / "sub" / "child"
    _init_repo(nested_repo)

    repos = discover_repositories(tmp_path)
    assert repos == [root_repo.resolve()]
