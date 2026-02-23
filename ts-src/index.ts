export {
  type AppConfig,
  type Layout,
  type CleanupPolicy,
  type TerminalRuntime,
  type RepositoryCacheEntry,
  type PresetConfig,
  DEFAULT_CONFIG,
} from './types/index.js';

export { BranchNexusError, ExitCode, userFacingError } from './types/errors.js';

export { loadConfig, saveConfig, getConfigPath } from './core/config.js';

export {
  savePreset,
  loadPresets,
  applyPreset,
  deletePreset,
  renamePreset,
} from './core/presets.js';

export {
  orchestrate,
  type OrchestrationRequest,
  type OrchestrationResult,
} from './core/orchestrator.js';

export { WorktreeManager } from './git/worktree.js';
export { listLocalBranches, type BranchListResult } from './git/branch.js';

export { buildLayoutCommands, validateLayout } from './tmux/layouts.js';
export {
  startSession,
  killSession,
  sessionExists,
  listSessions,
  attachSession,
} from './tmux/session.js';

export { detectPlatform, Platform, hasTmux, expandHomeDir } from './runtime/platform.js';
export { listDistributions, buildWslCommand, toWslPath } from './runtime/wsl.js';
export { runCommand, runCommandViaWSL, type ShellResult } from './runtime/shell.js';

export {
  runCommand as run,
  initCommand,
  configCommand,
  killCommand,
  presetCommand,
  statusCommand,
  attachCommand,
} from './commands/index.js';

export { HookRunner, type HookRunResult, type HookExecution } from './hooks/runner.js';
export { GitHubClient, type GitHubRepo, type GitHubBranch } from './github/api.js';
