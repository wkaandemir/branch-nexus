from __future__ import annotations

import pytest

from branchnexus.errors import BranchNexusError
from branchnexus.git.github_repositories import (
    GitHubRepository,
    list_github_repositories,
    list_github_repository_branches,
)


def test_repository_listing_sends_required_headers() -> None:
    captured_headers: dict[str, str] = {}

    def requester(_: str, headers: dict[str, str]) -> tuple[int, str, dict[str, str]]:
        captured_headers.update(headers)
        return 200, '[{"full_name":"org/repo","clone_url":"https://github.com/org/repo.git"}]', {}

    repos = list_github_repositories("token-123", requester=requester)

    assert repos == [GitHubRepository(full_name="org/repo", clone_url="https://github.com/org/repo.git")]
    assert captured_headers["Accept"] == "application/vnd.github+json"
    assert captured_headers["Authorization"] == "Bearer token-123"
    assert captured_headers["X-GitHub-Api-Version"] == "2022-11-28"
    assert captured_headers["User-Agent"] == "BranchNexus"


def test_repository_listing_deduplicates_by_clone_url_and_sorts_case_insensitive() -> None:
    def requester(_: str, __: dict[str, str]) -> tuple[int, str, dict[str, str]]:
        return (
            200,
            (
                '[{"full_name":"org/Zeta","clone_url":"https://github.com/org/shared.git"},'
                '{"full_name":"org/alpha","clone_url":"https://github.com/org/alpha.git"},'
                '{"full_name":"org/beta-override","clone_url":"https://github.com/org/shared.git"}]'
            ),
            {},
        )

    repos = list_github_repositories("token", requester=requester)

    assert [repo.full_name for repo in repos] == ["org/alpha", "org/beta-override"]


def test_branch_listing_encodes_repo_name_and_handles_pagination() -> None:
    calls: list[str] = []

    def requester(url: str, _: dict[str, str]) -> tuple[int, str, dict[str, str]]:
        calls.append(url)
        if "page=2" in url:
            return 200, '[{"name":"release"}]', {}
        return (
            200,
            '[{"name":"main"},{"name":"feature/a"}]',
            {"link": '<https://api.github.com/repos/org/repo%20name/branches?per_page=100&page=2>; rel="next"'},
        )

    branches = list_github_repository_branches("token", "org/repo name", requester=requester)

    assert branches == ["feature/a", "main", "release"]
    assert calls[0].endswith("/repos/org/repo%20name/branches?per_page=100")


def test_branch_listing_uses_default_error_hint_when_payload_is_not_json() -> None:
    def requester(_: str, __: dict[str, str]) -> tuple[int, str, dict[str, str]]:
        return 403, "<html>denied</html>", {}

    with pytest.raises(BranchNexusError) as exc:
        list_github_repository_branches("token", "org/repo", requester=requester)

    assert "token" in exc.value.hint.lower()
