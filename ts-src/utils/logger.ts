import { appendFileSync, mkdirSync, existsSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { homedir } from 'node:os';

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

const LOG_LEVELS: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

let currentLevel: LogLevel = 'info';
let logFilePath: string | null = null;

const DEFAULT_LOG_DIR = '.config/branchnexus/logs';
const DEFAULT_LOG_FILE = 'branchnexus.log';

export function defaultLogPath(): string {
  const logDir = resolve(homedir(), DEFAULT_LOG_DIR);
  return resolve(logDir, DEFAULT_LOG_FILE);
}

export function configureLogging(options?: { level?: LogLevel; logFile?: string }): void {
  if (options?.level !== undefined) {
    currentLevel = options.level;
  }
  if (options?.logFile !== undefined && options.logFile !== '') {
    logFilePath = resolve(options.logFile);
    const logDir = dirname(logFilePath);
    if (!existsSync(logDir)) {
      mkdirSync(logDir, { recursive: true });
    }
  }
}

function formatMessage(level: LogLevel, message: string, args: unknown[]): string {
  const timestamp = new Date().toISOString();
  const formattedArgs =
    args.length > 0 ? ' ' + args.map((arg) => JSON.stringify(arg)).join(' ') : '';
  return `${timestamp} ${level.toUpperCase()} ${message}${formattedArgs}`;
}

function log(level: LogLevel, message: string, args: unknown[]): void {
  if (LOG_LEVELS[level] < LOG_LEVELS[currentLevel]) {
    return;
  }

  const formatted = formatMessage(level, message, args);

  if (level === 'error') {
    console.error(formatted);
  } else if (level === 'warn') {
    console.warn(formatted);
  } else {
    console.log(formatted);
  }

  if (logFilePath !== null) {
    try {
      appendFileSync(logFilePath, formatted + '\n', 'utf-8');
    } catch {
      // Ignore file write errors
    }
  }
}

export const logger = {
  debug: (message: string, ...args: unknown[]): void => {
    log('debug', message, args);
  },
  info: (message: string, ...args: unknown[]): void => {
    log('info', message, args);
  },
  warn: (message: string, ...args: unknown[]): void => {
    log('warn', message, args);
  },
  error: (message: string, ...args: unknown[]): void => {
    log('error', message, args);
  },
};

export function createFileLogger(logFile: string): void {
  logFilePath = resolve(logFile);
  const logDir = dirname(logFilePath);
  if (!existsSync(logDir)) {
    mkdirSync(logDir, { recursive: true });
  }
  writeFileSync(logFilePath, '', 'utf-8');
}
