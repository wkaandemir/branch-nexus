import { type Layout, type ColorTheme } from '../types/index.js';
import { BranchNexusError, ExitCode } from '../types/errors.js';

export interface PaneTarget {
  paneIndex: number;
  worktreePath: string;
}

const VALID_LAYOUTS = new Set(['horizontal', 'vertical', 'grid']);

export function validateLayout(layout: string, panes: number): void {
  if (!VALID_LAYOUTS.has(layout)) {
    throw new BranchNexusError(
      `Unsupported layout: ${layout}`,
      ExitCode.VALIDATION_ERROR,
      'Use horizontal, vertical, or grid.'
    );
  }

  if (panes < 1 || panes > 6) {
    throw new BranchNexusError(
      `Invalid pane count: ${panes}`,
      ExitCode.VALIDATION_ERROR,
      'Use a pane value between 1 and 6.'
    );
  }
}

export function buildLayoutCommands(
  sessionName: string,
  layout: Layout,
  panePaths: string[],
  colorTheme?: ColorTheme,
  paneBranches?: string[],
  paneNames?: string[],
  startupCommands?: string[]
): string[][] {
  const panes = panePaths.length;
  validateLayout(layout, panes);

  const tmuxColor = colorTheme ?? 'cyan';

  const commands: string[][] = [
    ['tmux', 'new-session', '-d', '-s', sessionName, '-c', panePaths[0]],
    ['tmux', 'set-option', '-t', sessionName, 'mouse', 'on'],
    ['tmux', 'bind-key', '-n', 'WheelUpPane', 'send-keys', '-M'],
    ['tmux', 'bind-key', '-n', 'WheelDownPane', 'send-keys', '-M'],
    // Apply color theme
    ['tmux', 'set-option', '-t', sessionName, 'status-style', `bg=${tmuxColor},fg=black`],
    ['tmux', 'set-option', '-t', sessionName, 'pane-border-style', `fg=${tmuxColor}`],
    ['tmux', 'set-option', '-t', sessionName, 'pane-active-border-style', `fg=${tmuxColor},bold`],
    ['tmux', 'set-option', '-t', sessionName, 'status-left', ` ${sessionName} `],
    ['tmux', 'set-option', '-t', sessionName, 'status-left-style', `bg=${tmuxColor},fg=black,bold`],
    ['tmux', 'set-option', '-t', sessionName, 'status-right', ' %H:%M %d-%b-%y '],
    ['tmux', 'set-option', '-t', sessionName, 'status-right-style', `bg=${tmuxColor},fg=black`],
    ['tmux', 'set-option', '-t', sessionName, 'window-status-format', ''],
    ['tmux', 'set-option', '-t', sessionName, 'window-status-current-format', ''],
    // Pane border labels with blinking indicator for active pane
    ['tmux', 'set-option', '-t', sessionName, 'pane-border-status', 'top'],
    ['tmux', 'set-option', '-t', sessionName, 'pane-border-format',
      `#{?pane_active,#[fg=${tmuxColor}#,blink] ● #[noblink#,bold]#{pane_title} #[default],#[fg=grey] ○ #{pane_title} #[default]}`],
  ];

  function paneTitle(index: number): string {
    const customName = paneNames?.[index] ?? '';
    const branch = paneBranches?.[index]?.replace(/^origin\//, '') ?? '';
    if (customName !== '') return `${customName} [${branch}]`;
    return `Pane ${index} [${branch}]`;
  }

  // Set pane title for first pane (pane 0)
  commands.push([
    'tmux', 'select-pane', '-t', `${sessionName}:0.0`,
    '-T', paneTitle(0),
  ]);

  for (let index = 1; index < panes; index++) {
    let splitFlag: string;
    if (layout === 'horizontal') {
      splitFlag = '-h';
    } else if (layout === 'vertical') {
      splitFlag = '-v';
    } else {
      splitFlag = index % 2 === 0 ? '-v' : '-h';
    }

    commands.push([
      'tmux',
      'split-window',
      splitFlag,
      '-t',
      `${sessionName}:0`,
      '-c',
      panePaths[index],
    ]);

    commands.push([
      'tmux', 'select-pane', '-t', `${sessionName}:0.${index}`,
      '-T', paneTitle(index),
    ]);
  }

  let tmuxLayout: string;
  if (layout === 'horizontal') {
    tmuxLayout = 'even-horizontal';
  } else if (layout === 'vertical') {
    tmuxLayout = 'even-vertical';
  } else {
    tmuxLayout = 'tiled';
  }

  commands.push(['tmux', 'select-layout', '-t', `${sessionName}:0`, tmuxLayout]);

  commands.push([
    'tmux',
    'set-hook',
    '-t',
    sessionName,
    'client-resized',
    `select-layout -t ${sessionName}:0 ${tmuxLayout}`,
  ]);

  commands.push(['tmux', 'select-pane', '-t', `${sessionName}:0.0`]);

  // Send startup commands to each pane
  if (startupCommands !== undefined && startupCommands.length > 0) {
    for (let i = 0; i < panes; i++) {
      const cmd = startupCommands[i];
      if (cmd !== undefined && cmd.trim() !== '') {
        commands.push([
          'tmux', 'send-keys', '-t', `${sessionName}:0.${i}`, cmd.trim(), 'Enter',
        ]);
      }
    }
  }

  return commands;
}

export function mapPaneTargets(panePaths: string[]): PaneTarget[] {
  return panePaths.map((path, index) => ({
    paneIndex: index,
    worktreePath: path,
  }));
}
