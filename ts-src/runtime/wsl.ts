import { execa } from 'execa';
import { logger } from '../utils/logger.js';
import { BranchNexusError, ExitCode } from '../types/errors.js';
import { Platform, detectPlatform } from './platform.js';

export async function listDistributions(): Promise<string[]> {
  logger.debug('Listing WSL distributions using wsl.exe -l -q');

  if (detectPlatform() !== Platform.WINDOWS) {
    throw new BranchNexusError(
      'WSL is only available on Windows',
      ExitCode.UNSUPPORTED_PLATFORM,
      'Use native tmux on this platform.'
    );
  }

  try {
    const result = await execa('wsl.exe', ['-l', '-q'], {
      encoding: 'buffer',
    });

    const output = decodeWslOutput(result.stdout);
    const distros = output
      .split('\n')
      .map((line) => line.trim())
      .filter((line) => line.length > 0)
      .sort();

    if (distros.length === 0) {
      throw new BranchNexusError(
        'No WSL distributions were found.',
        ExitCode.RUNTIME_ERROR,
        'Install a distribution using `wsl --install` and retry.'
      );
    }

    logger.debug(`Discovered ${distros.length} WSL distributions`);
    return distros;
  } catch (error) {
    if (error instanceof BranchNexusError) {
      throw error;
    }

    const message = error instanceof Error ? error.message : String(error);
    throw new BranchNexusError(
      'Failed to list WSL distributions.',
      ExitCode.RUNTIME_ERROR,
      message
    );
  }
}

function decodeWslOutput(buffer: Buffer): string {
  if (buffer.includes(0x00)) {
    try {
      return buffer.toString('utf-16le').replace(/\ufeff/g, '');
    } catch {
      // Fall through
    }
  }
  return buffer.toString('utf-8');
}

export function validateDistribution(distribution: string, available: string[]): boolean {
  return available.includes(distribution);
}

export function buildWslCommand(distribution: string, command: string[]): string[] {
  if (distribution === '') {
    throw new BranchNexusError(
      'WSL distribution is required.',
      ExitCode.VALIDATION_ERROR,
      'Select a distribution before orchestration.'
    );
  }

  if (command.length === 0) {
    throw new BranchNexusError(
      'Runtime command is empty.',
      ExitCode.VALIDATION_ERROR,
      'Provide a command to execute in WSL.'
    );
  }

  return ['wsl.exe', '-d', distribution, '--', ...command];
}

export async function toWslPath(distribution: string, hostPath: string): Promise<string> {
  const normalized = hostPath.replace(/\\/g, '/');

  if (normalized.startsWith('/') && !normalized.startsWith('//')) {
    return normalized;
  }

  try {
    const cmd = buildWslCommand(distribution, ['wslpath', '-a', normalized]);
    const result = await execa(cmd[0], cmd.slice(1));
    const wslPath = result.stdout.trim();

    if (wslPath !== '') {
      return wslPath;
    }
  } catch {
    // Fall through to fallback
  }

  return fallbackWindowsToWslPath(normalized);
}

function fallbackWindowsToWslPath(hostPath: string): string {
  const match = hostPath.match(/^([A-Za-z]):[/\\](.*)$/);
  if (!match) {
    return hostPath;
  }

  const drive = match[1].toLowerCase();
  const rest = match[2].replace(/[/\\]/g, '/').replace(/\/+$/, '');

  if (rest === '') {
    return `/mnt/${drive}`;
  }

  return `/mnt/${drive}/${rest}`;
}

export function distributionUnreachableMessage(distribution: string): string {
  return (
    `Selected WSL distribution '${distribution}' is not reachable. ` +
    'Choose another distribution or start this one manually and retry.'
  );
}
