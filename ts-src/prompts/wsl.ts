import inquirer from 'inquirer';
import { listDistributions } from '../runtime/wsl.js';
import { loadConfig, setWslDistribution } from '../core/config.js';
import { detectPlatform, Platform } from '../runtime/platform.js';
import { BranchNexusError, ExitCode } from '../types/errors.js';
import { logger } from '../utils/logger.js';

export async function promptWslDistribution(): Promise<string> {
  const platform = detectPlatform();

  if (platform !== Platform.WINDOWS) {
    throw new BranchNexusError(
      'WSL is only available on Windows',
      ExitCode.UNSUPPORTED_PLATFORM,
      'Use native tmux on this platform.'
    );
  }

  const config = loadConfig();
  const cachedDistribution = config.wslDistribution;

  logger.debug('Prompting for WSL distribution');

  const distributions = await listDistributions();

  if (cachedDistribution && distributions.includes(cachedDistribution)) {
    const { useCached } = await inquirer.prompt<{
      useCached: boolean;
    }>([
      {
        type: 'confirm',
        name: 'useCached',
        message: `Use cached distribution "${cachedDistribution}"?`,
        default: true,
      },
    ]);

    if (useCached) {
      logger.debug(`Using cached distribution: ${cachedDistribution}`);
      return cachedDistribution;
    }
  }

  const { distribution } = await inquirer.prompt<{
    distribution: string;
  }>([
    {
      type: 'list',
      name: 'distribution',
      message: 'Select WSL distribution:',
      choices: distributions.map((d) => ({ name: d, value: d })),
    },
  ]);

  setWslDistribution(distribution);
  logger.debug(`Selected distribution: ${distribution}`);

  return distribution;
}
