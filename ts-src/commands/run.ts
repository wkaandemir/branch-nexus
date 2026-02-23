import chalk from 'chalk';
import * as p from '@clack/prompts';
import { type Layout, type CleanupPolicy } from '../types/index.js';
import { BranchNexusError, ExitCode } from '../types/errors.js';
import { loadConfig, updateLastSession } from '../core/config.js';
import { orchestrate, type OrchestrationRequest } from '../core/orchestrator.js';
import { promptWslDistribution } from '../prompts/wsl.js';
import {
  showPanel,
  showBranchSelection,
  showPreview,
  showSuccess,
  showError,
  confirmStart,
} from '../prompts/panel.js';
import { promptCleanup } from '../prompts/cleanup.js';
import { Platform, detectPlatform, expandHomeDir, hasTmux } from '../runtime/platform.js';
import { listDistributions } from '../runtime/wsl.js';
import { logger, configureLogging } from '../utils/logger.js';
import { cloneRepository, checkRepositoryAccess } from '../git/clone.js';
import { existsSync, mkdirSync } from 'node:fs';
import { join, basename } from 'node:path';
import simpleGit from 'simple-git';
import { execa } from 'execa';
import { HookRunner } from '../hooks/runner.js';
import { parseRuntimeSnapshot, SessionCleanupHandler } from '../core/session.js';
import { WorktreeManager } from '../git/worktree.js';

export interface RunOptions {
  root?: string;
  layout?: Layout;
  panes?: number;
  cleanup?: CleanupPolicy;
  fresh?: boolean;
  terminalTemplate?: string;
  maxTerminals?: number;
  logLevel?: string;
  logFile?: string;
  session?: string;
  hooks?: boolean;
}

async function ensureTmuxInstalled(): Promise<void> {
  const tmuxInstalled = await hasTmux();

  if (tmuxInstalled) {
    return;
  }

  const platform = detectPlatform();

  console.log(chalk.yellow('\n📦 tmux bulunamadı, kuruluyor...\n'));

  if (platform === Platform.MACOS) {
    try {
      await execa('brew', ['install', 'tmux'], { timeout: 120000 });
      console.log(chalk.green('✅ tmux kuruldu!\n'));
      return;
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      throw new BranchNexusError(
        `tmux kurulumu başarısız: ${msg}`,
        ExitCode.TMUX_ERROR,
        'Manuel kurulum: brew install tmux'
      );
    }
  }

  // Linux/WSL
  let installCmd: string;

  try {
    await execa('bash', ['-lc', 'which apt-get']);
    installCmd = 'apt-get update && apt-get install -y tmux';
  } catch {
    try {
      await execa('bash', ['-lc', 'which dnf']);
      installCmd = 'dnf install -y tmux';
    } catch {
      try {
        await execa('bash', ['-lc', 'which pacman']);
        installCmd = 'pacman -S --noconfirm tmux';
      } catch {
        try {
          await execa('bash', ['-lc', 'which apk']);
          installCmd = 'apk add tmux';
        } catch {
          throw new BranchNexusError(
            'Paket yöneticisi bulunamadı.',
            ExitCode.TMUX_ERROR,
            "Lütfen tmux'u manuel kurun."
          );
        }
      }
    }
  }

  // Try sudo -n first
  try {
    console.log(chalk.dim(`Çalıştırılıyor: sudo ${installCmd}`));
    await execa('sudo', ['-n', 'bash', '-lc', installCmd], { timeout: 180000 });
    console.log(chalk.green('✅ tmux kuruldu!\n'));
    return;
  } catch {
    // Needs password
  }

  // Show command and wait
  console.log(chalk.cyan('Başka bir terminalde bu komutu çalıştırın:\n'));
  console.log(chalk.bold.white(`  sudo ${installCmd}\n`));
  console.log(chalk.dim('tmux kurulumu bekleniyor...'));

  for (let i = 0; i < 60; i++) {
    await new Promise((r) => setTimeout(r, 2000));
    const installed = await hasTmux();
    if (installed) {
      console.log(chalk.green('\n✅ tmux algılandı!\n'));
      return;
    }
    process.stdout.write('.');
  }

  console.log();
  throw new BranchNexusError(
    '2 dakika içinde tmux kurulumu algılanamadı.',
    ExitCode.TMUX_ERROR,
    'tmux kurduktan sonra tekrar deneyin.'
  );
}

export async function runCommand(options: RunOptions): Promise<void> {
  if (
    (options.logLevel !== undefined && options.logLevel !== '') ||
    (options.logFile !== undefined && options.logFile !== '')
  ) {
    configureLogging({
      level: options.logLevel as 'debug' | 'info' | 'warn' | 'error',
      logFile: options.logFile,
    });
  }

  logger.info('Starting BranchNexus');

  // Check tmux first
  await ensureTmuxInstalled();

  const config = loadConfig();
  const sessionName = options.session ?? 'branchnexus';

  // Session restore check (skip if --fresh)
  if (
    options.fresh !== true &&
    config.sessionRestoreEnabled &&
    Object.keys(config.lastSession).length > 0
  ) {
    const snapshot = parseRuntimeSnapshot(config.lastSession);

    if (snapshot !== null) {
      const restore = await p.confirm({
        message: 'Son oturumu geri yüklemek ister misiniz?',
        initialValue: true,
      });

      if (restore !== undefined && restore !== null && restore === true) {
        logger.info('Restoring previous session');

        const platform = detectPlatform();
        const isWindows = platform === Platform.WINDOWS;
        let distribution = '';

        if (isWindows && config.wslDistribution !== '') {
          distribution = config.wslDistribution;
        }

        // Rebuild from snapshot
        const assignments = snapshot.terminals.map((t, i) => ({
          pane: i,
          repoPath: t.repoPath,
          branch: t.branch,
        }));

        const worktreeBase = expandHomeDir(
          config.defaultRoot !== '' ? `${config.defaultRoot}/.bnx` : '~/.bnx'
        );

        const request: OrchestrationRequest = {
          distribution,
          availableDistributions: [],
          layout: snapshot.layout as 'horizontal' | 'vertical' | 'grid',
          cleanupPolicy: config.cleanupPolicy,
          assignments,
          worktreeBase,
          sessionName,
          tmuxAutoInstall: config.tmuxAutoInstall,
          colorTheme: config.colorTheme,
          paneNames: snapshot.terminals.map((t) => t.title),
          displayBranches: snapshot.terminals.map((t) => t.branch),
        };

        const s = p.spinner();
        s.start('Oturum geri yükleniyor...');

        try {
          const result = await orchestrate(request);
          s.stop(`${result.worktrees.length} worktree geri yüklendi`);

          showSuccess('tmux session hazır! Bağlanılıyor...');

          try {
            await execa('tmux', ['attach-session', '-t', sessionName], {
              stdio: 'inherit',
              timeout: 0,
            });
          } catch {
            console.log();
            console.log(chalk.dim('tmux session devam ediyor. Tekrar bağlanmak için:'));
            console.log(chalk.cyan(`  tmux attach -t ${sessionName}`));
            console.log();
          }
          return;
        } catch (error) {
          s.stop('Geri yükleme başarısız, yeni oturum başlatılıyor');
          logger.warn(
            `Session restore failed: ${error instanceof Error ? error.message : String(error)}`
          );
        }
      }
    }
  }

  // Show interactive panel
  const panelResult = await showPanel();

  if (!panelResult) {
    return;
  }

  const { token, repoUrl, repoUrls, layout, paneCount, cleanup } = panelResult;
  const allRepoUrls = repoUrls.length > 0 ? repoUrls : [repoUrl];

  const platform = detectPlatform();
  const isWindows = platform === Platform.WINDOWS;

  let distribution = '';
  let availableDistributions: string[] = [];

  if (isWindows) {
    try {
      availableDistributions = await listDistributions();
      if (
        config.wslDistribution !== '' &&
        availableDistributions.includes(config.wslDistribution)
      ) {
        distribution = config.wslDistribution;
      } else {
        distribution = await promptWslDistribution();
      }
    } catch (error) {
      showError(
        'WSL distributions alınamadı',
        error instanceof Error ? error.message : String(error)
      );
      return;
    }
  }

  // Prepare workspace
  const workspaceRoot = expandHomeDir(
    config.defaultRoot !== '' ? config.defaultRoot : '~/workspace'
  );
  if (!existsSync(workspaceRoot)) {
    mkdirSync(workspaceRoot, { recursive: true });
  }

  // Clone/fetch all repos
  const s = p.spinner();
  const localRepoPaths: string[] = [];

  for (const url of allRepoUrls) {
    let rName = basename(url.replace('.git', ''));
    if (rName.startsWith('git@')) {
      rName = rName.split(':').pop()?.replace('.git', '') ?? 'repo';
    }

    const localPath = join(workspaceRoot, rName);
    localRepoPaths.push(localPath);

    if (existsSync(localPath) && existsSync(join(localPath, '.git'))) {
      s.start(`Mevcut repo kullanılıyor: ${rName}...`);
      try {
        const git = simpleGit(localPath);
        await git.fetch('origin');
        s.stop('Mevcut repo: ' + localPath);
      } catch {
        s.stop('Fetch başarısız, local ile devam');
      }
    } else {
      // Check repository access before cloning
      try {
        const accessResult = await checkRepositoryAccess(url);
        logger.debug(`Access check for ${url}: isPrivate=${accessResult.isPrivate}`);
      } catch (error) {
        if (error instanceof BranchNexusError) {
          showError(error.message, error.hint);
          return;
        }
      }

      s.start(`Repo klonlanıyor: ${rName}...`);

      let cloneUrl = url;

      if (token !== null && token !== '' && url.startsWith('https://')) {
        cloneUrl = url.replace('https://', `https://${token}@`);
      }

      try {
        await cloneRepository(cloneUrl, localPath);
        s.stop('Klonlandı: ' + localPath);
      } catch (error) {
        s.stop('Klonlama başarısız');
        const message = error instanceof Error ? error.message : String(error);

        if (message.includes('403') || message.includes('Authentication failed')) {
          showError('Kimlik doğrulama başarısız', 'Private repo için GitHub token gerekli');
          return;
        }

        showError('Repo klonlanamadı', message);
        return;
      }
    }
  }

  const localRepoPath = localRepoPaths[0];

  // Merge branches from all repos (prefix with repo name if multi-repo)
  const allBranches: string[] = [];
  const branchRepoMap: Map<string, string> = new Map();

  try {
    const { listLocalBranches } = await import('../git/branch.js');

    for (let ri = 0; ri < localRepoPaths.length; ri++) {
      const rPath = localRepoPaths[ri];
      const branchResult = await listLocalBranches(rPath);

      if (branchResult.warning !== undefined && branchResult.warning !== '') {
        p.log.warn(branchResult.warning);
      }

      for (const branch of branchResult.branches) {
        const key = localRepoPaths.length > 1 ? `[${basename(rPath)}] ${branch}` : branch;
        allBranches.push(key);
        branchRepoMap.set(key, rPath);
      }
    }

    if (allBranches.length === 0) {
      showError("Repository'de branch bulunamadı.");
      return;
    }
  } catch (error) {
    showError('Branch listesi alınamadı', error instanceof Error ? error.message : String(error));
    return;
  }

  // Get branches via interactive per-pane selection table
  let branches: string[];
  let paneNames: string[] = [];
  let startupCommands: string[] = [];

  try {
    const selected = await showBranchSelection(allBranches, paneCount);
    if (selected === null) {
      p.cancel('İptal edildi.');
      return;
    }
    branches = selected.branches;
    paneNames = selected.paneNames;
    startupCommands = selected.startupCommands ?? [];
  } catch (error) {
    showError('Branch seçimi başarısız', error instanceof Error ? error.message : String(error));
    return;
  }

  // Show preview with selected branches
  showPreview({
    repoUrl,
    layout,
    branchCount: branches.length,
    branches,
    cleanup,
  });

  // Final confirmation
  const confirmed = await confirmStart();
  if (!confirmed) {
    p.cancel('İptal edildi.');
    return;
  }

  s.start("Worktree'ler oluşturuluyor...");

  // Each pane needs its own branch for git worktree (git doesn't allow same branch in 2 worktrees)
  // Create a unique local branch per pane: e.g. bnx-Alpha-0, bnx-Beta-1
  const resolvedBranches: string[] = [];
  const paneRepoPaths: string[] = [];

  for (let i = 0; i < branches.length; i++) {
    const branchKey = branches[i];
    // For multi-repo, strip repo prefix to get actual branch name
    const actualBranch = branchKey.replace(/^\[.*?\]\s*/, '');
    const paneRepoPath = branchRepoMap.get(branchKey) ?? localRepoPath;
    paneRepoPaths.push(paneRepoPath);

    const git = simpleGit(paneRepoPath);
    const safeName =
      paneNames[i].replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '') || `pane-${i}`;
    const localName = `bnx-${safeName}-${i}`;
    try {
      // Delete if exists from previous run, then recreate from source
      try {
        await git.branch(['-D', localName]);
      } catch {
        /* ignore */
      }
      await git.branch([localName, actualBranch]);
      logger.debug(`Created local branch ${localName} from ${actualBranch}`);
    } catch {
      logger.debug(`Branch ${localName} already exists, reusing`);
    }
    resolvedBranches.push(localName);
  }

  const assignments = resolvedBranches.map((branch, index) => ({
    pane: index,
    repoPath: paneRepoPaths[index],
    branch,
  }));

  const worktreeBase = expandHomeDir(
    config.defaultRoot !== '' ? `${config.defaultRoot}/.bnx` : '~/.bnx'
  );

  const request: OrchestrationRequest = {
    distribution,
    availableDistributions,
    layout,
    cleanupPolicy: cleanup,
    assignments,
    worktreeBase,
    sessionName,
    tmuxAutoInstall: config.tmuxAutoInstall,
    colorTheme: config.colorTheme,
    paneNames,
    displayBranches: branches,
    startupCommands: startupCommands.length > 0 ? startupCommands : undefined,
  };

  try {
    const result = await orchestrate(request);
    s.stop(`${result.worktrees.length} worktree oluşturuldu`);

    // Run command hooks (unless --no-hooks)
    const noHooks = options.hooks === false;
    const hookCommands = config.commandHooks['post-setup'] ?? [];

    if (!noHooks && hookCommands.length > 0) {
      const hookSpinner = p.spinner();
      hookSpinner.start("Hook'lar çalıştırılıyor...");

      const runner = new HookRunner({ timeoutSeconds: 60 });
      let totalFailures = 0;

      for (let i = 0; i < result.worktrees.length; i++) {
        const hookResult = await runner.run(i, hookCommands, distribution || undefined);
        if (hookResult.hasFailures) {
          totalFailures += hookResult.executions.filter((e) => !e.success).length;
        }
      }

      if (totalFailures > 0) {
        hookSpinner.stop(chalk.yellow(`Hook'lar tamamlandı (${totalFailures} hata)`));
      } else {
        hookSpinner.stop("Hook'lar tamamlandı");
      }
    }

    // Save session snapshot for restore
    const snapshotData: Record<string, unknown> = {
      layout,
      templateCount: branches.length,
      focusedTerminalId: '',
      terminals: branches.map((branch, i) => ({
        terminalId: `pane-${i}`,
        title: paneNames[i] ?? `Pane ${i}`,
        runtime: 'native' as const,
        repoPath: localRepoPath,
        branch,
      })),
    };
    updateLastSession(snapshotData);

    showSuccess('tmux session hazır! Bağlanılıyor...');

    // Attach to tmux session interactively
    try {
      await execa('tmux', ['attach-session', '-t', sessionName], {
        stdio: 'inherit',
        timeout: 0,
      });
    } catch {
      // User detached from tmux (Ctrl+B D) or session ended - this is normal
      console.log();
      console.log(chalk.dim('tmux session devam ediyor. Tekrar bağlanmak için:'));
      console.log(chalk.cyan(`  tmux attach -t ${sessionName}`));
      console.log();
    }

    // Post-detach cleanup handler
    if (cleanup === 'session' && result.worktrees.length > 0) {
      const worktreeManager = new WorktreeManager(worktreeBase, cleanup);
      // Populate managed worktrees from result
      for (const wt of result.worktrees) {
        await worktreeManager.addWorktree(
          { pane: wt.pane, repoPath: wt.repoPath, branch: wt.branch },
          distribution || undefined
        );
      }

      const cleanupHandler = new SessionCleanupHandler(
        worktreeManager,
        promptCleanup,
        distribution || undefined
      );

      const cleanupResult = await cleanupHandler.handleExit();

      if (cleanupResult.removed.length > 0) {
        console.log(chalk.green(`✓ ${cleanupResult.removed.length} worktree temizlendi.`));
      }
      if (cleanupResult.preservedDirty.length > 0) {
        console.log(
          chalk.yellow(`⚠ ${cleanupResult.preservedDirty.length} dirty worktree korundu.`)
        );
      }
    }
  } catch (error) {
    s.stop('Session oluşturulamadı');

    if (error instanceof BranchNexusError) {
      showError(error.message, error.hint);
    } else {
      showError('Beklenmeyen hata', error instanceof Error ? error.message : String(error));
    }
  }
}
