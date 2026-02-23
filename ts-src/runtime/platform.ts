import * as os from 'node:os';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { execa } from 'execa';

export enum Platform {
  WINDOWS = 'windows',
  MACOS = 'macos',
  LINUX = 'linux',
}

export function detectPlatform(): Platform {
  const platform = os.platform();

  if (platform === 'win32') {
    return Platform.WINDOWS;
  }

  if (platform === 'darwin') {
    return Platform.MACOS;
  }

  return Platform.LINUX;
}

export function isWSL(): boolean {
  if (detectPlatform() !== Platform.LINUX) {
    return false;
  }

  try {
    const version = fs.readFileSync('/proc/version', 'utf-8');
    return version.toLowerCase().includes('microsoft');
  } catch {
    return false;
  }
}

export async function hasTmux(): Promise<boolean> {
  try {
    await execa('tmux', ['-V']);
    return true;
  } catch {
    return false;
  }
}

export async function getTmuxVersion(): Promise<string | null> {
  try {
    const result = await execa('tmux', ['-V']);
    const match = result.stdout.match(/tmux\s+(\d+\.\d+)/);
    return match ? match[1] : null;
  } catch {
    return null;
  }
}

export function expandHomeDir(filepath: string): string {
  if (filepath.startsWith('~/')) {
    return path.join(os.homedir(), filepath.slice(2));
  }
  return filepath;
}

export function getHomeDir(): string {
  return os.homedir();
}

export function getPlatformInfo(): {
  platform: Platform;
  isWSL: boolean;
  arch: string;
  homedir: string;
} {
  return {
    platform: detectPlatform(),
    isWSL: isWSL(),
    arch: os.arch(),
    homedir: os.homedir(),
  };
}
