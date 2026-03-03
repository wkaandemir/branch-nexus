#!/usr/bin/env node
import { Command } from 'commander';
import chalk from 'chalk';
import {
  initCommand,
  runCommand,
  configCommand,
  killCommand,
  presetCommand,
  statusCommand,
  attachCommand,
} from './commands/index.js';
import { type RunOptions } from './commands/run.js';
import { userFacingError, isBranchNexusError, ExitCode } from './types/errors.js';
import { configureLogging, defaultLogPath, logger } from './utils/logger.js';

const program = new Command();

program
  .name('branchnexus')
  .description('Multi-branch workspace orchestrator for tmux')
  .version('1.0.0');

program
  .command('init')
  .description('First-time setup wizard')
  .action(async () => {
    await initCommand();
  });

program
  .command('config')
  .description('Manage configuration (show | set | reset | export | import)')
  .argument('[action]', 'show | set | reset | export | import')
  .argument('[key]', 'Config key or file path')
  .argument('[value]', 'Config value')
  .action((action: string | undefined, key: string | undefined, value: string | undefined) => {
    configCommand(action, key, value);
  });

program
  .command('kill')
  .description('Kill an active BranchNexus tmux session')
  .argument('[session]', 'Session name to kill')
  .action(async (session?: string) => {
    await killCommand(session);
  });

program
  .command('preset')
  .description('Manage presets (list | save | load | delete | rename)')
  .argument('[action]', 'list | save | load | delete | rename')
  .argument('[name]', 'Preset name')
  .argument('[extra]', 'JSON data or new name for rename')
  .action((action?: string, name?: string, extra?: string) => {
    presetCommand(action, name, extra);
  });

program
  .command('status')
  .description('Show BranchNexus status overview')
  .action(async () => {
    await statusCommand();
  });

program
  .command('attach')
  .description('Attach to a detached BranchNexus tmux session')
  .argument('[session]', 'Session name to attach')
  .action(async (session?: string) => {
    await attachCommand(session);
  });

program
  .option('--root <path>', 'Working directory')
  .option('--layout <layout>', 'horizontal | vertical | grid')
  .option('--panes <number>', 'Number of panes (2-6)', parseInt)
  .option('--cleanup <policy>', 'session | persistent')
  .option('--fresh', 'Reset workspace and start fresh')
  .option('--terminal-template <template>', '2 | 4 | 6 | 8 | 12 | 16 | custom')
  .option('--max-terminals <count>', 'Maximum terminals', parseInt)
  .option('--log-level <level>', 'DEBUG | INFO | WARN | ERROR')
  .option('--log-file <path>', 'Log file path')
  .option('--session <name>', 'Custom session name')
  .option('--no-hooks', 'Skip command hooks');

program.action(async (options: Record<string, unknown>) => {
  await runCommand(options as RunOptions);
});

async function main(): Promise<void> {
  const logPath = defaultLogPath();
  configureLogging({ logFile: logPath });

  try {
    await program.parseAsync(process.argv);
  } catch (error) {
    if (isBranchNexusError(error)) {
      logger.error(`BranchNexusError: ${error.message}`);
      console.error(chalk.red(userFacingError(error.message, error.hint)));
      process.exit(error.code);
    }

    const message = error instanceof Error ? error.message : String(error);
    logger.error(`Unexpected error: ${message}`);
    console.error(
      chalk.red(userFacingError('Unexpected runtime failure', `Check logs: ${logPath}`))
    );
    process.exit(ExitCode.RUNTIME_ERROR);
  }
}

main().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : String(error);
  console.error(chalk.red(`Fatal error: ${message}`));
  process.exit(ExitCode.RUNTIME_ERROR);
});
