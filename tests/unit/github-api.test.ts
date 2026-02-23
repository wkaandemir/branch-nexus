import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { GitHubClient, parseGitHubUrl, checkRepoVisibility } from '../../ts-src/github/api.js';

describe('GitHubClient', () => {
  const originalFetch = globalThis.fetch;
  let mockFetch: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockFetch = vi.fn();
    globalThis.fetch = mockFetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  describe('constructor', () => {
    it('should accept a token parameter', () => {
      const client = new GitHubClient('test-token');
      expect(client).toBeInstanceOf(GitHubClient);
    });

    it('should use env var when no token provided', () => {
      const prev = process.env.BRANCHNEXUS_GH_TOKEN;
      process.env.BRANCHNEXUS_GH_TOKEN = 'env-token';

      const client = new GitHubClient();
      expect(client).toBeInstanceOf(GitHubClient);

      if (prev !== undefined) {
        process.env.BRANCHNEXUS_GH_TOKEN = prev;
      } else {
        delete process.env.BRANCHNEXUS_GH_TOKEN;
      }
    });
  });

  describe('listRepositories', () => {
    it('should fetch and return repositories', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve([
            { full_name: 'user/repo1', clone_url: 'https://github.com/user/repo1.git' },
            { full_name: 'user/repo2', clone_url: 'https://github.com/user/repo2.git' },
          ]),
      });

      const client = new GitHubClient('test-token');
      const repos = await client.listRepositories();

      expect(repos).toHaveLength(2);
      expect(repos[0]).toEqual({
        fullName: 'user/repo1',
        cloneUrl: 'https://github.com/user/repo1.git',
      });
      expect(repos[1]).toEqual({
        fullName: 'user/repo2',
        cloneUrl: 'https://github.com/user/repo2.git',
      });

      expect(mockFetch).toHaveBeenCalledWith(
        'https://api.github.com/user/repos?per_page=100&sort=updated',
        expect.objectContaining({
          headers: expect.objectContaining({
            Authorization: 'Bearer test-token',
          }),
        })
      );
    });

    it('should throw when no token is available', async () => {
      const prev = process.env.BRANCHNEXUS_GH_TOKEN;
      delete process.env.BRANCHNEXUS_GH_TOKEN;

      const client = new GitHubClient('');
      await expect(client.listRepositories()).rejects.toThrow('GitHub token is required');

      if (prev !== undefined) {
        process.env.BRANCHNEXUS_GH_TOKEN = prev;
      }
    });

    it('should throw on API error', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        status: 401,
        text: () => Promise.resolve('Bad credentials'),
      });

      const client = new GitHubClient('bad-token');
      await expect(client.listRepositories()).rejects.toThrow('GitHub API error: 401');
    });
  });

  describe('listBranches', () => {
    it('should fetch and return branches with default flag', async () => {
      // First call: branches list, Second call: repo default branch
      mockFetch
        .mockResolvedValueOnce({
          ok: true,
          json: () =>
            Promise.resolve([{ name: 'main' }, { name: 'develop' }, { name: 'feature/test' }]),
        })
        .mockResolvedValueOnce({
          ok: true,
          json: () => Promise.resolve({ default_branch: 'main' }),
        });

      const client = new GitHubClient('test-token');
      const branches = await client.listBranches('user', 'repo');

      expect(branches).toHaveLength(3);
      expect(branches[0]).toEqual({ name: 'main', isDefault: true });
      expect(branches[1]).toEqual({ name: 'develop', isDefault: false });
      expect(branches[2]).toEqual({ name: 'feature/test', isDefault: false });
    });
  });

  describe('getDefaultBranch', () => {
    it('should return the default branch', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ default_branch: 'main' }),
      });

      const client = new GitHubClient('test-token');
      const branch = await client.getDefaultBranch('user', 'repo');
      expect(branch).toBe('main');
    });

    it('should fallback to main when not specified', async () => {
      mockFetch.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({}),
      });

      const client = new GitHubClient('test-token');
      const branch = await client.getDefaultBranch('user', 'repo');
      expect(branch).toBe('main');
    });
  });
});

describe('parseGitHubUrl', () => {
  it('should parse HTTPS URLs', () => {
    expect(parseGitHubUrl('https://github.com/owner/repo')).toEqual({
      owner: 'owner',
      repo: 'repo',
    });
  });

  it('should parse HTTPS URLs with .git suffix', () => {
    expect(parseGitHubUrl('https://github.com/owner/repo.git')).toEqual({
      owner: 'owner',
      repo: 'repo',
    });
  });

  it('should parse SSH URLs', () => {
    expect(parseGitHubUrl('git@github.com:owner/repo.git')).toEqual({
      owner: 'owner',
      repo: 'repo',
    });
  });

  it('should parse SSH URLs without .git suffix', () => {
    expect(parseGitHubUrl('git@github.com:owner/repo')).toEqual({
      owner: 'owner',
      repo: 'repo',
    });
  });

  it('should parse token-embedded HTTPS URLs', () => {
    expect(parseGitHubUrl('https://ghp_abc123@github.com/owner/repo.git')).toEqual({
      owner: 'owner',
      repo: 'repo',
    });
  });

  it('should return null for non-GitHub URLs', () => {
    expect(parseGitHubUrl('https://gitlab.com/owner/repo.git')).toBeNull();
    expect(parseGitHubUrl('https://bitbucket.org/owner/repo.git')).toBeNull();
    expect(parseGitHubUrl('git@gitlab.com:owner/repo.git')).toBeNull();
  });
});

describe('checkRepoVisibility', () => {
  const originalFetch = globalThis.fetch;
  let mockFetch: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockFetch = vi.fn();
    globalThis.fetch = mockFetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('should return public for a 200 response with private: false', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ private: false }),
    });

    const result = await checkRepoVisibility('owner', 'repo');
    expect(result).toBe('public');
  });

  it('should return private for a 200 response with private: true', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ private: true }),
    });

    const result = await checkRepoVisibility('owner', 'repo', 'token');
    expect(result).toBe('private');
  });

  it('should return private for a 404 without token', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 404,
    });

    const result = await checkRepoVisibility('owner', 'repo');
    expect(result).toBe('private');
  });

  it('should return not_found for a 404 with token', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 404,
    });

    const result = await checkRepoVisibility('owner', 'repo', 'my-token');
    expect(result).toBe('not_found');
  });

  it('should return error on network failure', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));

    const result = await checkRepoVisibility('owner', 'repo');
    expect(result).toBe('error');
  });
});
