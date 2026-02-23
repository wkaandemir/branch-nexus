import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { checkRepositoryAccess } from '../../ts-src/git/clone.js';
import { BranchNexusError } from '../../ts-src/types/errors.js';

vi.mock('../../ts-src/utils/logger.js', () => ({
  logger: { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() },
}));

vi.mock('../../ts-src/core/config.js', () => ({
  loadConfig: vi.fn(() => ({ githubToken: '' })),
}));

// We need to import after mock setup to get the mocked version
import { loadConfig } from '../../ts-src/core/config.js';
const mockLoadConfig = vi.mocked(loadConfig);

describe('checkRepositoryAccess', () => {
  const originalFetch = globalThis.fetch;
  let mockFetch: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mockFetch = vi.fn();
    globalThis.fetch = mockFetch;
    mockLoadConfig.mockReturnValue({ githubToken: '' } as ReturnType<typeof loadConfig>);
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('should allow non-GitHub URLs without checking', async () => {
    const result = await checkRepositoryAccess('https://gitlab.com/owner/repo.git');

    expect(result).toEqual({ allowed: true, isPrivate: false });
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it('should allow public GitHub repos', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ private: false }),
    });

    const result = await checkRepositoryAccess('https://github.com/owner/repo.git');

    expect(result).toEqual({ allowed: true, isPrivate: false });
  });

  it('should throw for private repos without a token', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 404,
    });

    await expect(
      checkRepositoryAccess('https://github.com/owner/private-repo.git')
    ).rejects.toThrow(BranchNexusError);

    await expect(
      checkRepositoryAccess('https://github.com/owner/private-repo.git')
    ).rejects.toThrow('private');
  });

  it('should allow private repos when token is available', async () => {
    mockLoadConfig.mockReturnValue({ githubToken: 'ghp_test123' } as ReturnType<typeof loadConfig>);

    // First call (unauthenticated): 404 → private
    // Second call (authenticated): 200 → private: true
    mockFetch
      .mockResolvedValueOnce({
        ok: false,
        status: 404,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ private: true }),
      });

    const result = await checkRepositoryAccess('https://github.com/owner/private-repo.git');

    expect(result).toEqual({ allowed: true, isPrivate: true });
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it('should allow when GitHub API is unreachable (fail open)', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));

    const result = await checkRepositoryAccess('https://github.com/owner/repo.git');

    expect(result).toEqual({ allowed: true, isPrivate: false });
  });
});
