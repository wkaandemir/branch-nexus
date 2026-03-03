import chalk from 'chalk';
import { readFileSync } from 'node:fs';
import {
  loadConfig,
  saveConfig,
  setConfigValue,
  resetConfig,
  getConfigPath,
} from '../core/config.js';
import { AppConfigSchema } from '../types/index.js';

export function configCommand(action?: string, key?: string, value?: string): void {
  const config = loadConfig();

  switch (action) {
    case 'show':
      console.log(chalk.bold('\n📋 BranchNexus Configuration\n'));
      console.log(chalk.dim(`Location: ${getConfigPath()}\n`));
      console.log(JSON.stringify(config, null, 2));
      console.log();
      break;

    case 'set':
      if (key === undefined || key === '' || value === undefined) {
        console.error(chalk.red('Usage: branch-nexus config set <key> <value>'));
        console.log(chalk.dim('\nAvailable keys:'));
        console.log('  defaultRoot, defaultLayout, defaultPanes, cleanupPolicy');
        console.log('  wslDistribution, tmuxAutoInstall, sessionRestoreEnabled');
        console.log('  githubToken, terminalMaxCount, colorTheme');
        process.exit(1);
      }
      try {
        setConfigValue(key, value);
        console.log(chalk.green(`\n✅ Set ${key} = ${value}\n`));
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        console.error(chalk.red(`\n❌ ${message}\n`));
        process.exit(1);
      }
      break;

    case 'reset':
      resetConfig();
      console.log(chalk.green('\n✅ Configuration reset to defaults\n'));
      break;

    case 'export': {
      // Export config as JSON to stdout
      const exportData = JSON.stringify(config, null, 2);
      console.log(exportData);
      break;
    }

    case 'import': {
      if (key === undefined || key === '') {
        console.error(chalk.red('Usage: branch-nexus config import <file-path>'));
        process.exit(1);
      }

      try {
        const fileContent = readFileSync(key, 'utf-8');
        const parsed = JSON.parse(fileContent) as unknown;
        const validated = AppConfigSchema.parse(parsed);
        saveConfig(validated);
        console.log(chalk.green(`\n✅ Configuration imported from ${key}\n`));
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        console.error(chalk.red(`\n❌ Import başarısız: ${message}\n`));
        process.exit(1);
      }
      break;
    }

    default:
      console.log(chalk.bold('\n📋 Configuration Commands\n'));
      console.log('  branch-nexus config show                Show current configuration');
      console.log('  branch-nexus config set <key> <value>    Set a configuration value');
      console.log('  branch-nexus config reset                Reset to defaults');
      console.log('  branch-nexus config export               Export config as JSON');
      console.log('  branch-nexus config import <file>        Import config from JSON file');
      console.log();
  }
}
