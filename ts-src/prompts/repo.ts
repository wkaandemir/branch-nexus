import * as p from '@clack/prompts';
import chalk from 'chalk';
import { listLocalBranches } from '../git/branch.js';
import { logger } from '../utils/logger.js';
import { setGithubToken, loadConfig } from '../core/config.js';

export interface RepoSelection {
  url: string;
  needsAuth: boolean;
}

export async function promptGitHubToken(): Promise<string | null> {
  const config = loadConfig();

  if (config.githubToken !== undefined && config.githubToken !== '') {
    logger.debug('GitHub token already configured');
    return config.githubToken;
  }

  console.log(chalk.cyan('\n🔑 GitHub token (optional, for private repos).\n'));
  console.log(chalk.dim('Create a token at: https://github.com/settings/tokens'));
  console.log(chalk.dim('Required scopes: repo\n'));

  const hasToken = await p.confirm({
    message: 'Private repolar için GitHub token ister misiniz?',
    initialValue: false,
  });

  if (hasToken !== true) {
    return null;
  }

  const token = await p.password({
    message: 'GitHub personal access token:',
  });

  if (typeof token !== 'string' || token === '') {
    return null;
  }

  const trimmedToken = token.trim();
  setGithubToken(trimmedToken);
  console.log(chalk.green('\n✅ GitHub token kaydedildi!\n'));

  return trimmedToken;
}

export async function promptRepo(): Promise<RepoSelection> {
  logger.debug('Prompting for repository URL');

  const repoUrl = await p.text({
    message: 'Repository URL (HTTPS veya SSH):',
    placeholder: 'https://github.com/user/repo.git',
    validate: (value) => {
      if (value === undefined) return 'Repository URL gerekli';
      const trimmed = value.trim();
      if (trimmed === '') {
        return 'Repository URL gerekli';
      }
      if (
        !trimmed.includes('github.com') &&
        !trimmed.includes('gitlab.com') &&
        !trimmed.includes('bitbucket.org')
      ) {
        return 'Geçerli bir Git repository URL girin';
      }
      return undefined;
    },
  });

  if (p.isCancel(repoUrl)) {
    throw new Error('İptal edildi');
  }

  const url = repoUrl.trim();
  const needsAuth = url.startsWith('https://') && !url.includes('@');

  return {
    url,
    needsAuth,
  };
}

export async function promptBranches(repoPath: string): Promise<string[]> {
  logger.debug(`Prompting for branches in ${repoPath}`);

  const { branches, warning } = await listLocalBranches(repoPath);

  if (warning !== undefined && warning !== '') {
    p.log.warn(warning);
  }

  if (branches.length === 0) {
    throw new Error("Repository'de branch bulunamadı.");
  }

  const selectedBranches = await p.multiselect({
    message: 'Branch seçin (SPACE ile işaretleyin, Enter ile onaylayın):',
    options: branches.map((b) => ({
      value: b,
      label: b.startsWith('origin/') ? `${b} (remote)` : b,
    })),
    required: true,
  });

  if (p.isCancel(selectedBranches)) {
    throw new Error('İptal edildi');
  }

  logger.debug(`Selected ${selectedBranches.length} branches`);
  return selectedBranches;
}
