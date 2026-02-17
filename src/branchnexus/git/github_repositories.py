"""GitHub repository discovery using a personal access token."""

from __future__ import annotations

import json
import logging as py_logging
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from branchnexus.errors import BranchNexusError, ExitCode

logger = py_logging.getLogger(__name__)


@dataclass(frozen=True)
class GitHubRepository:
    full_name: str
    clone_url: str


HttpResponse = tuple[int, str, dict[str, str]]


class HttpRequester(Protocol):
    def __call__(self, url: str, headers: dict[str, str]) -> HttpResponse: ...


def _validate_github_api_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "api.github.com":
        raise BranchNexusError(
            "Gecersiz GitHub API adresi.",
            code=ExitCode.VALIDATION_ERROR,
            hint="Sadece https://api.github.com adresi desteklenir.",
        )


def _default_requester(url: str, headers: dict[str, str]) -> HttpResponse:
    _validate_github_api_url(url)
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=20) as response:  # nosec B310
            status = int(getattr(response, "status", response.getcode()))
            body = response.read().decode("utf-8")
            response_headers = {key.lower(): value for key, value in response.headers.items()}
            return status, body, response_headers
    except HTTPError as exc:
        payload = ""
        if exc.fp is not None:
            payload = exc.read().decode("utf-8", errors="replace")
        response_headers = {key.lower(): value for key, value in (exc.headers.items() if exc.headers else [])}
        return exc.code, payload, response_headers
    except URLError as exc:
        raise BranchNexusError(
            "GitHub API baglantisi kurulamadi.",
            code=ExitCode.RUNTIME_ERROR,
            hint=str(exc.reason) or "Ag baglantinizi kontrol edin.",
        ) from exc


def _next_page_url(link_header: str) -> str | None:
    if not link_header.strip():
        return None
    for chunk in link_header.split(","):
        section = chunk.strip()
        if 'rel="next"' not in section:
            continue
        if section.startswith("<") and ">" in section:
            return section[1 : section.index(">")]
    return None


def _extract_message(payload: str) -> str:
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return ""
    if isinstance(parsed, dict):
        message = parsed.get("message")
        if isinstance(message, str):
            return message
    return ""


def list_github_repositories(
    token: str,
    *,
    requester: HttpRequester | None = None,
) -> list[GitHubRepository]:
    token_value = token.strip()
    if not token_value:
        raise BranchNexusError(
            "GitHub token zorunludur.",
            code=ExitCode.VALIDATION_ERROR,
            hint="Token girip repo listesini tekrar yukleyin.",
        )

    do_request = requester or _default_requester
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token_value}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "BranchNexus",
    }

    page_url: str | None = "https://api.github.com/user/repos?per_page=100&sort=full_name&direction=asc"
    repository_by_url: dict[str, GitHubRepository] = {}

    while page_url:
        status, payload, response_headers = do_request(page_url, headers)
        header_map = {key.lower(): value for key, value in response_headers.items()}
        if status == 200:
            try:
                entries = json.loads(payload)
            except json.JSONDecodeError as exc:
                logger.error("GitHub API payload was not valid JSON")
                raise BranchNexusError(
                    "GitHub repo listesi okunamadi.",
                    code=ExitCode.RUNTIME_ERROR,
                    hint="Biraz sonra tekrar deneyin.",
                ) from exc

            if not isinstance(entries, list):
                raise BranchNexusError(
                    "GitHub API beklenmeyen bir cevap dondurdu.",
                    code=ExitCode.RUNTIME_ERROR,
                    hint="Token izinlerini ve API erisimini kontrol edin.",
                )

            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                full_name = entry.get("full_name")
                clone_url = entry.get("clone_url")
                if isinstance(full_name, str) and isinstance(clone_url, str):
                    repository_by_url[clone_url] = GitHubRepository(full_name=full_name, clone_url=clone_url)

            page_url = _next_page_url(header_map.get("link", ""))
            continue

        message = _extract_message(payload)
        if status == 401:
            raise BranchNexusError(
                "GitHub token gecersiz veya suresi dolmus.",
                code=ExitCode.GIT_ERROR,
                hint=message or "Gecerli token ile tekrar deneyin.",
            )
        if status == 403:
            raise BranchNexusError(
                "GitHub API erisimi reddedildi.",
                code=ExitCode.GIT_ERROR,
                hint=message or "Token izinlerini veya rate limit durumunu kontrol edin.",
            )
        raise BranchNexusError(
            f"GitHub repo listesi alinamadi (HTTP {status}).",
            code=ExitCode.GIT_ERROR,
            hint=message or "Ag erisimi ve token izinlerini kontrol edin.",
        )

    repositories = sorted(repository_by_url.values(), key=lambda item: item.full_name.lower())
    if not repositories:
        raise BranchNexusError(
            "Bu token icin erisilebilir repo bulunamadi.",
            code=ExitCode.VALIDATION_ERROR,
            hint="Tokenin en az bir repoya erisimi oldugundan emin olun.",
        )
    return repositories


def list_github_repository_branches(
    token: str,
    repo_full_name: str,
    *,
    requester: HttpRequester | None = None,
) -> list[str]:
    token_value = token.strip()
    if not token_value:
        raise BranchNexusError(
            "GitHub token zorunludur.",
            code=ExitCode.VALIDATION_ERROR,
            hint="Token girip branch listesini tekrar yukleyin.",
        )

    repo_name = repo_full_name.strip().strip("/")
    if not repo_name or "/" not in repo_name:
        raise BranchNexusError(
            f"Gecersiz repository: {repo_full_name}",
            code=ExitCode.VALIDATION_ERROR,
            hint="org/repo formatinda bir repository secin.",
        )

    do_request = requester or _default_requester
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token_value}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "BranchNexus",
    }

    encoded_repo = quote(repo_name, safe="/")
    page_url: str | None = f"https://api.github.com/repos/{encoded_repo}/branches?per_page=100"
    branches: set[str] = set()

    while page_url:
        status, payload, response_headers = do_request(page_url, headers)
        header_map = {key.lower(): value for key, value in response_headers.items()}

        if status == 200:
            try:
                entries = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise BranchNexusError(
                    "GitHub branch listesi okunamadi.",
                    code=ExitCode.RUNTIME_ERROR,
                    hint="Biraz sonra tekrar deneyin.",
                ) from exc

            if not isinstance(entries, list):
                raise BranchNexusError(
                    "GitHub API beklenmeyen branch cevabi dondurdu.",
                    code=ExitCode.RUNTIME_ERROR,
                    hint="Repository erisim izinlerini kontrol edin.",
                )

            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                name = entry.get("name")
                if isinstance(name, str) and name.strip():
                    branches.add(name.strip())

            page_url = _next_page_url(header_map.get("link", ""))
            continue

        message = _extract_message(payload)
        if status == 401:
            raise BranchNexusError(
                "GitHub token gecersiz veya suresi dolmus.",
                code=ExitCode.GIT_ERROR,
                hint=message or "Gecerli token ile tekrar deneyin.",
            )
        if status == 403:
            raise BranchNexusError(
                "GitHub branch erisimi reddedildi.",
                code=ExitCode.GIT_ERROR,
                hint=message or "Token izinlerini veya rate limit durumunu kontrol edin.",
            )
        if status == 404:
            raise BranchNexusError(
                f"Repository bulunamadi: {repo_name}",
                code=ExitCode.GIT_ERROR,
                hint=message or "Repository adini ve token erisimini kontrol edin.",
            )
        raise BranchNexusError(
            f"GitHub branch listesi alinamadi (HTTP {status}).",
            code=ExitCode.GIT_ERROR,
            hint=message or "Ag erisimi ve token izinlerini kontrol edin.",
        )

    result = sorted(branches, key=str.lower)
    if not result:
        raise BranchNexusError(
            "Repository icin branch bulunamadi.",
            code=ExitCode.GIT_ERROR,
            hint="Repository'de en az bir branch oldugundan emin olun.",
        )
    return result
