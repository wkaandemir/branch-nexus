import { execa } from 'execa';
import { logger } from '../utils/logger.js';
import { buildWslCommand } from '../runtime/wsl.js';
import { Platform, detectPlatform } from '../runtime/platform.js';
import { hasDistribution } from '../utils/validators.js';

export interface HookExecution {
  command: string;
  success: boolean;
  returncode: number;
  output: string;
}

export interface HookRunResult {
  pane: number;
  executions: HookExecution[];
  hasFailures: boolean;
}

export class HookRunner {
  private timeoutSeconds: number;
  private trustedConfig: boolean;
  private allowCommandPrefixes: string[];

  constructor(options?: {
    timeoutSeconds?: number;
    trustedConfig?: boolean;
    allowCommandPrefixes?: string[];
  }) {
    this.timeoutSeconds = options?.timeoutSeconds ?? 30;
    this.trustedConfig = options?.trustedConfig ?? true;
    this.allowCommandPrefixes = options?.allowCommandPrefixes ?? [];
  }

  private isCommandAllowed(command: string): boolean {
    if (this.trustedConfig) {
      return true;
    }

    const argv = command.split(/\s+/);
    if (argv.length === 0) {
      return false;
    }

    if (this.allowCommandPrefixes.length === 0) {
      return false;
    }

    return this.allowCommandPrefixes.includes(argv[0]);
  }

  async run(pane: number, commands: string[], distribution?: string): Promise<HookRunResult> {
    const executions: HookExecution[] = [];
    logger.debug(`Running ${commands.length} hook commands for pane=${pane}`);

    for (const command of commands) {
      if (!this.isCommandAllowed(command)) {
        logger.warn(`Hook command blocked by policy pane=${pane} command=${command}`);
        executions.push({
          command,
          success: false,
          returncode: 126,
          output: 'Command blocked by hook trust policy.',
        });
        continue;
      }

      try {
        logger.debug(`Executing hook command pane=${pane} command=${command}`);

        const isWindows = detectPlatform() === Platform.WINDOWS;
        const cmd = ['bash', '-lc', command];
        const finalCmd =
          isWindows && hasDistribution(distribution) ? buildWslCommand(distribution, cmd) : cmd;

        const result = await execa(finalCmd[0], finalCmd.slice(1), {
          timeout: this.timeoutSeconds * 1000,
          reject: false,
          all: true,
        });

        const success = result.exitCode === 0;
        const output = `${result.stdout}${result.stderr}`.trim();

        if (!success) {
          logger.warn(
            `Hook command failed pane=${pane} returncode=${result.exitCode} command=${command}`
          );
        }

        executions.push({
          command,
          success,
          returncode: result.exitCode,
          output,
        });
      } catch (error) {
        const isTimeout = error instanceof Error && error.message.includes('timed out');
        logger.error(
          `Hook command ${isTimeout ? 'timed out' : 'failed'} pane=${pane} command=${command}`
        );

        executions.push({
          command,
          success: false,
          returncode: isTimeout ? 124 : 1,
          output: isTimeout
            ? 'Command timed out.'
            : error instanceof Error
              ? error.message
              : 'Unknown error',
        });
      }
    }

    return {
      pane,
      executions,
      hasFailures: executions.some((e) => !e.success),
    };
  }
}
