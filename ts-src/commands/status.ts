import chalk from 'chalk';
import { loadConfig, getConfigPath } from '../core/config.js';
import { loadPresets } from '../core/presets.js';
import { listSessions } from '../tmux/session.js';
import { existsSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { expandHomeDir } from '../runtime/platform.js';

export async function statusCommand(): Promise<void> {
  const config = loadConfig();
  const distribution = config.wslDistribution || undefined;

  console.log(chalk.bold('\n📊 BranchNexus Durum\n'));

  // Config path
  console.log(chalk.dim('Config: ') + getConfigPath());
  console.log();

  // Active tmux sessions
  console.log(chalk.bold('tmux Session\'lar:'));
  const sessions = await listSessions(distribution);
  const bnSessions = sessions.filter((s) => s.startsWith('branchnexus'));

  if (bnSessions.length === 0) {
    console.log(chalk.dim('  Aktif session yok'));
  } else {
    for (const s of bnSessions) {
      console.log(chalk.green(`  ● ${s}`));
    }
  }
  console.log();

  // Managed worktrees
  console.log(chalk.bold('Worktree\'ler:'));
  const root = config.defaultRoot !== '' ? config.defaultRoot : expandHomeDir('~');
  const bnxDir = join(root, '.bnx');

  if (existsSync(bnxDir)) {
    try {
      const repoDirs = readdirSync(bnxDir, { withFileTypes: true }).filter((d) => d.isDirectory());
      let wtCount = 0;

      for (const repoDir of repoDirs) {
        const repoPath = join(bnxDir, repoDir.name);
        const paneDirs = readdirSync(repoPath, { withFileTypes: true }).filter((d) =>
          d.isDirectory()
        );

        for (const paneDir of paneDirs) {
          const gitFile = join(repoPath, paneDir.name, '.git');
          if (existsSync(gitFile)) {
            wtCount++;
            console.log(chalk.cyan(`  ${repoDir.name}/${paneDir.name}`));
          }
        }
      }

      if (wtCount === 0) {
        console.log(chalk.dim('  Aktif worktree yok'));
      }
    } catch {
      console.log(chalk.dim('  Worktree dizini okunamadı'));
    }
  } else {
    console.log(chalk.dim('  Aktif worktree yok'));
  }
  console.log();

  // Presets
  console.log(chalk.bold('Preset\'ler:'));
  const presets = loadPresets();
  const presetEntries = Object.entries(presets);

  if (presetEntries.length === 0) {
    console.log(chalk.dim('  Kayıtlı preset yok'));
  } else {
    for (const [name, preset] of presetEntries) {
      console.log(
        chalk.cyan(`  ${name}`) +
          chalk.dim(` — ${preset.layout}, ${preset.panes} pane, ${preset.cleanup}`)
      );
    }
  }
  console.log();

  // Command hooks
  console.log(chalk.bold('Hook\'lar:'));
  const hooks = config.commandHooks;
  const hookEntries = Object.entries(hooks);

  if (hookEntries.length === 0) {
    console.log(chalk.dim('  Tanımlı hook yok'));
  } else {
    for (const [event, commands] of hookEntries) {
      console.log(chalk.cyan(`  ${event}:`));
      for (const cmd of commands) {
        console.log(chalk.dim(`    $ ${cmd}`));
      }
    }
  }
  console.log();

  // GitHub token
  console.log(chalk.bold('GitHub Token:'));
  const hasToken = config.githubToken !== '';
  const envToken = process.env.BRANCHNEXUS_GH_TOKEN;
  const tokenSource = envToken !== undefined && envToken !== '' ? ' (env)' : ' (config)';
  console.log(
    hasToken
      ? chalk.green(`  ● Tanımlı${tokenSource}`)
      : chalk.dim('  ○ Tanımlı değil')
  );
  console.log();

  // General settings
  console.log(chalk.bold('Ayarlar:'));
  console.log(chalk.dim('  Layout:    ') + config.defaultLayout);
  console.log(chalk.dim('  Panes:     ') + config.defaultPanes);
  console.log(chalk.dim('  Cleanup:   ') + config.cleanupPolicy);
  console.log(chalk.dim('  Theme:     ') + config.colorTheme);
  console.log(chalk.dim('  Restore:   ') + (config.sessionRestoreEnabled ? 'Açık' : 'Kapalı'));

  if (config.wslDistribution !== '') {
    console.log(chalk.dim('  WSL:       ') + config.wslDistribution);
  }
  console.log();
}
