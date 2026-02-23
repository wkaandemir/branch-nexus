import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  buildRuntimeSnapshot,
  parseRuntimeSnapshot,
  SessionCleanupHandler,
} from '../../ts-src/core/session.js';
import {
  ExitChoice,
  type RuntimeKind,
  type SessionTerminalSnapshot,
  type RuntimeSessionSnapshot,
  type ManagedWorktree,
} from '../../ts-src/types/index.js';
import { WorktreeManager } from '../../ts-src/git/worktree.js';

function makeTerminal(overrides: Partial<SessionTerminalSnapshot> = {}): SessionTerminalSnapshot {
  return {
    terminalId: 'term-1',
    title: 'Terminal 1',
    runtime: 'native' as RuntimeKind,
    repoPath: '/repo/path',
    branch: 'main',
    ...overrides,
  };
}

function makeSnapshot(
  overrides: Partial<RuntimeSessionSnapshot> = {}
): RuntimeSessionSnapshot {
  return {
    layout: 'grid',
    templateCount: 4,
    focusedTerminalId: 'term-1',
    terminals: [makeTerminal()],
    ...overrides,
  };
}

function makeManagedWorktree(overrides: Partial<ManagedWorktree> = {}): ManagedWorktree {
  return {
    pane: 0,
    repoPath: '/repo/path',
    branch: 'feature-a',
    path: '/worktrees/repo/feature-a',
    ...overrides,
  };
}

describe('session', () => {
  describe('buildRuntimeSnapshot', () => {
    it('should create a valid snapshot with all parameters', () => {
      const terminals = [makeTerminal()];
      const result = buildRuntimeSnapshot('grid', 4, terminals, 'term-1');

      expect(result).toEqual({
        layout: 'grid',
        templateCount: 4,
        focusedTerminalId: 'term-1',
        terminals,
      });
    });

    it('should default focusedTerminalId to empty string when omitted', () => {
      const terminals = [makeTerminal()];
      const result = buildRuntimeSnapshot('horizontal', 2, terminals);

      expect(result.focusedTerminalId).toBe('');
    });

    it('should accept templateCount at minimum boundary (2)', () => {
      const terminals = [makeTerminal()];
      const result = buildRuntimeSnapshot('grid', 2, terminals);

      expect(result.templateCount).toBe(2);
    });

    it('should accept templateCount at maximum boundary (16)', () => {
      const terminals = [makeTerminal()];
      const result = buildRuntimeSnapshot('grid', 16, terminals);

      expect(result.templateCount).toBe(16);
    });

    it('should throw for templateCount below minimum (1)', () => {
      expect(() => buildRuntimeSnapshot('grid', 1, [])).toThrow('Invalid terminal count: 1');
    });

    it('should throw for templateCount of 0', () => {
      expect(() => buildRuntimeSnapshot('grid', 0, [])).toThrow('Invalid terminal count: 0');
    });

    it('should throw for negative templateCount', () => {
      expect(() => buildRuntimeSnapshot('grid', -1, [])).toThrow('Invalid terminal count: -1');
    });

    it('should throw for templateCount above maximum (17)', () => {
      expect(() => buildRuntimeSnapshot('grid', 17, [])).toThrow('Invalid terminal count: 17');
    });

    it('should throw for templateCount of 100', () => {
      expect(() => buildRuntimeSnapshot('grid', 100, [])).toThrow('Invalid terminal count: 100');
    });

    it('should preserve any layout string', () => {
      const result = buildRuntimeSnapshot('vertical', 3, [makeTerminal()]);
      expect(result.layout).toBe('vertical');
    });

    it('should preserve empty terminals array when count is valid', () => {
      const result = buildRuntimeSnapshot('grid', 4, []);
      expect(result.terminals).toEqual([]);
    });

    it('should preserve multiple terminals', () => {
      const terminals = [
        makeTerminal({ terminalId: 'a' }),
        makeTerminal({ terminalId: 'b' }),
        makeTerminal({ terminalId: 'c' }),
      ];
      const result = buildRuntimeSnapshot('grid', 4, terminals);
      expect(result.terminals).toHaveLength(3);
    });
  });

  describe('parseRuntimeSnapshot', () => {
    it('should parse a valid snapshot', () => {
      const raw = makeSnapshot();
      const result = parseRuntimeSnapshot(raw);

      expect(result).not.toBeNull();
      expect(result!.layout).toBe('grid');
      expect(result!.templateCount).toBe(4);
      expect(result!.focusedTerminalId).toBe('term-1');
      expect(result!.terminals).toHaveLength(1);
      expect(result!.terminals[0].terminalId).toBe('term-1');
    });

    it('should return null for null input', () => {
      expect(parseRuntimeSnapshot(null)).toBeNull();
    });

    it('should return null for undefined input', () => {
      expect(parseRuntimeSnapshot(undefined)).toBeNull();
    });

    it('should return null for a string input', () => {
      expect(parseRuntimeSnapshot('hello')).toBeNull();
    });

    it('should return null for a number input', () => {
      expect(parseRuntimeSnapshot(42)).toBeNull();
    });

    it('should return null for a boolean input', () => {
      expect(parseRuntimeSnapshot(true)).toBeNull();
    });

    it('should return null for an empty object', () => {
      expect(parseRuntimeSnapshot({})).toBeNull();
    });

    it('should return null for an array', () => {
      expect(parseRuntimeSnapshot([])).toBeNull();
    });

    it('should return null when layout is missing', () => {
      const raw = { templateCount: 4, terminals: [makeTerminal()] };
      expect(parseRuntimeSnapshot(raw)).toBeNull();
    });

    it('should return null when layout is not a string', () => {
      const raw = { layout: 123, templateCount: 4, terminals: [makeTerminal()] };
      expect(parseRuntimeSnapshot(raw)).toBeNull();
    });

    it('should return null when templateCount is missing', () => {
      const raw = { layout: 'grid', terminals: [makeTerminal()] };
      expect(parseRuntimeSnapshot(raw)).toBeNull();
    });

    it('should return null when templateCount is not a number', () => {
      const raw = { layout: 'grid', templateCount: '4', terminals: [makeTerminal()] };
      expect(parseRuntimeSnapshot(raw)).toBeNull();
    });

    it('should return null when terminals is missing', () => {
      const raw = { layout: 'grid', templateCount: 4 };
      expect(parseRuntimeSnapshot(raw)).toBeNull();
    });

    it('should return null when terminals is not an array', () => {
      const raw = { layout: 'grid', templateCount: 4, terminals: 'not-array' };
      expect(parseRuntimeSnapshot(raw)).toBeNull();
    });

    it('should return null for empty terminals array', () => {
      const raw = makeSnapshot({ terminals: [] });
      expect(parseRuntimeSnapshot(raw)).toBeNull();
    });

    it('should return null for templateCount of 0', () => {
      const raw = makeSnapshot({ templateCount: 0 });
      expect(parseRuntimeSnapshot(raw)).toBeNull();
    });

    it('should return null for templateCount of 1', () => {
      const raw = makeSnapshot({ templateCount: 1 });
      expect(parseRuntimeSnapshot(raw)).toBeNull();
    });

    it('should return null for templateCount of 17', () => {
      const raw = makeSnapshot({ templateCount: 17 });
      expect(parseRuntimeSnapshot(raw)).toBeNull();
    });

    it('should return null for negative templateCount', () => {
      const raw = makeSnapshot({ templateCount: -5 });
      expect(parseRuntimeSnapshot(raw)).toBeNull();
    });

    it('should return null for very large templateCount', () => {
      const raw = makeSnapshot({ templateCount: 1000 });
      expect(parseRuntimeSnapshot(raw)).toBeNull();
    });

    it('should accept templateCount at minimum boundary (2)', () => {
      const raw = makeSnapshot({ templateCount: 2 });
      const result = parseRuntimeSnapshot(raw);
      expect(result).not.toBeNull();
      expect(result!.templateCount).toBe(2);
    });

    it('should accept templateCount at maximum boundary (16)', () => {
      const raw = makeSnapshot({ templateCount: 16 });
      const result = parseRuntimeSnapshot(raw);
      expect(result).not.toBeNull();
      expect(result!.templateCount).toBe(16);
    });

    describe('runtime normalization', () => {
      it('should normalize "wsl" runtime', () => {
        const raw = makeSnapshot({
          terminals: [makeTerminal({ runtime: 'wsl' as RuntimeKind })],
        });
        const result = parseRuntimeSnapshot(raw);
        expect(result!.terminals[0].runtime).toBe('wsl');
      });

      it('should normalize "powershell" runtime', () => {
        const raw = makeSnapshot({
          terminals: [makeTerminal({ runtime: 'powershell' as RuntimeKind })],
        });
        const result = parseRuntimeSnapshot(raw);
        expect(result!.terminals[0].runtime).toBe('powershell');
      });

      it('should normalize "native" runtime', () => {
        const raw = makeSnapshot({
          terminals: [makeTerminal({ runtime: 'native' as RuntimeKind })],
        });
        const result = parseRuntimeSnapshot(raw);
        expect(result!.terminals[0].runtime).toBe('native');
      });

      it('should normalize uppercase "WSL" to "wsl"', () => {
        const raw = makeSnapshot({
          terminals: [makeTerminal({ runtime: 'WSL' as unknown as RuntimeKind })],
        });
        const result = parseRuntimeSnapshot(raw);
        expect(result!.terminals[0].runtime).toBe('wsl');
      });

      it('should normalize mixed case "PowerShell" to "powershell"', () => {
        const raw = makeSnapshot({
          terminals: [makeTerminal({ runtime: 'PowerShell' as unknown as RuntimeKind })],
        });
        const result = parseRuntimeSnapshot(raw);
        expect(result!.terminals[0].runtime).toBe('powershell');
      });

      it('should normalize "NATIVE" to "native"', () => {
        const raw = makeSnapshot({
          terminals: [makeTerminal({ runtime: 'NATIVE' as unknown as RuntimeKind })],
        });
        const result = parseRuntimeSnapshot(raw);
        expect(result!.terminals[0].runtime).toBe('native');
      });

      it('should normalize runtime with leading/trailing whitespace', () => {
        const raw = makeSnapshot({
          terminals: [makeTerminal({ runtime: '  wsl  ' as unknown as RuntimeKind })],
        });
        const result = parseRuntimeSnapshot(raw);
        expect(result!.terminals[0].runtime).toBe('wsl');
      });

      it('should return null for invalid runtime kind', () => {
        const raw = makeSnapshot({
          terminals: [makeTerminal({ runtime: 'bash' as unknown as RuntimeKind })],
        });
        expect(parseRuntimeSnapshot(raw)).toBeNull();
      });

      it('should return null for empty string runtime', () => {
        const raw = makeSnapshot({
          terminals: [makeTerminal({ runtime: '' as unknown as RuntimeKind })],
        });
        expect(parseRuntimeSnapshot(raw)).toBeNull();
      });
    });

    describe('string trimming and defaults', () => {
      it('should trim terminalId', () => {
        const raw = makeSnapshot({
          terminals: [makeTerminal({ terminalId: '  term-1  ' })],
        });
        const result = parseRuntimeSnapshot(raw);
        expect(result!.terminals[0].terminalId).toBe('term-1');
      });

      it('should trim title', () => {
        const raw = makeSnapshot({
          terminals: [makeTerminal({ title: '  My Terminal  ' })],
        });
        const result = parseRuntimeSnapshot(raw);
        expect(result!.terminals[0].title).toBe('My Terminal');
      });

      it('should use terminalId as title when title is empty', () => {
        const raw = makeSnapshot({
          terminals: [makeTerminal({ terminalId: 'term-x', title: '' })],
        });
        const result = parseRuntimeSnapshot(raw);
        expect(result!.terminals[0].title).toBe('term-x');
      });

      it('should use terminalId as title when title is only whitespace', () => {
        const raw = makeSnapshot({
          terminals: [makeTerminal({ terminalId: 'term-y', title: '   ' })],
        });
        const result = parseRuntimeSnapshot(raw);
        expect(result!.terminals[0].title).toBe('term-y');
      });

      it('should trim repoPath', () => {
        const raw = makeSnapshot({
          terminals: [makeTerminal({ repoPath: '  /some/path  ' })],
        });
        const result = parseRuntimeSnapshot(raw);
        expect(result!.terminals[0].repoPath).toBe('/some/path');
      });

      it('should default repoPath to empty string when missing', () => {
        const terminal = makeTerminal();
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        delete (terminal as any).repoPath;
        const raw = makeSnapshot({ terminals: [terminal] });
        const result = parseRuntimeSnapshot(raw);
        expect(result!.terminals[0].repoPath).toBe('');
      });

      it('should trim branch', () => {
        const raw = makeSnapshot({
          terminals: [makeTerminal({ branch: '  feature/x  ' })],
        });
        const result = parseRuntimeSnapshot(raw);
        expect(result!.terminals[0].branch).toBe('feature/x');
      });

      it('should default branch to empty string when missing', () => {
        const terminal = makeTerminal();
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        delete (terminal as any).branch;
        const raw = makeSnapshot({ terminals: [terminal] });
        const result = parseRuntimeSnapshot(raw);
        expect(result!.terminals[0].branch).toBe('');
      });

      it('should trim focusedTerminalId', () => {
        const raw = makeSnapshot({ focusedTerminalId: '  term-1  ' });
        const result = parseRuntimeSnapshot(raw);
        expect(result!.focusedTerminalId).toBe('term-1');
      });

      it('should default focusedTerminalId to empty string when missing', () => {
        const raw = { layout: 'grid', templateCount: 4, terminals: [makeTerminal()] };
        const result = parseRuntimeSnapshot(raw);
        expect(result!.focusedTerminalId).toBe('');
      });

      it('should default layout to "grid" when layout is empty', () => {
        const raw = makeSnapshot({ layout: '' });
        const result = parseRuntimeSnapshot(raw);
        expect(result!.layout).toBe('grid');
      });
    });

    it('should return null when a terminal has no terminalId', () => {
      const terminal = makeTerminal();
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (terminal as any).terminalId = '';
      const raw = makeSnapshot({ terminals: [terminal] });
      expect(parseRuntimeSnapshot(raw)).toBeNull();
    });

    it('should parse multiple terminals', () => {
      const raw = makeSnapshot({
        terminals: [
          makeTerminal({ terminalId: 'a', runtime: 'wsl' as RuntimeKind }),
          makeTerminal({ terminalId: 'b', runtime: 'native' as RuntimeKind }),
          makeTerminal({ terminalId: 'c', runtime: 'powershell' as RuntimeKind }),
        ],
      });
      const result = parseRuntimeSnapshot(raw);
      expect(result).not.toBeNull();
      expect(result!.terminals).toHaveLength(3);
      expect(result!.terminals[0].runtime).toBe('wsl');
      expect(result!.terminals[1].runtime).toBe('native');
      expect(result!.terminals[2].runtime).toBe('powershell');
    });

    it('should return null if any terminal has invalid runtime', () => {
      const raw = makeSnapshot({
        terminals: [
          makeTerminal({ terminalId: 'a', runtime: 'native' as RuntimeKind }),
          makeTerminal({ terminalId: 'b', runtime: 'invalid' as unknown as RuntimeKind }),
        ],
      });
      expect(parseRuntimeSnapshot(raw)).toBeNull();
    });

    it('should return null if any terminal has empty terminalId', () => {
      const raw = makeSnapshot({
        terminals: [
          makeTerminal({ terminalId: 'a' }),
          makeTerminal({ terminalId: '' }),
        ],
      });
      expect(parseRuntimeSnapshot(raw)).toBeNull();
    });
  });

  describe('SessionCleanupHandler', () => {
    let mockManager: WorktreeManager;
    let promptFn: ReturnType<typeof vi.fn>;

    beforeEach(() => {
      mockManager = {
        getCleanupPolicy: vi.fn(),
        getManaged: vi.fn(),
        checkDirty: vi.fn(),
        cleanup: vi.fn(),
      } as unknown as WorktreeManager;

      promptFn = vi.fn();
    });

    describe('persistent policy', () => {
      it('should return all paths as preservedDirty and closed=true', async () => {
        const worktrees: ManagedWorktree[] = [
          makeManagedWorktree({ path: '/wt/a' }),
          makeManagedWorktree({ path: '/wt/b' }),
        ];
        vi.mocked(mockManager.getCleanupPolicy).mockReturnValue('persistent');
        vi.mocked(mockManager.getManaged).mockReturnValue(worktrees);

        const handler = new SessionCleanupHandler(mockManager, promptFn);
        const result = await handler.handleExit();

        expect(result.closed).toBe(true);
        expect(result.cancelled).toBe(false);
        expect(result.removed).toEqual([]);
        expect(result.preservedDirty).toEqual(['/wt/a', '/wt/b']);
      });

      it('should not call checkDirty or cleanup', async () => {
        vi.mocked(mockManager.getCleanupPolicy).mockReturnValue('persistent');
        vi.mocked(mockManager.getManaged).mockReturnValue([
          makeManagedWorktree({ path: '/wt/a' }),
        ]);

        const handler = new SessionCleanupHandler(mockManager, promptFn);
        await handler.handleExit();

        expect(mockManager.checkDirty).not.toHaveBeenCalled();
        expect(mockManager.cleanup).not.toHaveBeenCalled();
      });

      it('should not call the prompt function', async () => {
        vi.mocked(mockManager.getCleanupPolicy).mockReturnValue('persistent');
        vi.mocked(mockManager.getManaged).mockReturnValue([]);

        const handler = new SessionCleanupHandler(mockManager, promptFn);
        await handler.handleExit();

        expect(promptFn).not.toHaveBeenCalled();
      });
    });

    describe('no dirty worktrees', () => {
      it('should remove all and return removed paths', async () => {
        const worktrees: ManagedWorktree[] = [
          makeManagedWorktree({ path: '/wt/a' }),
          makeManagedWorktree({ path: '/wt/b' }),
        ];
        vi.mocked(mockManager.getCleanupPolicy).mockReturnValue('session');
        vi.mocked(mockManager.getManaged).mockReturnValue(worktrees);
        vi.mocked(mockManager.checkDirty).mockResolvedValue(false);
        vi.mocked(mockManager.cleanup).mockResolvedValue(['/wt/a', '/wt/b']);

        const handler = new SessionCleanupHandler(mockManager, promptFn);
        const result = await handler.handleExit();

        expect(result.closed).toBe(true);
        expect(result.cancelled).toBe(false);
        expect(result.removed).toEqual(['/wt/a', '/wt/b']);
        expect(result.preservedDirty).toEqual([]);
      });

      it('should call cleanup without selected filter', async () => {
        vi.mocked(mockManager.getCleanupPolicy).mockReturnValue('session');
        vi.mocked(mockManager.getManaged).mockReturnValue([
          makeManagedWorktree({ path: '/wt/x' }),
        ]);
        vi.mocked(mockManager.checkDirty).mockResolvedValue(false);
        vi.mocked(mockManager.cleanup).mockResolvedValue(['/wt/x']);

        const handler = new SessionCleanupHandler(mockManager, promptFn, 'Ubuntu');
        await handler.handleExit();

        expect(mockManager.cleanup).toHaveBeenCalledWith({
          distribution: 'Ubuntu',
        });
      });

      it('should not call the prompt function when nothing is dirty', async () => {
        vi.mocked(mockManager.getCleanupPolicy).mockReturnValue('session');
        vi.mocked(mockManager.getManaged).mockReturnValue([makeManagedWorktree()]);
        vi.mocked(mockManager.checkDirty).mockResolvedValue(false);
        vi.mocked(mockManager.cleanup).mockResolvedValue([]);

        const handler = new SessionCleanupHandler(mockManager, promptFn);
        await handler.handleExit();

        expect(promptFn).not.toHaveBeenCalled();
      });

      it('should handle empty managed list gracefully', async () => {
        vi.mocked(mockManager.getCleanupPolicy).mockReturnValue('session');
        vi.mocked(mockManager.getManaged).mockReturnValue([]);
        vi.mocked(mockManager.cleanup).mockResolvedValue([]);

        const handler = new SessionCleanupHandler(mockManager, promptFn);
        const result = await handler.handleExit();

        expect(result.closed).toBe(true);
        expect(result.cancelled).toBe(false);
        expect(result.removed).toEqual([]);
        expect(result.preservedDirty).toEqual([]);
        expect(promptFn).not.toHaveBeenCalled();
      });
    });

    describe('dirty worktrees - CANCEL', () => {
      it('should return cancelled=true and closed=false', async () => {
        const dirtyWt = makeManagedWorktree({ path: '/wt/dirty' });
        vi.mocked(mockManager.getCleanupPolicy).mockReturnValue('session');
        vi.mocked(mockManager.getManaged).mockReturnValue([dirtyWt]);
        vi.mocked(mockManager.checkDirty).mockResolvedValue(true);
        promptFn.mockResolvedValue(ExitChoice.CANCEL);

        const handler = new SessionCleanupHandler(mockManager, promptFn);
        const result = await handler.handleExit();

        expect(result.closed).toBe(false);
        expect(result.cancelled).toBe(true);
        expect(result.removed).toEqual([]);
        expect(result.preservedDirty).toEqual(['/wt/dirty']);
      });

      it('should call prompt with dirty paths', async () => {
        const dirty1 = makeManagedWorktree({ path: '/wt/d1' });
        const dirty2 = makeManagedWorktree({ path: '/wt/d2' });
        const clean1 = makeManagedWorktree({ path: '/wt/c1' });

        vi.mocked(mockManager.getCleanupPolicy).mockReturnValue('session');
        vi.mocked(mockManager.getManaged).mockReturnValue([dirty1, clean1, dirty2]);
        vi.mocked(mockManager.checkDirty)
          .mockResolvedValueOnce(true)
          .mockResolvedValueOnce(false)
          .mockResolvedValueOnce(true);
        promptFn.mockResolvedValue(ExitChoice.CANCEL);

        const handler = new SessionCleanupHandler(mockManager, promptFn);
        await handler.handleExit();

        expect(promptFn).toHaveBeenCalledWith(['/wt/d1', '/wt/d2']);
      });

      it('should not call cleanup when cancelled', async () => {
        vi.mocked(mockManager.getCleanupPolicy).mockReturnValue('session');
        vi.mocked(mockManager.getManaged).mockReturnValue([
          makeManagedWorktree({ path: '/wt/dirty' }),
        ]);
        vi.mocked(mockManager.checkDirty).mockResolvedValue(true);
        promptFn.mockResolvedValue(ExitChoice.CANCEL);

        const handler = new SessionCleanupHandler(mockManager, promptFn);
        await handler.handleExit();

        expect(mockManager.cleanup).not.toHaveBeenCalled();
      });
    });

    describe('dirty worktrees - PRESERVE', () => {
      it('should remove only clean worktrees and preserve dirty ones', async () => {
        const dirty = makeManagedWorktree({ path: '/wt/dirty', branch: 'dirty-branch' });
        const clean = makeManagedWorktree({ path: '/wt/clean', branch: 'clean-branch' });

        vi.mocked(mockManager.getCleanupPolicy).mockReturnValue('session');
        vi.mocked(mockManager.getManaged).mockReturnValue([dirty, clean]);
        vi.mocked(mockManager.checkDirty)
          .mockResolvedValueOnce(true)
          .mockResolvedValueOnce(false);
        promptFn.mockResolvedValue(ExitChoice.PRESERVE);
        vi.mocked(mockManager.cleanup).mockResolvedValue(['/wt/clean']);

        const handler = new SessionCleanupHandler(mockManager, promptFn);
        const result = await handler.handleExit();

        expect(result.closed).toBe(true);
        expect(result.cancelled).toBe(false);
        expect(result.removed).toEqual(['/wt/clean']);
        expect(result.preservedDirty).toEqual(['/wt/dirty']);
      });

      it('should call cleanup with only clean worktrees as selected', async () => {
        const dirty = makeManagedWorktree({ path: '/wt/dirty' });
        const clean1 = makeManagedWorktree({ path: '/wt/clean1' });
        const clean2 = makeManagedWorktree({ path: '/wt/clean2' });

        vi.mocked(mockManager.getCleanupPolicy).mockReturnValue('session');
        vi.mocked(mockManager.getManaged).mockReturnValue([dirty, clean1, clean2]);
        vi.mocked(mockManager.checkDirty)
          .mockResolvedValueOnce(true)
          .mockResolvedValueOnce(false)
          .mockResolvedValueOnce(false);
        promptFn.mockResolvedValue(ExitChoice.PRESERVE);
        vi.mocked(mockManager.cleanup).mockResolvedValue(['/wt/clean1', '/wt/clean2']);

        const handler = new SessionCleanupHandler(mockManager, promptFn, 'Debian');
        await handler.handleExit();

        expect(mockManager.cleanup).toHaveBeenCalledWith({
          selected: [clean1, clean2],
          distribution: 'Debian',
        });
      });

      it('should handle all dirty worktrees with PRESERVE (no clean to remove)', async () => {
        const dirty1 = makeManagedWorktree({ path: '/wt/d1' });
        const dirty2 = makeManagedWorktree({ path: '/wt/d2' });

        vi.mocked(mockManager.getCleanupPolicy).mockReturnValue('session');
        vi.mocked(mockManager.getManaged).mockReturnValue([dirty1, dirty2]);
        vi.mocked(mockManager.checkDirty).mockResolvedValue(true);
        promptFn.mockResolvedValue(ExitChoice.PRESERVE);
        vi.mocked(mockManager.cleanup).mockResolvedValue([]);

        const handler = new SessionCleanupHandler(mockManager, promptFn);
        const result = await handler.handleExit();

        expect(result.closed).toBe(true);
        expect(result.cancelled).toBe(false);
        expect(result.removed).toEqual([]);
        expect(result.preservedDirty).toEqual(['/wt/d1', '/wt/d2']);
      });
    });

    describe('dirty worktrees - CLEAN', () => {
      it('should remove all worktrees including dirty ones', async () => {
        const dirty = makeManagedWorktree({ path: '/wt/dirty' });
        const clean = makeManagedWorktree({ path: '/wt/clean' });

        vi.mocked(mockManager.getCleanupPolicy).mockReturnValue('session');
        vi.mocked(mockManager.getManaged).mockReturnValue([dirty, clean]);
        vi.mocked(mockManager.checkDirty)
          .mockResolvedValueOnce(true)
          .mockResolvedValueOnce(false);
        promptFn.mockResolvedValue(ExitChoice.CLEAN);
        vi.mocked(mockManager.cleanup).mockResolvedValue(['/wt/dirty', '/wt/clean']);

        const handler = new SessionCleanupHandler(mockManager, promptFn);
        const result = await handler.handleExit();

        expect(result.closed).toBe(true);
        expect(result.cancelled).toBe(false);
        expect(result.removed).toEqual(['/wt/dirty', '/wt/clean']);
        expect(result.preservedDirty).toEqual([]);
      });

      it('should call cleanup without selected filter (removes all)', async () => {
        const dirty = makeManagedWorktree({ path: '/wt/dirty' });

        vi.mocked(mockManager.getCleanupPolicy).mockReturnValue('session');
        vi.mocked(mockManager.getManaged).mockReturnValue([dirty]);
        vi.mocked(mockManager.checkDirty).mockResolvedValue(true);
        promptFn.mockResolvedValue(ExitChoice.CLEAN);
        vi.mocked(mockManager.cleanup).mockResolvedValue(['/wt/dirty']);

        const handler = new SessionCleanupHandler(mockManager, promptFn, 'Ubuntu');
        await handler.handleExit();

        expect(mockManager.cleanup).toHaveBeenCalledWith({
          distribution: 'Ubuntu',
        });
      });
    });

    describe('distribution parameter', () => {
      it('should pass distribution to checkDirty', async () => {
        const wt = makeManagedWorktree({ path: '/wt/a' });

        vi.mocked(mockManager.getCleanupPolicy).mockReturnValue('session');
        vi.mocked(mockManager.getManaged).mockReturnValue([wt]);
        vi.mocked(mockManager.checkDirty).mockResolvedValue(false);
        vi.mocked(mockManager.cleanup).mockResolvedValue(['/wt/a']);

        const handler = new SessionCleanupHandler(mockManager, promptFn, 'Ubuntu-22.04');
        await handler.handleExit();

        expect(mockManager.checkDirty).toHaveBeenCalledWith(wt, 'Ubuntu-22.04');
      });

      it('should pass undefined distribution when not provided', async () => {
        const wt = makeManagedWorktree({ path: '/wt/a' });

        vi.mocked(mockManager.getCleanupPolicy).mockReturnValue('session');
        vi.mocked(mockManager.getManaged).mockReturnValue([wt]);
        vi.mocked(mockManager.checkDirty).mockResolvedValue(false);
        vi.mocked(mockManager.cleanup).mockResolvedValue(['/wt/a']);

        const handler = new SessionCleanupHandler(mockManager, promptFn);
        await handler.handleExit();

        expect(mockManager.checkDirty).toHaveBeenCalledWith(wt, undefined);
        expect(mockManager.cleanup).toHaveBeenCalledWith({
          distribution: undefined,
        });
      });
    });
  });
});
