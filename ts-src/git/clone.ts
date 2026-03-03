import simpleGit, { type SimpleGit } from 'simple-git';
import { execa } from 'execa';
import { logger } from '../utils/logger.js';
import { BranchNexusError, ExitCode } from '../types/errors.js';
import { posixPath } from '../utils/validators.js';
import { parseGitHubUrl, checkRepoVisibility } from '../github/api.js';
import { loadConfig } from '../core/config.js';

export async function materializeRemoteBranch(
  repoPath: string,
  remoteBranch: string
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
  } catch (error) {
    logger.debug(
      `Branch check failed, continuing with creation: ${error instanceof Error ? error.message : String(error)}`
    );
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

export async function cloneRepository(
  url: string,
  targetPath: string,
  token?: string
): Promise<void> {
  logger.debug(`Cloning repository to ${targetPath}`);

  if (token !== undefined && token !== '' && url.startsWith('https://')) {
    // Use git credential environment variables to pass the token securely.
    // This avoids embedding the token in the URL where it could leak into
    // git logs, process lists, or shell history.
    const urlObj = new URL(url);
    const credentialHelper = `!f() { echo "username=x-access-token"; echo "password=${token}"; }; f`;

    try {
      await execa(
        'git',
        ['-c', `credential.${urlObj.origin}.helper=${credentialHelper}`, 'clone', url, targetPath],
        { timeout: 120000, env: { ...process.env, GIT_TERMINAL_PROMPT: '0' } }
      );
      logger.debug(`Cloned repository to ${targetPath}`);
      return;
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      throw new BranchNexusError(`Failed to clone repository: ${url}`, ExitCode.GIT_ERROR, message);
    }
  }

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
