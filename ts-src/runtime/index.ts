export {
  Platform,
  detectPlatform,
  isWSL,
  hasTmux,
  getTmuxVersion,
  expandHomeDir,
  getHomeDir,
  getPlatformInfo,
} from './platform.js';

export {
  listDistributions,
  validateDistribution,
  buildWslCommand,
  toWslPath,
  distributionUnreachableMessage,
} from './wsl.js';

export {
  runCommand,
  runCommandViaWSL,
  runCommandChecked,
  runCommandViaWSLChecked,
  type ShellResult,
  type RunCommandOptions,
} from './shell.js';
