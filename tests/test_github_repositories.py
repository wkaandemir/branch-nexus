from __future__ import annotations

import pytest

from branchnexus.errors import BranchNexusError
from branchnexus.git.github_repositories import (
    list_github_repositories,
    list_github_repository_branches,
)


def test_list_github_repositories_collects_all_pages() -> None:
    calls: list[str] = []

    def requester(url: str, headers: dict[str, str]) -> tuple[int, str, dict[str, str]]:
        assert headers["Authorization"] == "Bearer test-token"
        calls.append(url)
        if "page=2" in url:
            return (
                200,
                '[{"full_name":"org/beta","clone_url":"https://github.com/org/beta.git"}]',
                {},
            )
        return (
            200,
            '[{"full_name":"org/alpha","clone_url":"https://github.com/org/alpha.git"}]',
            {"link": '<https://api.github.com/user/repos?per_page=100&page=2>; rel="next"'},
        )

    repositories = list_github_repositories("test-token", requester=requester)
    assert [item.full_name for item in repositories] == ["org/alpha", "org/beta"]
    assert calls == [
        "https://api.github.com/user/repos?per_page=100&sort=full_name&direction=asc",
        "https://api.github.com/user/repos?per_page=100&page=2",
    ]


def test_list_github_repositories_raises_for_invalid_token() -> None:
    def requester(_: str, __: dict[str, str]) -> tuple[int, str, dict[str, str]]:
        return 401, '{"message":"Bad credentials"}', {}

    with pytest.raises(BranchNexusError) as exc:
        list_github_repositories("expired-token", requester=requester)
    assert "token" in str(exc.value).lower()


def test_list_github_repositories_raises_when_token_has_no_repos() -> None:
    def requester(_: str, __: dict[str, str]) -> tuple[int, str, dict[str, str]]:
        return 200, "[]", {}

    with pytest.raises(BranchNexusError) as exc:
        list_github_repositories("test-token", requester=requester)
    assert "repo" in str(exc.value).lower()


def test_list_github_repository_branches_collects_all_pages() -> None:
    calls: list[str] = []

    def requester(url: str, headers: dict[str, str]) -> tuple[int, str, dict[str, str]]:
        assert headers["Authorization"] == "Bearer test-token"
        calls.append(url)
        if "page=2" in url:
            return 200, '[{"name":"release"}]', {}
        return (
            200,
            '[{"name":"main"},{"name":"feature-a"}]',
            {"link": '<https://api.github.com/repos/org/repo/branches?per_page=100&page=2>; rel="next"'},
        )

    branches = list_github_repository_branches("test-token", "org/repo", requester=requester)
    assert branches == ["feature-a", "main", "release"]
    assert calls == [
        "https://api.github.com/repos/org/repo/branches?per_page=100",
        "https://api.github.com/repos/org/repo/branches?per_page=100&page=2",
    ]


def test_list_github_repository_branches_raises_for_invalid_repo() -> None:
    with pytest.raises(BranchNexusError):
        list_github_repository_branches("test-token", "invalid")
