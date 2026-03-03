import { logger } from '../utils/logger.js';
import { BranchNexusError, ExitCode } from '../types/errors.js';
import {
  type WorktreeAssignment,
  type ManagedWorktree,
  type CleanupPolicy,
  createManagedWorktree,
} from '../types/index.js';
import { runCommand, runCommandViaWSL } from '../runtime/shell.js';
import { hasDistribution } from '../utils/validators.js';

const SANITIZE_PATTERN = /[^A-Za-z0-9._-]+/g;

export class WorktreeManager {
  private baseDir: string;
  private cleanupPolicy: CleanupPolicy;
  private posixMode: boolean;
  private managed: ManagedWorktree[] = [];

  constructor(baseDir: string, cleanupPolicy: CleanupPolicy = 'session') {
    this.baseDir = baseDir;
    this.cleanupPolicy = cleanupPolicy;
    this.posixMode = false;
  }

  setPosixMode(enabled: boolean): void {
    this.posixMode = enabled;
  }

  private safe(value: string): string {
    const cleaned = value.replace(SANITIZE_PATTERN, '-').replace(/^-+|-+$/g, '');
    return cleaned || 'default';
  }

  private asPosix(value: string): string {
    let normalized = value.replace(/\\/g, '/');
    while (normalized.startsWith('//')) {
      normalized = normalized.slice(1);
    }
    return normalized;
  }

  private commandPath(value: string): string {
    return this.posixMode ? this.asPosix(value) : value;
  }

  buildWorktreePath(assignment: WorktreeAssignment): string {
    const repoName = this.safe(this.asPosix(assignment.repoPath).split('/').pop() ?? 'repo');
    // Strip bnx- prefix from branch name for cleaner path
    const branchSlug = this.safe(assignment.branch.replace(/^bnx-/, '').replace(/^origin\//, ''));
    return `${this.baseDir}/${repoName}/${branchSlug}`;
  }

  async addWorktree(
    assignment: WorktreeAssignment,
    distribution?: string
  ): Promise<ManagedWorktree> {
    const target = this.buildWorktreePath(assignment);
    logger.debug(
      `Adding worktree pane=${assignment.pane} repo=${assignment.repoPath} branch=${assignment.branch} target=${target}`
    );

    const repoPath = this.commandPath(assignment.repoPath);
    const targetPath = this.commandPath(target);

    // Prune stale worktree references first
    const pruneCmd = ['git', '-C', repoPath, 'worktree', 'prune'];
    try {
      if (hasDistribution(distribution)) {
        await runCommandViaWSL(distribution, pruneCmd);
      } else {
        await runCommand(pruneCmd);
      }
    } catch (error) {
      logger.debug(
        `Prune failed (non-critical): ${error instanceof Error ? error.message : String(error)}`
      );
    }

    const existingWorktrees = await this.getWorktreesForBranch(
      assignment.repoPath,
      assignment.branch,
      distribution
    );

    if (existingWorktrees.length > 0) {
      const existingPath = existingWorktrees[0];
      if (this.isUnderBaseDir(existingPath) || existingPath === repoPath) {
        logger.info(`Reusing existing worktree at ${existingPath}`);
        const managed = createManagedWorktree(assignment, existingPath);
        this.managed.push(managed);
        return managed;
      }

      // Remove stale worktree from a previous run and continue
      logger.warn(`Removing stale worktree at ${existingPath}`);
      const removeCmd = [
        'git',
        '-C',
        repoPath,
        'worktree',
        'remove',
        '--force',
        this.commandPath(existingPath),
      ];
      try {
        if (hasDistribution(distribution)) {
          await runCommandViaWSL(distribution, removeCmd);
        } else {
          await runCommand(removeCmd);
        }
        logger.debug(`Removed stale worktree: ${existingPath}`);
      } catch (removeError) {
        logger.debug(
          `Remove failed, trying prune: ${removeError instanceof Error ? removeError.message : String(removeError)}`
        );
        // If remove fails, try prune and continue
        const pruneCmd = ['git', '-C', repoPath, 'worktree', 'prune'];
        if (hasDistribution(distribution)) {
          await runCommandViaWSL(distribution, pruneCmd);
        } else {
          await runCommand(pruneCmd);
        }
        logger.debug('Pruned stale worktree references');
      }
    }

    const cmd = ['git', '-C', repoPath, 'worktree', 'add', targetPath, assignment.branch];

    try {
      if (hasDistribution(distribution)) {
        await runCommandViaWSL(distribution, cmd);
      } else {
        await runCommand(cmd);
      }

      logger.debug(`Created worktree at ${target}`);
      const managed = createManagedWorktree(assignment, target);
      this.managed.push(managed);
      return managed;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      throw new BranchNexusError(
        `Failed to create worktree for pane ${assignment.pane}`,
        ExitCode.GIT_ERROR,
        message
      );
    }
  }

  async materialize(
    assignments: WorktreeAssignment[],
    distribution?: string
  ): Promise<ManagedWorktree[]> {
    logger.debug(`Materializing ${assignments.length} worktree assignments`);
    const created: ManagedWorktree[] = [];

    for (const assignment of assignments.sort((a, b) => a.pane - b.pane)) {
      created.push(await this.addWorktree(assignment, distribution));
    }

    return created;
  }

  async checkDirty(worktree: ManagedWorktree, distribution?: string): Promise<boolean> {
    const cmd = ['git', '-C', this.commandPath(worktree.path), 'status', '--porcelain'];

    try {
      const result = hasDistribution(distribution)
        ? await runCommandViaWSL(distribution, cmd)
        : await runCommand(cmd);

      const dirty = result.stdout.trim().length > 0;
      logger.debug(`Dirty check path=${worktree.path} dirty=${dirty}`);
      return dirty;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      throw new BranchNexusError(
        `Dirty check failed for ${worktree.path}`,
        ExitCode.GIT_ERROR,
        message
      );
    }
  }

  async cleanup(options?: {
    force?: boolean;
    selected?: ManagedWorktree[];
    ignorePolicy?: boolean;
    distribution?: string;
  }): Promise<string[]> {
    if (this.cleanupPolicy === 'persistent' && options?.ignorePolicy !== true) {
      logger.debug('Cleanup skipped due to persistent policy');
      return [];
    }

    const targets = options?.selected ?? this.managed;
    const removed: string[] = [];
    const removedPaths = new Set<string>();

    for (const worktree of targets) {
      const worktreePath = this.commandPath(worktree.path);
      if (removedPaths.has(worktreePath)) {
        continue;
      }
      removedPaths.add(worktreePath);

      const cmd = ['git', '-C', this.commandPath(worktree.repoPath), 'worktree', 'remove'];
      if (options?.force !== false) {
        cmd.push('--force');
      }
      cmd.push(worktreePath);

      try {
        if (hasDistribution(options?.distribution)) {
          await runCommandViaWSL(options.distribution, cmd);
        } else {
          await runCommand(cmd);
        }
        removed.push(worktreePath);
        logger.debug(`Removed worktree at ${worktreePath}`);
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        throw new BranchNexusError(
          `Cleanup failed for ${worktreePath}`,
          ExitCode.GIT_ERROR,
          message
        );
      }
    }

    return removed;
  }

  trackExisting(assignment: WorktreeAssignment, path: string): ManagedWorktree {
    logger.debug(
      `Tracking existing worktree pane=${assignment.pane} branch=${assignment.branch} path=${path}`
    );
    const managed = createManagedWorktree(assignment, path);
    this.managed.push(managed);
    return managed;
  }

  getManaged(): ManagedWorktree[] {
    return [...this.managed];
  }

  getCleanupPolicy(): CleanupPolicy {
    return this.cleanupPolicy;
  }

  private isUnderBaseDir(path: string): boolean {
    const normalizedBase = this.asPosix(this.baseDir);
    const normalizedPath = this.asPosix(path);
    return normalizedPath.startsWith(normalizedBase);
  }

  private async getWorktreesForBranch(
    repoPath: string,
    branch: string,
    distribution?: string
  ): Promise<string[]> {
    const cmd = ['git', '-C', this.commandPath(repoPath), 'worktree', 'list', '--porcelain'];

    try {
      const result = hasDistribution(distribution)
        ? await runCommandViaWSL(distribution, cmd)
        : await runCommand(cmd);

      const worktrees: string[] = [];
      let currentWorktree = '';
      const expectedRef = branch.startsWith('refs/heads/') ? branch : `refs/heads/${branch}`;

      for (const line of result.stdout.split('\n')) {
        const trimmed = line.trim();
        if (trimmed === '') continue;

        if (trimmed.startsWith('worktree ')) {
          currentWorktree = trimmed.slice(9).trim();
        } else if (trimmed.startsWith('branch ') && currentWorktree !== '') {
          const branchRef = trimmed.slice(7).trim();
          if (branchRef === expectedRef) {
            worktrees.push(currentWorktree);
          }
        }
      }

      return worktrees;
    } catch (error) {
      logger.debug(
        `Failed to list worktrees for branch ${branch}: ${error instanceof Error ? error.message : String(error)}`
      );
      return [];
    }
  }
}
