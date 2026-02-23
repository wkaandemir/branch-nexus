import simpleGit, { type SimpleGit } from 'simple-git';
import { logger } from '../utils/logger.js';
import { BranchNexusError, ExitCode } from '../types/errors.js';
import { posixPath } from '../utils/validators.js';

export async function materializeRemoteBranch(
  repoPath: string,
  remoteBranch: string,
  _distribution?: string
): Promise<string> {
  const normalizedRepo = posixPath(repoPath);

  if (!remoteBranch.includes('/')) {
    throw new BranchNexusError(
      `Invalid remote branch format: ${remoteBranch}`,
      ExitCode.VALIDATION_ERROR,
      'Use branch names like origin/feature-x.'
    );
  }

  const localBranch = remoteBranch.split('/').slice(1).join('/');
  logger.debug(
    `Materializing remote branch repo=${normalizedRepo} remote=${remoteBranch} local=${localBranch}`
  );

  const git: SimpleGit = simpleGit(normalizedRepo);

  try {
    const localBranches = await git.branchLocal();
    if (localBranches.all.includes(localBranch)) {
      logger.debug(`Local branch already exists: ${localBranch}`);
      return localBranch;
    }
  } catch {
    // Continue with creation
  }

  try {
    await git.branch(['--track', localBranch, remoteBranch]);
    logger.debug(`Created tracking branch: ${localBranch}`);
    return localBranch;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new BranchNexusError(
      `Failed to materialize remote branch ${remoteBranch}`,
      ExitCode.GIT_ERROR,
      message
    );
  }
}

export async function fetchRemote(repoPath: string, remote = 'origin'): Promise<void> {
  const git: SimpleGit = simpleGit(posixPath(repoPath));

  try {
    await git.fetch(remote);
    logger.debug(`Fetched remote: ${remote}`);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new BranchNexusError(`Failed to fetch from ${remote}`, ExitCode.GIT_ERROR, message);
  }
}

export async function cloneRepository(url: string, targetPath: string): Promise<void> {
  logger.debug(`Cloning repository ${url} to ${targetPath}`);

  const git: SimpleGit = simpleGit();

  try {
    await git.clone(url, targetPath);
    logger.debug(`Cloned repository to ${targetPath}`);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new BranchNexusError(`Failed to clone repository: ${url}`, ExitCode.GIT_ERROR, message);
  }
}
