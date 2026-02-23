import {
  type RuntimeSessionSnapshot,
  type SessionTerminalSnapshot,
  type SessionCleanupResult,
  type ManagedWorktree,
  ExitChoice,
  type RuntimeKind,
  isSessionSnapshot,
} from '../types/index.js';
import { WorktreeManager } from '../git/worktree.js';
import { logger } from '../utils/logger.js';

const TERMINAL_MIN = 2;
const TERMINAL_MAX = 16;

function validateTerminalCount(value: number): number {
  if (value < TERMINAL_MIN || value > TERMINAL_MAX) {
    throw new Error(`Invalid terminal count: ${value}`);
  }
  return value;
}

export function buildRuntimeSnapshot(
  layout: string,
  templateCount: number,
  terminals: SessionTerminalSnapshot[],
  focusedTerminalId = ''
): RuntimeSessionSnapshot {
  const count = validateTerminalCount(templateCount);
  return {
    layout,
    templateCount: count,
    focusedTerminalId,
    terminals,
  };
}

export function parseRuntimeSnapshot(raw: unknown): RuntimeSessionSnapshot | null {
  if (!isSessionSnapshot(raw)) {
    return null;
  }

  const snapshot = raw;

  if (snapshot.terminals.length === 0) {
    return null;
  }

  try {
    validateTerminalCount(snapshot.templateCount);
  } catch {
    return null;
  }

  const terminals: SessionTerminalSnapshot[] = [];
  for (const item of snapshot.terminals) {
    if (!item.terminalId) {
      return null;
    }

    const runtime = normalizeRuntimeKind(item.runtime);
    if (!runtime) {
      return null;
    }

    terminals.push({
      terminalId: item.terminalId.trim(),
      title: item.title?.trim() || item.terminalId,
      runtime,
      repoPath: item.repoPath?.trim() || '',
      branch: item.branch?.trim() || '',
    });
  }

  return {
    layout: snapshot.layout || 'grid',
    templateCount: snapshot.templateCount,
    focusedTerminalId: snapshot.focusedTerminalId?.trim() || '',
    terminals,
  };
}

function normalizeRuntimeKind(value: string): RuntimeKind | null {
  const normalized = value?.toLowerCase().trim();
  if (normalized === 'wsl') return 'wsl';
  if (normalized === 'powershell') return 'powershell';
  if (normalized === 'native') return 'native';
  return null;
}

export class SessionCleanupHandler {
  private manager: WorktreeManager;
  private prompt: (dirty: string[]) => Promise<ExitChoice>;
  private distribution?: string;

  constructor(
    manager: WorktreeManager,
    prompt: (dirty: string[]) => Promise<ExitChoice>,
    distribution?: string
  ) {
    this.manager = manager;
    this.prompt = prompt;
    this.distribution = distribution;
  }

  async handleExit(): Promise<SessionCleanupResult> {
    if (this.manager.getCleanupPolicy() === 'persistent') {
      logger.debug('Session cleanup skipped due to persistent policy');
      return {
        closed: true,
        cancelled: false,
        removed: [],
        preservedDirty: this.manager.getManaged().map((w) => w.path),
      };
    }

    const dirty: ManagedWorktree[] = [];
    const clean: ManagedWorktree[] = [];

    for (const worktree of this.manager.getManaged()) {
      const isDirty = await this.manager.checkDirty(worktree, this.distribution);
      if (isDirty) {
        dirty.push(worktree);
      } else {
        clean.push(worktree);
      }
    }

    logger.debug(`Cleanup check complete dirty=${dirty.length} clean=${clean.length}`);

    if (dirty.length === 0) {
      const removed = await this.manager.cleanup({
        distribution: this.distribution,
      });
      logger.debug(`All worktrees clean; removed=${removed.length}`);
      return {
        closed: true,
        cancelled: false,
        removed,
        preservedDirty: [],
      };
    }

    const choice = await this.prompt(dirty.map((w) => w.path));
    logger.info(`Cleanup prompt result choice=${choice} dirty_count=${dirty.length}`);

    if (choice === ExitChoice.CANCEL) {
      return {
        closed: false,
        cancelled: true,
        removed: [],
        preservedDirty: dirty.map((w) => w.path),
      };
    }

    if (choice === ExitChoice.PRESERVE) {
      const removedClean = await this.manager.cleanup({
        selected: clean,
        distribution: this.distribution,
      });
      logger.debug(`Preserve dirty worktrees; removed clean=${removedClean.length}`);
      return {
        closed: true,
        cancelled: false,
        removed: removedClean,
        preservedDirty: dirty.map((w) => w.path),
      };
    }

    const removedAll = await this.manager.cleanup({
      distribution: this.distribution,
    });
    logger.debug(`Cleanup forced for all worktrees removed=${removedAll.length}`);
    return {
      closed: true,
      cancelled: false,
      removed: removedAll,
      preservedDirty: [],
    };
  }
}
