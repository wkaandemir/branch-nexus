import {
  AppConfigSchema,
  LayoutSchema,
  CleanupPolicySchema,
  PresetConfigSchema,
  type AppConfig,
  type Layout,
  type CleanupPolicy,
  type PresetConfig,
} from '../types/index.js';

export {
  AppConfigSchema,
  LayoutSchema,
  CleanupPolicySchema,
  PresetConfigSchema,
  type AppConfig,
  type Layout,
  type CleanupPolicy,
  type PresetConfig,
};

export function validateConfig(config: unknown): AppConfig {
  return AppConfigSchema.parse(config);
}

export function validateLayout(value: string): Layout {
  return LayoutSchema.parse(value);
}

export function validateCleanupPolicy(value: string): CleanupPolicy {
  return CleanupPolicySchema.parse(value);
}

export function validatePresetConfig(config: unknown): PresetConfig {
  return PresetConfigSchema.parse(config);
}

export function isValidLayout(value: string): value is Layout {
  return LayoutSchema.safeParse(value).success;
}

export function isValidCleanupPolicy(value: string): value is CleanupPolicy {
  return CleanupPolicySchema.safeParse(value).success;
}

export function isValidPaneCount(value: number): boolean {
  return Number.isInteger(value) && value >= 2 && value <= 6;
}

export function isValidTerminalCount(value: number): boolean {
  return Number.isInteger(value) && value >= 2 && value <= 16;
}

const SANITIZE_PATTERN = /[^A-Za-z0-9._-]+/g;

export function sanitizePathSegment(value: string): string {
  const cleaned = value.replace(SANITIZE_PATTERN, '-').replace(/^-+|-+$/g, '');
  return cleaned || 'default';
}

export function normalizePath(path: string): string {
  return path.replace(/\\/g, '/');
}

export function posixPath(path: string): string {
  let normalized = normalizePath(path);
  while (normalized.startsWith('//')) {
    normalized = normalized.slice(1);
  }
  return normalized;
}
