import simpleGit, { type SimpleGit } from 'simple-git';
import { logger } from '../utils/logger.js';
import { BranchNexusError, ExitCode } from '../types/errors.js';

export interface BranchListResult {
  branches: string[];
  warning?: string;
}

export async function listLocalBranches(repoPath: string): Promise<BranchListResult> {
  logger.debug(`Listing local branches for ${repoPath}`);

  const git: SimpleGit = simpleGit(repoPath);

  try {
    const isRepo = await git.checkIsRepo();
    if (!isRepo) {
      throw new BranchNexusError(
        `Not a git repository: ${repoPath}`,
        ExitCode.GIT_ERROR,
        'Check the path and ensure it is a valid Git repository.'
      );
    }
  } catch (error) {
    if (error instanceof BranchNexusError) {
      throw error;
    }
    throw new BranchNexusError(
      `Repository is not accessible: ${repoPath}`,
      ExitCode.GIT_ERROR,
      'Check the path and ensure it is a valid Git repository.'
    );
  }

  let warning: string | undefined;

  try {
    const status = await git.status();
    if (status.detached) {
      warning = 'Detached HEAD detected. Branch operations may be limited.';
      logger.warn(`Detached HEAD detected repo=${repoPath}`);
    }
  } catch {
    // Ignore status check errors
  }

  try {
    const localBranches = await git.branchLocal();

    // Filter out BranchNexus fork branches (e.g. main-pane-2, feature/x-pane-3)
    const FORK_BRANCH_RE = /-pane-\d+$/;
    let branchNames = localBranches.all.filter((b) => !FORK_BRANCH_RE.test(b)).sort();

    // Also fetch remote branches for more options
    try {
      await git.fetch(['--all']);
      const remoteBranches = await git.branch(['-r']);
      const remoteNames = remoteBranches.all
        .filter((b) => !b.includes('HEAD') && !FORK_BRANCH_RE.test(b))
        .sort();

      // Combine local and remote branches, local first
      branchNames = [...branchNames, ...remoteNames];
      logger.debug(
        `Discovered ${localBranches.all.length} local + ${remoteNames.length} remote branches`
      );
    } catch (fetchError) {
      logger.debug('Could not fetch remote branches');
    }

    if (branchNames.length === 0) {
      throw new BranchNexusError(
        'No branches found.',
        ExitCode.GIT_ERROR,
        'Create an initial commit and at least one branch.'
      );
    }

    logger.debug(`Total ${branchNames.length} branches available`);

    return {
      branches: branchNames,
      warning,
    };
  } catch (error) {
    if (error instanceof BranchNexusError) {
      throw error;
    }
    throw new BranchNexusError(
      `Failed to list branches for ${repoPath}`,
      ExitCode.GIT_ERROR,
      'Run `git branch -a` manually to inspect repository state.'
    );
  }
}

export async function getCurrentBranch(repoPath: string): Promise<string> {
  const git: SimpleGit = simpleGit(repoPath);
  const status = await git.status();
  return status.current ?? 'HEAD';
}

export async function branchExists(repoPath: string, branch: string): Promise<boolean> {
  const git: SimpleGit = simpleGit(repoPath);
  const branches = await git.branchLocal();
  return branches.all.includes(branch);
}

export async function remoteBranchExists(repoPath: string, remoteBranch: string): Promise<boolean> {
  const git: SimpleGit = simpleGit(repoPath);
  const branches = await git.branch(['-r']);
  return branches.all.includes(remoteBranch);
}
