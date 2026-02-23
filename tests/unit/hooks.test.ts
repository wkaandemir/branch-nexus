import { describe, it, expect, vi, beforeEach } from 'vitest';
import { HookRunner } from '../../ts-src/hooks/runner.js';

// Mock execa
vi.mock('execa', () => ({
  execa: vi.fn(),
}));

// Mock platform detection
vi.mock('../../ts-src/runtime/platform.js', () => ({
  Platform: { WINDOWS: 'WINDOWS', MACOS: 'MACOS', LINUX: 'LINUX' },
  detectPlatform: vi.fn(() => 'LINUX'),
}));

// Mock WSL
vi.mock('../../ts-src/runtime/wsl.js', () => ({
  buildWslCommand: vi.fn((dist: string, cmd: string[]) => ['wsl', '-d', dist, '--', ...cmd]),
}));

// Mock logger
vi.mock('../../ts-src/utils/logger.js', () => ({
  logger: {
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  },
}));

describe('HookRunner', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('constructor', () => {
    it('should use default options', () => {
      const runner = new HookRunner();
      expect(runner).toBeInstanceOf(HookRunner);
    });

    it('should accept custom options', () => {
      const runner = new HookRunner({
        timeoutSeconds: 60,
        trustedConfig: false,
        allowCommandPrefixes: ['npm', 'yarn'],
      });
      expect(runner).toBeInstanceOf(HookRunner);
    });
  });

  describe('run', () => {
    it('should execute commands and return results', async () => {
      const { execa } = await import('execa');
      const mockExeca = vi.mocked(execa);
      mockExeca.mockResolvedValue({
        exitCode: 0,
        stdout: 'success',
        stderr: '',
      } as never);

      const runner = new HookRunner();
      const result = await runner.run(0, ['echo hello']);

      expect(result.pane).toBe(0);
      expect(result.executions).toHaveLength(1);
      expect(result.executions[0].success).toBe(true);
      expect(result.executions[0].returncode).toBe(0);
      expect(result.hasFailures).toBe(false);
    });

    it('should handle failed commands', async () => {
      const { execa } = await import('execa');
      const mockExeca = vi.mocked(execa);
      mockExeca.mockResolvedValue({
        exitCode: 1,
        stdout: '',
        stderr: 'error output',
      } as never);

      const runner = new HookRunner();
      const result = await runner.run(1, ['failing-cmd']);

      expect(result.pane).toBe(1);
      expect(result.executions[0].success).toBe(false);
      expect(result.executions[0].returncode).toBe(1);
      expect(result.hasFailures).toBe(true);
    });

    it('should handle multiple commands', async () => {
      const { execa } = await import('execa');
      const mockExeca = vi.mocked(execa);
      mockExeca
        .mockResolvedValueOnce({ exitCode: 0, stdout: 'ok', stderr: '' } as never)
        .mockResolvedValueOnce({ exitCode: 1, stdout: '', stderr: 'fail' } as never);

      const runner = new HookRunner();
      const result = await runner.run(0, ['cmd1', 'cmd2']);

      expect(result.executions).toHaveLength(2);
      expect(result.executions[0].success).toBe(true);
      expect(result.executions[1].success).toBe(false);
      expect(result.hasFailures).toBe(true);
    });

    it('should handle empty command list', async () => {
      const runner = new HookRunner();
      const result = await runner.run(0, []);

      expect(result.pane).toBe(0);
      expect(result.executions).toHaveLength(0);
      expect(result.hasFailures).toBe(false);
    });

    it('should block commands when not trusted and not in allowlist', async () => {
      const runner = new HookRunner({
        trustedConfig: false,
        allowCommandPrefixes: ['npm'],
      });

      const result = await runner.run(0, ['rm -rf /']);

      expect(result.executions[0].success).toBe(false);
      expect(result.executions[0].returncode).toBe(126);
      expect(result.executions[0].output).toContain('blocked');
    });

    it('should allow commands matching allowlist prefix', async () => {
      const { execa } = await import('execa');
      const mockExeca = vi.mocked(execa);
      mockExeca.mockResolvedValue({
        exitCode: 0,
        stdout: 'installed',
        stderr: '',
      } as never);

      const runner = new HookRunner({
        trustedConfig: false,
        allowCommandPrefixes: ['npm'],
      });

      const result = await runner.run(0, ['npm install']);

      expect(result.executions[0].success).toBe(true);
    });

    it('should handle timeout errors', async () => {
      const { execa } = await import('execa');
      const mockExeca = vi.mocked(execa);
      mockExeca.mockRejectedValue(new Error('timed out after 30000'));

      const runner = new HookRunner({ timeoutSeconds: 1 });
      const result = await runner.run(0, ['slow-command']);

      expect(result.executions[0].success).toBe(false);
      expect(result.executions[0].returncode).toBe(124);
      expect(result.executions[0].output).toContain('timed out');
    });

    it('should handle non-timeout errors', async () => {
      const { execa } = await import('execa');
      const mockExeca = vi.mocked(execa);
      mockExeca.mockRejectedValue(new Error('command not found'));

      const runner = new HookRunner();
      const result = await runner.run(0, ['nonexistent-cmd']);

      expect(result.executions[0].success).toBe(false);
      expect(result.executions[0].returncode).toBe(1);
      expect(result.executions[0].output).toContain('command not found');
    });
  });
});
