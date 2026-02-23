import { resolve, dirname } from 'node:path';
import { existsSync, mkdirSync } from 'node:fs';
import { homedir } from 'node:os';

export function expandHomeDir(filepath: string): string {
  if (filepath.startsWith('~/')) {
    return resolve(homedir(), filepath.slice(2));
  }
  return filepath;
}

export function ensureDir(dir: string): string {
  const expanded = expandHomeDir(dir);
  if (!existsSync(expanded)) {
    mkdirSync(expanded, { recursive: true });
  }
  return expanded;
}

export function ensureParentDir(filepath: string): string {
  const parent = dirname(filepath);
  ensureDir(parent);
  return filepath;
}
