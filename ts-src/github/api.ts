export interface GitHubRepo {
  fullName: string;
  cloneUrl: string;
}

export interface GitHubBranch {
  name: string;
  isDefault: boolean;
}

export interface ParsedGitHubUrl {
  owner: string;
  repo: string;
}

export type RepoVisibility = 'public' | 'private' | 'not_found' | 'error';

/**
 * Extracts owner/repo from GitHub URLs.
 * Supports HTTPS, SSH, and token-embedded URLs.
 * Returns null for non-GitHub URLs.
 */
export function parseGitHubUrl(url: string): ParsedGitHubUrl | null {
  // HTTPS: https://github.com/owner/repo.git or https://token@github.com/owner/repo
  const httpsMatch = url.match(
    /^https?:\/\/(?:[^@]+@)?github\.com\/([^/]+)\/([^/\s]+?)(?:\.git)?$/
  );
  if (httpsMatch) {
    return { owner: httpsMatch[1], repo: httpsMatch[2] };
  }

  // SSH: git@github.com:owner/repo.git
  const sshMatch = url.match(/^git@github\.com:([^/]+)\/([^/\s]+?)(?:\.git)?$/);
  if (sshMatch) {
    return { owner: sshMatch[1], repo: sshMatch[2] };
  }

  return null;
}

/**
 * Checks repository visibility via the GitHub API.
 * Uses unauthenticated request by default; pass token for authenticated check.
 */
export async function checkRepoVisibility(
  owner: string,
  repo: string,
  token?: string
): Promise<RepoVisibility> {
  try {
    const headers: Record<string, string> = {
      Accept: 'application/vnd.github.v3+json',
      'User-Agent': 'BranchNexus/1.0',
    };

    if (token !== undefined && token !== '') {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(`https://api.github.com/repos/${owner}/${repo}`, { headers });

    if (response.ok) {
      const data = (await response.json()) as { private: boolean };
      return data.private ? 'private' : 'public';
    }

    if (response.status === 404) {
      // Without token, GitHub returns 404 for private repos
      // With token, 404 means repo genuinely doesn't exist
      return token !== undefined && token !== '' ? 'not_found' : 'private';
    }

    return 'error';
  } catch {
    // Network error — fail open, let clone attempt proceed
    return 'error';
  }
}

export class GitHubClient {
  private token: string;

  constructor(token?: string) {
    this.token = token ?? process.env.BRANCHNEXUS_GH_TOKEN ?? '';
  }

  private async fetch(endpoint: string): Promise<unknown> {
    if (this.token === '') {
      throw new Error('GitHub token is required. Set BRANCHNEXUS_GH_TOKEN env var.');
    }

    const response = await fetch(`https://api.github.com${endpoint}`, {
      headers: {
        Authorization: `Bearer ${this.token}`,
        Accept: 'application/vnd.github.v3+json',
        'User-Agent': 'BranchNexus/1.0',
      },
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`GitHub API error: ${response.status} ${error}`);
    }

    return response.json();
  }

  async listRepositories(): Promise<GitHubRepo[]> {
    const data = (await this.fetch('/user/repos?per_page=100&sort=updated')) as Array<{
      full_name: string;
      clone_url: string;
    }>;

    return data.map((repo) => ({
      fullName: repo.full_name,
      cloneUrl: repo.clone_url,
    }));
  }

  async listBranches(owner: string, repo: string): Promise<GitHubBranch[]> {
    const data = (await this.fetch(`/repos/${owner}/${repo}/branches?per_page=100`)) as Array<{
      name: string;
    }>;

    const defaultBranch = await this.getDefaultBranch(owner, repo);

    return data.map((branch) => ({
      name: branch.name,
      isDefault: branch.name === defaultBranch,
    }));
  }

  async getDefaultBranch(owner: string, repo: string): Promise<string> {
    const data = (await this.fetch(`/repos/${owner}/${repo}`)) as {
      default_branch: string;
    };
    return data.default_branch ?? 'main';
  }
}
