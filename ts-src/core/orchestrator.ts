import {
  type Layout,
  type CleanupPolicy,
  type ColorTheme,
  type WorktreeAssignment,
  type ManagedWorktree,
  createWorktreeAssignment,
} from '../types/index.js';
import { BranchNexusError, ExitCode } from '../types/errors.js';
import { validateDistribution } from '../runtime/wsl.js';
import { buildLayoutCommands } from '../tmux/layouts.js';
import { startSession } from '../tmux/session.js';
import { WorktreeManager } from '../git/worktree.js';
import { materializeRemoteBranch } from '../git/clone.js';
import { logger } from '../utils/logger.js';
import { Platform, detectPlatform } from '../runtime/platform.js';

export interface OrchestrationRequest {
  distribution: string;
  availableDistributions: string[];
  layout: Layout;
  cleanupPolicy: CleanupPolicy;
  assignments: WorktreeAssignment[];
  worktreeBase: string;
  sessionName?: string;
  tmuxAutoInstall: boolean;
  colorTheme?: ColorTheme;
  paneNames?: string[];
  displayBranches?: string[];
  startupCommands?: string[];
}

export interface OrchestrationResult {
  worktrees: ManagedWorktree[];
  executedCommands: string[][];
}

export async function orchestrate(request: OrchestrationRequest): Promise<OrchestrationResult> {
  const platform = detectPlatform();
  const isWindows = platform === Platform.WINDOWS;
  const sessionName =
    request.sessionName !== undefined && request.sessionName !== ''
      ? request.sessionName
      : 'branchnexus';

  logger.debug(
    `Starting orchestration distribution=${request.distribution} layout=${request.layout} panes=${request.assignments.length}`
  );

  // Validate WSL distribution on Windows
  if (isWindows && request.distribution !== '') {
    if (!validateDistribution(request.distribution, request.availableDistributions)) {
      logger.error(`Invalid WSL distribution: ${request.distribution}`);
      throw new BranchNexusError(
        `Invalid WSL distribution: ${request.distribution}`,
        ExitCode.RUNTIME_ERROR,
        'Re-open WSL selection and choose a discovered distribution.'
      );
    }
  }

  // tmux check is done in run.ts before orchestrate
  logger.debug('Proceeding with orchestration');

  const worktreeManager = new WorktreeManager(request.worktreeBase, request.cleanupPolicy);

  if (isWindows) {
    worktreeManager.setPosixMode(true);
  }

  const executedCommands: string[][] = [];

  // Materialize remote branches
  const normalizedAssignments: WorktreeAssignment[] = [];
  logger.debug('Preparing selected branches');

  for (const assignment of request.assignments.sort((a, b) => a.pane - b.pane)) {
    let localBranch = assignment.branch;

    if (assignment.branch.startsWith('origin/')) {
      logger.debug(
        `Materializing remote branch pane=${assignment.pane} repo=${assignment.repoPath} branch=${assignment.branch}`
      );

      localBranch = await materializeRemoteBranch(assignment.repoPath, assignment.branch);
    }

    normalizedAssignments.push(
      createWorktreeAssignment(assignment.pane, assignment.repoPath, localBranch)
    );
  }

  logger.debug(`Prepared ${normalizedAssignments.length} pane assignments`);

  let worktrees: ManagedWorktree[] = [];

  try {
    // Create worktrees
    logger.debug('Creating worktrees');
    worktrees = await worktreeManager.materialize(
      normalizedAssignments,
      isWindows ? request.distribution : undefined
    );
    logger.debug(`Created ${worktrees.length} worktrees`);

    // Build tmux layout commands
    const sorted = worktrees.sort((a, b) => a.pane - b.pane);
    const panePaths = sorted.map((w) => w.path);
    // Use original branch names for display, not internal fork names like main-pane-2
    const paneBranches = request.displayBranches ?? sorted.map((w) => w.branch);

    const tmuxCommands = buildLayoutCommands(
      sessionName, request.layout, panePaths, request.colorTheme, paneBranches, request.paneNames,
      request.startupCommands
    );

    // Start tmux session
    logger.debug('Starting tmux session');
    await startSession(sessionName, tmuxCommands, isWindows ? request.distribution : undefined);

    logger.debug('Orchestration finished successfully');

    return {
      worktrees,
      executedCommands,
    };
  } catch (error) {
    // Rollback on failure
    if (worktrees.length > 0) {
      try {
        const removed = await worktreeManager.cleanup({
          ignorePolicy: true,
          selected: worktrees,
          distribution: isWindows ? request.distribution : undefined,
        });
        logger.warn(`Orchestration rollback removed ${removed.length} worktrees`);
      } catch (cleanupError) {
        logger.error(`Orchestration rollback cleanup failed: ${String(cleanupError)}`);
      }
    }

    throw error;
  }
}
