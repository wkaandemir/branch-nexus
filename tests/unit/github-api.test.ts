import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { GitHubClient } from '../../ts-src/github/api.js';

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
            Promise.resolve([
              { name: 'main' },
              { name: 'develop' },
              { name: 'feature/test' },
            ]),
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
