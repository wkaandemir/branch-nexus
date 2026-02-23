import simpleGit, { type SimpleGit } from 'simple-git';
import { logger } from '../utils/logger.js';
import { BranchNexusError, ExitCode } from '../types/errors.js';
import { posixPath } from '../utils/validators.js';
import { parseGitHubUrl, checkRepoVisibility } from '../github/api.js';
import { loadConfig } from '../core/config.js';

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

export interface AccessCheckResult {
  allowed: boolean;
  isPrivate: boolean;
}

/**
 * Checks whether a GitHub repository is accessible before cloning.
 * For non-GitHub URLs, skips the check and allows.
 * For private repos without a token, throws BranchNexusError.
 */
export async function checkRepositoryAccess(url: string): Promise<AccessCheckResult> {
  const parsed = parseGitHubUrl(url);

  if (parsed === null) {
    // Non-GitHub URL — skip check
    return { allowed: true, isPrivate: false };
  }

  const { owner, repo } = parsed;

  // Unauthenticated check first
  const visibility = await checkRepoVisibility(owner, repo);

  if (visibility === 'public') {
    return { allowed: true, isPrivate: false };
  }

  if (visibility === 'error') {
    // Network error — fail open, let clone attempt proceed
    logger.debug('GitHub API unreachable, skipping visibility check');
    return { allowed: true, isPrivate: false };
  }

  // Repo appears private — check if we have a token
  const config = loadConfig();
  const token = config.githubToken;

  if (token === '') {
    throw new BranchNexusError(
      `Bu repo private görünüyor: ${owner}/${repo}`,
      ExitCode.GIT_ERROR,
      "BRANCHNEXUS_GH_TOKEN ortam değişkenini tanımlayın veya 'branchnexus init' ile token girin."
    );
  }

  // Re-check with authentication
  const authVisibility = await checkRepoVisibility(owner, repo, token);

  if (authVisibility === 'not_found') {
    throw new BranchNexusError(
      `Repo bulunamadı: ${owner}/${repo}`,
      ExitCode.GIT_ERROR,
      'Repo adını kontrol edin veya erişim izinlerinizi doğrulayın.'
    );
  }

  if (authVisibility === 'error') {
    logger.debug('GitHub API unreachable on auth check, proceeding with clone');
    return { allowed: true, isPrivate: true };
  }

  return { allowed: true, isPrivate: authVisibility === 'private' };
}
