export interface GitHubRepo {
  fullName: string;
  cloneUrl: string;
}

export interface GitHubBranch {
  name: string;
  isDefault: boolean;
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
