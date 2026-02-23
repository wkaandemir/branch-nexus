import { runCommand } from '../runtime/shell.js';
import { logger } from '../utils/logger.js';
import { BranchNexusError, ExitCode } from '../types/errors.js';
import { Platform, detectPlatform } from '../runtime/platform.js';

export interface BootstrapResult {
  tmuxAvailable: boolean;
  installAttempted: boolean;
}

const INSTALL_COMMANDS: Record<string, string> = {
  debian: 'sudo apt-get update && sudo apt-get install -y tmux',
  fedora: 'sudo dnf install -y tmux',
  arch: 'sudo pacman -S --noconfirm tmux',
  alpine: 'sudo apk add tmux',
  void: 'sudo xbps-install -Sy tmux',
  gentoo: 'sudo emerge app-misc/tmux',
  nixos: 'nix profile install nixpkgs#tmux',
  macos: 'brew install tmux',
};

function getInstallCommand(osRelease: string): string {
  const lowered = osRelease.toLowerCase();

  const debianIds = ['debian', 'ubuntu', 'pengwin', 'kali', 'mint', 'pop', 'elementary', 'zorin'];
  if (
    debianIds.some((name) => lowered.includes(name)) ||
    lowered.replace(/\s/g, '').includes('id_like=debian')
  ) {
    return INSTALL_COMMANDS['debian'];
  }

  const rhelIds = ['fedora', 'rhel', 'centos', 'rocky', 'almalinux', 'oracle', 'amazon'];
  if (rhelIds.some((name) => lowered.includes(name))) {
    return INSTALL_COMMANDS['fedora'];
  }

  const archIds = ['arch', 'manjaro', 'endeavouros', 'garuda'];
  if (
    archIds.some((name) => lowered.includes(name)) ||
    lowered.replace(/\s/g, '').includes('id_like=arch')
  ) {
    return INSTALL_COMMANDS['arch'];
  }

  if (lowered.includes('opensuse') || lowered.includes('suse')) {
    return 'sudo zypper install -y tmux';
  }

  if (lowered.includes('alpine')) {
    return INSTALL_COMMANDS['alpine'];
  }

  if (lowered.includes('void')) {
    return INSTALL_COMMANDS['void'];
  }

  if (lowered.includes('gentoo')) {
    return INSTALL_COMMANDS['gentoo'];
  }

  if (lowered.includes('nixos') || lowered.includes('nix')) {
    return INSTALL_COMMANDS['nixos'];
  }

  throw new BranchNexusError(
    'Unsupported distribution for automatic tmux install.',
    ExitCode.TMUX_ERROR,
    'Install tmux manually inside the selected distribution.'
  );
}

function getManualInstallGuidance(osRelease: string): string {
  try {
    const cmd = getInstallCommand(osRelease);
    return `Run this inside WSL: ${cmd}`;
  } catch {
    return 'Install tmux manually in the selected distribution and retry.';
  }
}

export async function ensureTmux(
  distribution: string,
  options?: { autoInstall?: boolean }
): Promise<BootstrapResult> {
  logger.debug(`Checking tmux availability in distribution=${distribution}`);

  const isWindows = detectPlatform() === Platform.WINDOWS;

  const checkCommand = isWindows
    ? ['wsl.exe', '-d', distribution, '--', 'command', '-v', 'tmux']
    : ['tmux'];

  try {
    const result = isWindows
      ? await runCommand(checkCommand)
      : await runCommand(['command', '-v', 'tmux']);

    if (result.exitCode === 0) {
      logger.debug(`tmux is already installed`);
      return { tmuxAvailable: true, installAttempted: false };
    }
  } catch {
    // Continue to install attempt
  }

  if (options?.autoInstall !== true) {
    throw new BranchNexusError(
      'tmux is not installed in selected WSL distribution.',
      ExitCode.TMUX_ERROR,
      'Install tmux manually or enable auto-install.'
    );
  }

  let osRelease = '';
  if (isWindows) {
    const osReleaseResult = await runCommand([
      'wsl.exe',
      '-d',
      distribution,
      '--',
      'cat',
      '/etc/os-release',
    ]);
    osRelease = osReleaseResult.stdout;
  } else if (detectPlatform() === Platform.MACOS) {
    osRelease = 'macos';
  } else {
    const fs = await import('node:fs/promises');
    try {
      osRelease = await fs.readFile('/etc/os-release', 'utf-8');
    } catch {
      osRelease = '';
    }
  }

  logger.warn(`tmux not found, attempting auto-install`);

  const installCmd = getInstallCommand(osRelease);

  // Try non-interactive install first
  const nonInteractiveCmd = installCmd.replace('sudo ', 'sudo -n ');
  logger.debug(`Trying non-interactive tmux install`);

  const nonInteractiveResult = isWindows
    ? await runCommand(['wsl.exe', '-d', distribution, '--', 'bash', '-lc', nonInteractiveCmd])
    : await runCommand(['bash', '-lc', nonInteractiveCmd]);

  if (nonInteractiveResult.exitCode === 0) {
    logger.info('Non-interactive tmux install succeeded');
    return { tmuxAvailable: true, installAttempted: true };
  }

  throw new BranchNexusError(
    'Interactive tmux installation required.',
    ExitCode.TMUX_ERROR,
    getManualInstallGuidance(osRelease)
  );
}
