import chalk, { type ChalkInstance } from 'chalk';

/* ── Color Palettes ───────────────────────────────────── */

export interface ColorPalette {
  name: string;
  label: string;
  primary: ChalkInstance;
  primaryBold: ChalkInstance;
  bg: ChalkInstance;
}

export const COLOR_PALETTES: Record<string, ColorPalette> = {
  cyan: {
    name: 'cyan',
    label: 'Cyan',
    primary: chalk.cyan,
    primaryBold: chalk.cyan.bold,
    bg: chalk.bgCyan.black.bold,
  },
  green: {
    name: 'green',
    label: 'Yeşil',
    primary: chalk.green,
    primaryBold: chalk.green.bold,
    bg: chalk.bgGreen.black.bold,
  },
  magenta: {
    name: 'magenta',
    label: 'Magenta',
    primary: chalk.magenta,
    primaryBold: chalk.magenta.bold,
    bg: chalk.bgMagenta.black.bold,
  },
  blue: {
    name: 'blue',
    label: 'Mavi',
    primary: chalk.blue,
    primaryBold: chalk.blue.bold,
    bg: chalk.bgBlue.black.bold,
  },
  yellow: {
    name: 'yellow',
    label: 'Sarı',
    primary: chalk.yellow,
    primaryBold: chalk.yellow.bold,
    bg: chalk.bgYellow.black.bold,
  },
  red: {
    name: 'red',
    label: 'Kırmızı',
    primary: chalk.red,
    primaryBold: chalk.red.bold,
    bg: chalk.bgRed.black.bold,
  },
};

export const PALETTE_KEYS = Object.keys(COLOR_PALETTES);

export function getPalette(name: string): ColorPalette {
  return COLOR_PALETTES[name] ?? COLOR_PALETTES.cyan;
}

export const theme = {
  colors: {
    primary: chalk.cyan,
    success: chalk.green,
    warning: chalk.yellow,
    error: chalk.red,
    info: chalk.blue,
    muted: chalk.gray,
    highlight: chalk.white.bold,
    accent: chalk.magenta,
  },

  symbols: {
    pointer: '❯',
    check: '✓',
    cross: '✕',
    radio: {
      on: '●',
      off: '○',
    },
    checkbox: {
      on: '◼',
      off: '◻',
    },
    arrow: {
      left: '←',
      right: '→',
      up: '↑',
      down: '↓',
    },
    box: {
      topLeft: '╔',
      topRight: '╗',
      bottomLeft: '╚',
      bottomRight: '╝',
      horizontal: '═',
      vertical: '║',
      left: '╠',
      right: '╣',
    },
  },

  spacing: {
    xs: 1,
    sm: 2,
    md: 3,
    lg: 4,
  },
};

export function box(title: string, content: string[], width = 60): string {
  const { box: b } = theme.symbols;
  const lines: string[] = [];

  const titleLine = ` ${title} `;
  const titlePadding = Math.floor((width - titleLine.length) / 2);
  const paddedTitle =
    b.horizontal.repeat(titlePadding) +
    titleLine +
    b.horizontal.repeat(width - titlePadding - titleLine.length);

  lines.push(b.topLeft + paddedTitle + b.topRight);

  for (const line of content) {
    const paddedLine = line.padEnd(width - 2);
    lines.push(b.vertical + ' ' + paddedLine + b.vertical);
  }

  lines.push(b.bottomLeft + b.horizontal.repeat(width) + b.bottomRight);

  return lines.join('\n');
}

export function formatPreview(key: string, value: string): string {
  return `${theme.colors.muted(key.padEnd(10))} ${theme.colors.highlight(value)}`;
}
