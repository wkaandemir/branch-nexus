import { runCommand, runCommandViaWSL } from '../runtime/shell.js';
import { buildWslCommand } from '../runtime/wsl.js';
import { logger } from '../utils/logger.js';
import { BranchNexusError, ExitCode } from '../types/errors.js';
import { Platform, detectPlatform } from '../runtime/platform.js';

const DEFAULT_SESSION_NAME = 'branchnexus';

export async function startSession(
  sessionName: string,
  commands: string[][],
  distribution?: string
): Promise<void> {
  const isWindows = detectPlatform() === Platform.WINDOWS;

  logger.debug(`Starting tmux session: ${sessionName}`);

  for (const command of commands) {
    const wrappedCommand =
      isWindows && distribution !== undefined && distribution !== ''
        ? buildWslCommand(distribution, command)
        : command;

    logger.debug(`Executing tmux command: ${wrappedCommand.join(' ')}`);

    const result =
      isWindows && distribution !== undefined && distribution !== ''
        ? await runCommandViaWSL(distribution, command)
        : await runCommand(wrappedCommand);

    if (result.exitCode !== 0) {
      const stderr = result.stderr.trim();

      // Check for duplicate session
      const isNewSession = command[0] === 'tmux' && command[1] === 'new-session';
      if (isNewSession && stderr.toLowerCase().includes('duplicate session')) {
        logger.warn(`tmux session already exists: ${sessionName}, replacing`);

        // Kill existing session and retry
        await killSession(sessionName, distribution);

        const retryResult =
          isWindows && distribution !== undefined && distribution !== ''
            ? await runCommandViaWSL(distribution, command)
            : await runCommand(wrappedCommand);

        if (retryResult.exitCode !== 0) {
          throw new BranchNexusError(
            'Failed to initialize tmux session.',
            ExitCode.TMUX_ERROR,
            retryResult.stderr || 'tmux command failed'
          );
        }

        continue;
      }

      throw new BranchNexusError(
        'Failed to initialize tmux session.',
        ExitCode.TMUX_ERROR,
        stderr || 'tmux command failed'
      );
    }
  }

  logger.info(`tmux session ready: ${sessionName}`);
}

export async function killSession(sessionName: string, distribution?: string): Promise<void> {
  const isWindows = detectPlatform() === Platform.WINDOWS;
  const command = ['tmux', 'kill-session', '-t', sessionName];

  logger.debug(`Killing tmux session: ${sessionName}`);

  const result =
    isWindows && distribution !== undefined && distribution !== ''
      ? await runCommandViaWSL(distribution, command)
      : await runCommand(command);

  if (result.exitCode !== 0) {
    logger.warn(`Failed to kill session: ${result.stderr}`);
  }
}

export async function sessionExists(sessionName: string, distribution?: string): Promise<boolean> {
  const isWindows = detectPlatform() === Platform.WINDOWS;
  const command = ['tmux', 'has-session', '-t', sessionName];

  const result =
    isWindows && distribution !== undefined && distribution !== ''
      ? await runCommandViaWSL(distribution, command)
      : await runCommand(command);

  return result.exitCode === 0;
}

export async function attachSession(sessionName: string, distribution?: string): Promise<void> {
  const isWindows = detectPlatform() === Platform.WINDOWS;
  const command = ['tmux', 'attach-session', '-t', sessionName];

  logger.info(`Attaching to tmux session: ${sessionName}`);

  // This will take over the terminal
  const result =
    isWindows && distribution !== undefined && distribution !== ''
      ? await runCommandViaWSL(distribution, command)
      : await runCommand(command);

  if (result.exitCode !== 0) {
    throw new BranchNexusError(
      `Failed to attach to session: ${sessionName}`,
      ExitCode.TMUX_ERROR,
      result.stderr
    );
  }
}

export function getDefaultSessionName(): string {
  return DEFAULT_SESSION_NAME;
}

export async function listSessions(distribution?: string): Promise<string[]> {
  const isWindows = detectPlatform() === Platform.WINDOWS;
  const command = ['tmux', 'list-sessions', '-F', '#{session_name}'];

  try {
    const result =
      isWindows && distribution !== undefined && distribution !== ''
        ? await runCommandViaWSL(distribution, command)
        : await runCommand(command);

    if (result.exitCode !== 0) {
      return [];
    }

    return result.stdout
      .split('\n')
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
  } catch {
    return [];
  }
}
