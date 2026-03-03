import { z } from 'zod';
import Conf from 'conf';
import {
  type AppConfig,
  DEFAULT_CONFIG,
  AppConfigSchema,
  type CleanupPolicy,
  type ColorTheme,
  type Layout,
} from '../types/index.js';
import { BranchNexusError, ExitCode } from '../types/errors.js';

const GITHUB_TOKEN_ENV = 'BRANCHNEXUS_GH_TOKEN';

const configStore = new Conf<AppConfig>({
  projectName: 'branch-nexus',
  configName: 'config',
  defaults: DEFAULT_CONFIG,
  schema: {
    defaultRoot: { type: 'string' },
    remoteRepoUrl: { type: 'string' },
    githubToken: { type: 'string' },
    githubRepositoriesCache: { type: 'array' },
    githubBranchesCache: { type: 'object' },
    defaultLayout: { type: 'string', enum: ['horizontal', 'vertical', 'grid'] },
    defaultPanes: { type: 'number', minimum: 2, maximum: 6 },
    cleanupPolicy: { type: 'string', enum: ['session', 'persistent'] },
    tmuxAutoInstall: { type: 'boolean' },
    wslDistribution: { type: 'string' },
    terminalDefaultRuntime: { type: 'string', enum: ['wsl', 'powershell', 'native'] },
    terminalMaxCount: { type: 'number', minimum: 2, maximum: 16 },
    sessionRestoreEnabled: { type: 'boolean' },
    lastSession: { type: 'object' },
    colorTheme: { type: 'string', enum: ['cyan', 'green', 'magenta', 'blue', 'yellow', 'red'] },
    presets: { type: 'object' },
    commandHooks: { type: 'object' },
  } as const,
});

export function getConfigPath(): string {
  return configStore.path;
}

export function loadConfig(): AppConfig {
  try {
    const raw = configStore.store;
    const config = AppConfigSchema.parse(raw);

    const envToken = process.env[GITHUB_TOKEN_ENV];
    if (envToken !== undefined && envToken.trim() !== '') {
      config.githubToken = envToken.trim();
    }

    return config;
  } catch (error) {
    if (error instanceof z.ZodError) {
      throw new BranchNexusError(
        'Configuration validation failed',
        ExitCode.CONFIG_ERROR,
        error.message
      );
    }
    return { ...DEFAULT_CONFIG };
  }
}

export function saveConfig(config: AppConfig): void {
  const validated = AppConfigSchema.parse(config);
  configStore.store = validated;
}

export function resetConfig(): AppConfig {
  configStore.store = DEFAULT_CONFIG;
  return { ...DEFAULT_CONFIG };
}

export function setWslDistribution(distribution: string): AppConfig {
  const config = loadConfig();
  config.wslDistribution = distribution;
  saveConfig(config);
  return config;
}

export function setDefaultRoot(root: string): AppConfig {
  const config = loadConfig();
  config.defaultRoot = root;
  saveConfig(config);
  return config;
}

export function setGithubToken(token: string): AppConfig {
  const config = loadConfig();
  config.githubToken = token;
  saveConfig(config);
  return config;
}

export function updateGithubRepoCache(
  repos: Array<{ full_name: string; clone_url: string }>
): AppConfig {
  const config = loadConfig();
  config.githubRepositoriesCache = repos.map((repo) => ({
    full_name: repo.full_name,
    clone_url: repo.clone_url,
  }));
  saveConfig(config);
  return config;
}

export function updateGithubBranchesCache(repoName: string, branches: string[]): AppConfig {
  const config = loadConfig();
  config.githubBranchesCache = {
    ...config.githubBranchesCache,
    [repoName]: branches,
  };
  saveConfig(config);
  return config;
}

export function updateLastSession(session: Record<string, unknown>): AppConfig {
  const config = loadConfig();
  config.lastSession = session;
  saveConfig(config);
  return config;
}

export function setConfigValue(key: string, value: string): AppConfig {
  const config = loadConfig();

  switch (key) {
    case 'defaultRoot':
      config.defaultRoot = value;
      break;
    case 'remoteRepoUrl':
      config.remoteRepoUrl = value;
      break;
    case 'githubToken':
      config.githubToken = value;
      break;
    case 'defaultLayout':
      if (['horizontal', 'vertical', 'grid'].includes(value)) {
        config.defaultLayout = value as Layout;
      }
      break;
    case 'defaultPanes':
      config.defaultPanes = parseInt(value, 10);
      break;
    case 'cleanupPolicy':
      if (['session', 'persistent'].includes(value)) {
        config.cleanupPolicy = value as CleanupPolicy;
      }
      break;
    case 'wslDistribution':
      config.wslDistribution = value;
      break;
    case 'terminalMaxCount':
      config.terminalMaxCount = parseInt(value, 10);
      break;
    case 'tmuxAutoInstall':
      config.tmuxAutoInstall = value === 'true';
      break;
    case 'sessionRestoreEnabled':
      config.sessionRestoreEnabled = value === 'true';
      break;
    case 'colorTheme':
      if (['cyan', 'green', 'magenta', 'blue', 'yellow', 'red'].includes(value)) {
        config.colorTheme = value as ColorTheme;
      }
      break;
    default:
      throw new BranchNexusError(
        `Unknown config key: ${key}`,
        ExitCode.CONFIG_ERROR,
        'Use "branch-nexus config show" to see available keys.'
      );
  }

  saveConfig(config);
  return config;
}
