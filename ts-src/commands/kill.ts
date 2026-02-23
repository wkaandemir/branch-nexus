import chalk from 'chalk';
import * as p from '@clack/prompts';
import { existsSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { listSessions, killSession } from '../tmux/session.js';
import { loadConfig } from '../core/config.js';
import { expandHomeDir } from '../runtime/platform.js';
import { runCommand } from '../runtime/shell.js';
import { logger } from '../utils/logger.js';

const SESSION_PREFIX = 'branchnexus';

async function cleanupWorktreeDir(basePath: string, distribution?: string): Promise<number> {
  if (!existsSync(basePath)) {
    return 0;
  }

  let removed = 0;
  const repoDirs = readdirSync(basePath, { withFileTypes: true }).filter((d) => d.isDirectory());

  for (const repoDir of repoDirs) {
    const repoWorktreeDir = join(basePath, repoDir.name);
    const paneDirs = readdirSync(repoWorktreeDir, { withFileTypes: true }).filter((d) => d.isDirectory());

    for (const paneDir of paneDirs) {
      const panePath = join(repoWorktreeDir, paneDir.name);
      const gitFile = join(panePath, '.git');

      // Only remove if it's actually a worktree (has .git file, not directory)
      if (!existsSync(gitFile)) {
        continue;
      }

      // Find the parent repo to run git worktree remove against it
      const cmd = ['git', '-C', panePath, 'worktree', 'list', '--porcelain'];
      try {
        const result = distribution ? await runCommand(['wsl', '-d', distribution, ...cmd]) : await runCommand(cmd);

        // Extract the main worktree path (first "worktree" entry)
        let mainRepoPath = '';
        for (const line of result.stdout.split('\n')) {
          if (line.startsWith('worktree ')) {
            mainRepoPath = line.slice(9).trim();
            break;
          }
        }

        if (mainRepoPath !== '') {
          const removeCmd = ['git', '-C', mainRepoPath, 'worktree', 'remove', '--force', panePath];
          const removeResult = distribution
            ? await runCommand(['wsl', '-d', distribution, ...removeCmd])
            : await runCommand(removeCmd);

          if (removeResult.exitCode === 0) {
            removed++;
            logger.debug(`Removed worktree: ${panePath}`);
          } else {
            logger.warn(`Failed to remove worktree ${panePath}: ${removeResult.stderr}`);
          }
        }
      } catch (error) {
        logger.warn(`Error cleaning worktree ${panePath}: ${error instanceof Error ? error.message : String(error)}`);
      }
    }

    // Remove the repo directory if now empty
    try {
      const remaining = readdirSync(repoWorktreeDir);
      if (remaining.length === 0) {
        const { rmSync } = await import('node:fs');
        rmSync(repoWorktreeDir, { recursive: true });
        logger.debug(`Removed empty worktree dir: ${repoWorktreeDir}`);
      }
    } catch {
      // ignore
    }
  }

  // Remove basePath if now empty
  try {
    const remaining = readdirSync(basePath);
    if (remaining.length === 0) {
      const { rmSync } = await import('node:fs');
      rmSync(basePath, { recursive: true });
      logger.debug(`Removed empty worktree base: ${basePath}`);
    }
  } catch {
    // ignore
  }

  return removed;
}

async function cleanupWorktrees(distribution?: string): Promise<number> {
  const config = loadConfig();
  const root = config.defaultRoot !== '' ? config.defaultRoot : expandHomeDir('~');
  const workspaceRoot = config.defaultRoot !== '' ? config.defaultRoot : expandHomeDir('~/workspace');

  // Clean both new (.bnx) and legacy (branchnexus-worktrees) paths
  const paths = [
    join(root, '.bnx'),
    join(workspaceRoot, '.bnx'),
    join(workspaceRoot, 'branchnexus-worktrees'),
    join(root, 'branchnexus-worktrees'),
  ];

  let total = 0;
  const seen = new Set<string>();
  for (const p of paths) {
    if (seen.has(p)) continue;
    seen.add(p);
    total += await cleanupWorktreeDir(p, distribution);
  }
  return total;
}

export async function killCommand(sessionName?: string): Promise<void> {
  const config = loadConfig();
  const distribution = config.wslDistribution || undefined;

  const allSessions = await listSessions(distribution);
  const bnSessions = allSessions.filter((s) => s.startsWith(SESSION_PREFIX));

  if (bnSessions.length === 0) {
    console.log(chalk.yellow('\nAktif BranchNexus session bulunamadı.\n'));

    // Still try to clean up orphaned worktrees
    const removed = await cleanupWorktrees(distribution);
    if (removed > 0) {
      console.log(chalk.green(`${removed} orphan worktree temizlendi.\n`));
    }
    return;
  }

  let target: string;

  if (sessionName !== undefined && sessionName !== '') {
    if (!bnSessions.includes(sessionName)) {
      console.error(chalk.red(`\nSession "${sessionName}" bulunamadı.\n`));
      console.log(chalk.dim('Aktif session\'lar:'));
      for (const s of bnSessions) {
        console.log(chalk.dim(`  - ${s}`));
      }
      console.log();
      process.exit(1);
    }
    target = sessionName;
  } else if (bnSessions.length === 1) {
    target = bnSessions[0];
  } else {
    const selected = await p.select({
      message: 'Hangi session kapatılsın?',
      options: bnSessions.map((s) => ({ value: s, label: s })),
    });

    if (p.isCancel(selected)) {
      p.cancel('İptal edildi.');
      return;
    }

    target = selected;
  }

  // 1) Kill tmux session
  await killSession(target, distribution);
  console.log(chalk.green(`\n✓ Session "${target}" kapatıldı.`));

  // 2) Cleanup worktrees
  const removed = await cleanupWorktrees(distribution);
  if (removed > 0) {
    console.log(chalk.green(`✓ ${removed} worktree temizlendi.\n`));
  } else {
    console.log();
  }
}
