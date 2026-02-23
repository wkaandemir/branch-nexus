import { execa, type ExecaError } from 'execa';
import { logger } from '../utils/logger.js';
import { BranchNexusError, ExitCode } from '../types/errors.js';
import { buildWslCommand } from './wsl.js';

export interface ShellResult {
  exitCode: number;
  stdout: string;
  stderr: string;
}

export interface RunCommandOptions {
  cwd?: string;
  timeout?: number;
  captureOutput?: boolean;
  input?: string;
}

export async function runCommand(
  command: string[],
  options: RunCommandOptions = {}
): Promise<ShellResult> {
  const [cmd, ...args] = command;
  logger.debug(`Running command: ${command.join(' ')}`);

  try {
    const result = await execa(cmd, args, {
      cwd: options.cwd,
      timeout: options.timeout ?? 30000,
      input: options.input,
      reject: false,
      all: true,
    });

    return {
      exitCode: result.exitCode,
      stdout: result.stdout,
      stderr: result.stderr,
    };
  } catch (error) {
    const execaError = error as ExecaError;
    return {
      exitCode: execaError.exitCode ?? 1,
      stdout: execaError.stdout ?? '',
      stderr: execaError.stderr ?? execaError.message,
    };
  }
}

export async function runCommandViaWSL(
  distribution: string,
  command: string[],
  options: RunCommandOptions = {}
): Promise<ShellResult> {
  const wrapped = buildWslCommand(distribution, command);
  logger.debug(`Running WSL command: ${wrapped.join(' ')}`);
  return runCommand(wrapped, options);
}

export async function runCommandChecked(
  command: string[],
  options: RunCommandOptions = {}
): Promise<ShellResult> {
  const result = await runCommand(command, options);

  if (result.exitCode !== 0) {
    throw new BranchNexusError(
      `Command failed: ${command.join(' ')}`,
      ExitCode.RUNTIME_ERROR,
      result.stderr || `Exit code: ${result.exitCode}`
    );
  }

  return result;
}

export async function runCommandViaWSLChecked(
  distribution: string,
  command: string[],
  options: RunCommandOptions = {}
): Promise<ShellResult> {
  const result = await runCommandViaWSL(distribution, command, options);

  if (result.exitCode !== 0) {
    throw new BranchNexusError(
      `WSL command failed: ${command.join(' ')}`,
      ExitCode.RUNTIME_ERROR,
      result.stderr || `Exit code: ${result.exitCode}`
    );
  }

  return result;
}
