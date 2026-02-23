import { z } from 'zod';

export const LayoutSchema = z.enum(['horizontal', 'vertical', 'grid']);
export type Layout = z.infer<typeof LayoutSchema>;

export const CleanupPolicySchema = z.enum(['session', 'persistent']);
export type CleanupPolicy = z.infer<typeof CleanupPolicySchema>;

export const ColorThemeSchema = z.enum(['cyan', 'green', 'magenta', 'blue', 'yellow', 'red']);
export type ColorTheme = z.infer<typeof ColorThemeSchema>;

export const TerminalRuntimeSchema = z.enum(['wsl', 'powershell', 'native']);
export type TerminalRuntime = z.infer<typeof TerminalRuntimeSchema>;

export const RepositoryCacheEntrySchema = z.object({
  full_name: z.string(),
  clone_url: z.string(),
});
export type RepositoryCacheEntry = z.infer<typeof RepositoryCacheEntrySchema>;

export const PresetConfigSchema = z.object({
  layout: LayoutSchema,
  panes: z.number().int().min(2).max(6),
  cleanup: CleanupPolicySchema,
});
export type PresetConfig = z.infer<typeof PresetConfigSchema>;

export const AppConfigSchema = z.object({
  defaultRoot: z.string().default(''),
  remoteRepoUrl: z.string().default(''),
  githubToken: z.string().default(''),
  githubRepositoriesCache: z.array(RepositoryCacheEntrySchema).default([]),
  githubBranchesCache: z.record(z.array(z.string())).default({}),
  defaultLayout: LayoutSchema.default('grid'),
  defaultPanes: z.number().int().min(2).max(6).default(4),
  cleanupPolicy: CleanupPolicySchema.default('session'),
  tmuxAutoInstall: z.boolean().default(true),
  wslDistribution: z.string().default(''),
  terminalDefaultRuntime: TerminalRuntimeSchema.default('wsl'),
  terminalMaxCount: z.number().int().min(2).max(16).default(16),
  sessionRestoreEnabled: z.boolean().default(true),
  lastSession: z.record(z.unknown()).default({}),
  colorTheme: ColorThemeSchema.default('cyan'),
  presets: z.record(PresetConfigSchema).default({}),
  commandHooks: z.record(z.array(z.string())).default({}),
});
export type AppConfig = z.infer<typeof AppConfigSchema>;

export const DEFAULT_CONFIG: AppConfig = {
  defaultRoot: '',
  remoteRepoUrl: '',
  githubToken: '',
  githubRepositoriesCache: [],
  githubBranchesCache: {},
  defaultLayout: 'grid',
  defaultPanes: 4,
  cleanupPolicy: 'session',
  tmuxAutoInstall: true,
  wslDistribution: '',
  terminalDefaultRuntime: 'wsl',
  terminalMaxCount: 16,
  sessionRestoreEnabled: true,
  lastSession: {},
  colorTheme: 'cyan',
  presets: {},
  commandHooks: {},
};
