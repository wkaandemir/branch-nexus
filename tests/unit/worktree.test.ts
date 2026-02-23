import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  type WorktreeAssignment,
  type ManagedWorktree,
  createWorktreeAssignment,
  createManagedWorktree,
} from '../../ts-src/types/worktree.js';

describe('worktree types', () => {
  describe('createWorktreeAssignment', () => {
    it('should create a valid assignment', () => {
      const assignment = createWorktreeAssignment(0, '/repo/path', 'main');
      expect(assignment).toEqual({
        pane: 0,
        repoPath: '/repo/path',
        branch: 'main',
      });
    });

    it('should create assignments for different panes', () => {
      const a1 = createWorktreeAssignment(0, '/repo', 'main');
      const a2 = createWorktreeAssignment(1, '/repo', 'develop');
      const a3 = createWorktreeAssignment(2, '/other-repo', 'feature');

      expect(a1.pane).toBe(0);
      expect(a2.pane).toBe(1);
      expect(a3.pane).toBe(2);
      expect(a3.repoPath).toBe('/other-repo');
    });
  });

  describe('createManagedWorktree', () => {
    it('should create a managed worktree from assignment', () => {
      const assignment = createWorktreeAssignment(1, '/repo', 'feature');
      const managed = createManagedWorktree(assignment, '/worktrees/repo/feature');

      expect(managed).toEqual({
        pane: 1,
        repoPath: '/repo',
        branch: 'feature',
        path: '/worktrees/repo/feature',
      });
    });

    it('should preserve all assignment fields', () => {
      const assignment: WorktreeAssignment = {
        pane: 3,
        repoPath: '/path/to/repo',
        branch: 'origin/feature-branch',
      };
      const managed = createManagedWorktree(assignment, '/wt/repo/feature-branch');

      expect(managed.pane).toBe(assignment.pane);
      expect(managed.repoPath).toBe(assignment.repoPath);
      expect(managed.branch).toBe(assignment.branch);
      expect(managed.path).toBe('/wt/repo/feature-branch');
    });
  });
});

describe('session types', () => {
  let createTerminalSnapshot: typeof import('../../ts-src/types/session.js').createTerminalSnapshot;
  let createSessionSnapshot: typeof import('../../ts-src/types/session.js').createSessionSnapshot;
  let isSessionSnapshot: typeof import('../../ts-src/types/session.js').isSessionSnapshot;
  let ExitChoice: typeof import('../../ts-src/types/session.js').ExitChoice;

  beforeEach(async () => {
    const mod = await import('../../ts-src/types/session.js');
    createTerminalSnapshot = mod.createTerminalSnapshot;
    createSessionSnapshot = mod.createSessionSnapshot;
    isSessionSnapshot = mod.isSessionSnapshot;
    ExitChoice = mod.ExitChoice;
  });

  describe('createTerminalSnapshot', () => {
    it('should create a terminal snapshot', () => {
      const snap = createTerminalSnapshot('t1', 'My Terminal', 'native', '/repo', 'main');
      expect(snap).toEqual({
        terminalId: 't1',
        title: 'My Terminal',
        runtime: 'native',
        repoPath: '/repo',
        branch: 'main',
      });
    });
  });

  describe('createSessionSnapshot', () => {
    it('should create a session snapshot', () => {
      const terminals = [createTerminalSnapshot('t1', 'Alpha', 'native', '/repo', 'main')];
      const snap = createSessionSnapshot('grid', 2, terminals, 't1');

      expect(snap.layout).toBe('grid');
      expect(snap.templateCount).toBe(2);
      expect(snap.focusedTerminalId).toBe('t1');
      expect(snap.terminals).toHaveLength(1);
    });

    it('should default focusedTerminalId to empty string', () => {
      const snap = createSessionSnapshot('horizontal', 4, []);
      expect(snap.focusedTerminalId).toBe('');
    });
  });

  describe('isSessionSnapshot', () => {
    it('should return true for valid snapshot object', () => {
      expect(
        isSessionSnapshot({
          layout: 'grid',
          templateCount: 4,
          terminals: [],
        })
      ).toBe(true);
    });

    it('should return false for null', () => {
      expect(isSessionSnapshot(null)).toBe(false);
    });

    it('should return false for undefined', () => {
      expect(isSessionSnapshot(undefined)).toBe(false);
    });

    it('should return false for string', () => {
      expect(isSessionSnapshot('not a snapshot')).toBe(false);
    });

    it('should return false for missing layout', () => {
      expect(isSessionSnapshot({ templateCount: 4, terminals: [] })).toBe(false);
    });

    it('should return false for missing templateCount', () => {
      expect(isSessionSnapshot({ layout: 'grid', terminals: [] })).toBe(false);
    });

    it('should return false for non-array terminals', () => {
      expect(isSessionSnapshot({ layout: 'grid', templateCount: 4, terminals: 'bad' })).toBe(false);
    });
  });

  describe('ExitChoice', () => {
    it('should have correct values', () => {
      expect(ExitChoice.CANCEL).toBe('Vazgec');
      expect(ExitChoice.PRESERVE).toBe('Koruyarak Cik');
      expect(ExitChoice.CLEAN).toBe('Temizleyerek Cik');
    });
  });
});
