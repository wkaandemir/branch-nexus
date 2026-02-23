import inquirer from 'inquirer';
import chalk from 'chalk';
import { type AppConfig, type Layout, type CleanupPolicy, DEFAULT_CONFIG } from '../types/index.js';
import { loadConfig, saveConfig, setWslDistribution, setGithubToken } from '../core/config.js';
import { detectPlatform, Platform, hasTmux } from '../runtime/platform.js';
import { listDistributions } from '../runtime/wsl.js';
import { logger } from '../utils/logger.js';
import { execa } from 'execa';

async function checkDependencies(): Promise<{ tmux: boolean; git: boolean }> {
  const tmuxInstalled = await hasTmux();
  let gitInstalled = false;

  try {
    await execa('git', ['--version']);
    gitInstalled = true;
  } catch {
    gitInstalled = false;
  }

  return { tmux: tmuxInstalled, git: gitInstalled };
}

async function installTmux(): Promise<boolean> {
  const platform = detectPlatform();

  console.log(chalk.dim('\n📦 Installing tmux...\n'));

  let cmd: string;

  if (platform === Platform.MACOS) {
    cmd = 'brew install tmux';
  } else {
    // Linux/WSL - try apt first, then other package managers
    try {
      await execa('bash', ['-lc', 'which apt-get']);
      cmd = 'sudo apt-get update && sudo apt-get install -y tmux';
    } catch {
      try {
        await execa('bash', ['-lc', 'which dnf']);
        cmd = 'sudo dnf install -y tmux';
      } catch {
        try {
          await execa('bash', ['-lc', 'which pacman']);
          cmd = 'sudo pacman -S --noconfirm tmux';
        } catch {
          console.log(chalk.red('Could not detect package manager. Please install tmux manually.'));
          return false;
        }
      }
    }
  }

  console.log(chalk.dim(`Running: ${cmd}`));

  try {
    if (cmd.includes('sudo')) {
      // For sudo commands, we need interactive terminal
      console.log(chalk.yellow('\n⚠️  sudo password required. Running in your shell...\n'));
      console.log(chalk.cyan(`Please run: ${cmd}\n`));

      const { proceed } = await inquirer.prompt<{
        proceed: boolean;
      }>([
        {
          type: 'confirm',
          name: 'proceed',
          message: 'Press Enter after you have run the command above',
          default: true,
        },
      ]);

      return proceed;
    } else {
      await execa('bash', ['-lc', cmd]);
      console.log(chalk.green('✅ tmux installed successfully!\n'));
      return true;
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.log(chalk.red(`Failed to install tmux: ${message}`));
    console.log(chalk.dim(`Please run manually: ${cmd}`));
    return false;
  }
}

export async function promptSetup(): Promise<Partial<AppConfig>> {
  console.log(chalk.cyan.bold('\n🚀 BranchNexus Setup Wizard\n'));

  const platform = detectPlatform();
  const currentConfig = loadConfig();

  // Check and install dependencies
  const deps = await checkDependencies();

  if (!deps.git) {
    console.log(chalk.red('❌ Git is not installed. Please install Git first.'));
    console.log(chalk.dim('https://git-scm.com/downloads\n'));
    process.exit(1);
  }

  if (!deps.tmux) {
    console.log(chalk.yellow('⚠️  tmux is not installed.\n'));

    const { installTmuxNow } = await inquirer.prompt<{
      installTmuxNow: boolean;
    }>([
      {
        type: 'confirm',
        name: 'installTmuxNow',
        message: 'Install tmux automatically?',
        default: true,
      },
    ]);

    if (installTmuxNow) {
      const installed = await installTmux();
      if (!installed) {
        console.log(chalk.red('\n❌ tmux installation failed or was skipped.'));
        console.log(chalk.dim('Please install tmux manually and run branchnexus init again.\n'));
        process.exit(1);
      }
    } else {
      console.log(chalk.dim('\nPlease install tmux manually:'));
      if (platform === Platform.MACOS) {
        console.log(chalk.cyan('  brew install tmux'));
      } else {
        console.log(chalk.cyan('  sudo apt-get install tmux'));
      }
      console.log();
      process.exit(1);
    }
  } else {
    console.log(chalk.green('✅ tmux is installed\n'));
  }

  const answers = await inquirer.prompt<{
    defaultRoot: string;
    layout: Layout;
    panes: number;
    cleanup: CleanupPolicy;
    wslDistribution?: string;
    githubToken?: string;
    saveConfig: boolean;
  }>([
    {
      type: 'input',
      name: 'defaultRoot',
      message: 'Default working directory:',
      default: currentConfig.defaultRoot || '~/workspace',
    },
    {
      type: 'list',
      name: 'layout',
      message: 'Default layout:',
      choices: [
        { name: 'grid (2x2)', value: 'grid' },
        { name: 'horizontal (side by side)', value: 'horizontal' },
        { name: 'vertical (stacked)', value: 'vertical' },
      ],
      default: currentConfig.defaultLayout,
    },
    {
      type: 'number',
      name: 'panes',
      message: 'Default number of panes (2-6):',
      default: currentConfig.defaultPanes,
      validate: (value: number): string | boolean => {
        if (value < 2 || value > 6) {
          return 'Panes must be between 2 and 6';
        }
        return true;
      },
    },
    {
      type: 'list',
      name: 'cleanup',
      message: 'Cleanup policy:',
      choices: [
        { name: 'session (delete worktrees on exit)', value: 'session' },
        { name: 'persistent (keep worktrees)', value: 'persistent' },
      ],
      default: currentConfig.cleanupPolicy,
    },
    ...(platform === Platform.WINDOWS
      ? [
          {
            type: 'list' as const,
            name: 'wslDistribution',
            message: 'WSL distribution:',
            choices: async (): Promise<Array<{ name: string; value: string }>> => {
              try {
                const distros = await listDistributions();
                return distros.map((d) => ({ name: d, value: d }));
              } catch {
                return [{ name: 'No WSL distributions found', value: '' }];
              }
            },
            default: currentConfig.wslDistribution,
          },
        ]
      : []),
    {
      type: 'confirm',
      name: 'githubTokenPrompt',
      message: 'Configure GitHub token for private repos?',
      default: false,
    },
    {
      type: 'password',
      name: 'githubToken',
      message: 'GitHub token (optional):',
      mask: '*',
      when: (answers: { githubTokenPrompt: boolean }) => answers.githubTokenPrompt,
    },
    {
      type: 'confirm',
      name: 'saveConfig',
      message: 'Save configuration?',
      default: true,
    },
  ]);

  return {
    defaultRoot: answers.defaultRoot,
    defaultLayout: answers.layout,
    defaultPanes: answers.panes,
    cleanupPolicy: answers.cleanup,
    wslDistribution: answers.wslDistribution,
    githubToken: answers.githubToken,
  };
}

export async function initCommand(): Promise<void> {
  logger.info('Starting init wizard');

  console.log(chalk.bold('\n📋 BranchNexus Setup\n'));

  console.log('This wizard will help you configure BranchNexus for your workflow.\n');

  const partialConfig = await promptSetup();

  const config = loadConfig();
  const merged: AppConfig = {
    ...DEFAULT_CONFIG,
    ...config,
    ...partialConfig,
  };

  if (partialConfig.wslDistribution !== undefined && partialConfig.wslDistribution !== '') {
    setWslDistribution(partialConfig.wslDistribution);
  }

  if (partialConfig.githubToken !== undefined && partialConfig.githubToken !== '') {
    setGithubToken(partialConfig.githubToken);
  }

  saveConfig(merged);

  console.log(chalk.green('\n✅ Configuration saved!\n'));
  console.log(chalk.dim(`Config location: ${process.env.HOME}/.config/branchnexus/config.json`));
  console.log(chalk.dim('\nRun `branchnexus` to start a session.\n'));
}
