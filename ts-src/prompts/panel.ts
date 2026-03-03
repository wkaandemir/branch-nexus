import * as p from '@clack/prompts';
import * as readline from 'node:readline';
import chalk from 'chalk';
import { type Layout, type CleanupPolicy, type ColorTheme } from '../types/index.js';
import { loadConfig, setGithubToken, saveConfig } from '../core/config.js';
import { loadPresets, applyPreset } from '../core/presets.js';
import {
  formatPreview,
  type ColorPalette,
  getPalette,
  PALETTE_KEYS,
  COLOR_PALETTES,
} from '../utils/theme.js';
import { showGitHubBrowser } from './github-browser.js';
import { visibleLength } from '../utils/ansi.js';

export interface PanelResult {
  token: string | null;
  repoUrl: string;
  repoUrls: string[];
  layout: Layout;
  paneCount: number;
  cleanup: CleanupPolicy;
  colorTheme: ColorTheme;
}

/* ── Option constants ─────────────────────────────────── */

const LAYOUTS: { value: Layout; label: string }[] = [
  { value: 'grid', label: 'Grid (2x2)' },
  { value: 'horizontal', label: 'Yatay' },
  { value: 'vertical', label: 'Dikey' },
];

const PANE_OPTIONS = [1, 2, 3, 4, 5, 6];

const CLEANUP_OPTIONS: { value: CleanupPolicy; label: string }[] = [
  { value: 'session', label: 'Session' },
  { value: 'persistent', label: 'Persistent' },
];

/* ── Field IDs (panel form) ───────────────────────────── */

const FIELD = {
  HAS_TOKEN: 0,
  TOKEN: 1,
  REPO: 2,
  LAYOUT: 3,
  PANES: 4,
  CLEANUP: 5,
  COLOR: 6,
  SUBMIT: 7,
} as const;

const COLOR_OPTIONS = PALETTE_KEYS.map((key) => ({
  value: key as ColorTheme,
  label: COLOR_PALETTES[key].label,
}));

/* ── Shared types & helpers ───────────────────────────── */

interface KeypressKey {
  name?: string;
  ctrl?: boolean;
  meta?: boolean;
  shift?: boolean;
}

const CLR = '\x1B[K';

function padToWidth(content: string, width: number): string {
  const pad = Math.max(0, width - visibleLength(content));
  return content + ' '.repeat(pad);
}

function boxLine(content: string, width: number): string {
  return '║' + padToWidth(content, width) + '║' + CLR;
}

function boxTop(title: string, width: number, pal: ColorPalette): string {
  const tPad = Math.floor((width - title.length) / 2);
  return (
    '╔' +
    '═'.repeat(tPad) +
    pal.primaryBold(title) +
    '═'.repeat(width - tPad - title.length) +
    '╗' +
    CLR
  );
}

function boxMid(width: number): string {
  return '╠' + '═'.repeat(width) + '╣' + CLR;
}

function boxBottom(width: number): string {
  return '╚' + '═'.repeat(width) + '╝' + CLR;
}

function selectDisplay(label: string, focused: boolean, pal: ColorPalette): string {
  if (focused) {
    return chalk.dim('◀ ') + pal.primaryBold(label) + chalk.dim(' ▶');
  }
  return chalk.white(label);
}

function renderButton(label: string, focused: boolean, width: number, pal: ColorPalette): string {
  const btn = focused ? pal.bg(` ▶ ${label} `) : chalk.dim(` ▶ ${label} `);
  const btnLen = visibleLength(btn);
  const left = Math.floor((width - btnLen) / 2);
  const right = Math.max(0, width - left - btnLen);
  return '║' + ' '.repeat(left) + btn + ' '.repeat(right) + '║' + CLR;
}

/** Shared keypress loop — returns a promise + teardown hook */
function attachKeypress(handler: (str: string | undefined, key: KeypressKey) => void): {
  teardown: () => void;
} {
  readline.emitKeypressEvents(process.stdin);
  const wasRaw = process.stdin.isRaw ?? false;
  if (process.stdin.isTTY === true) {
    process.stdin.setRawMode(true);
  }
  process.stdin.resume();

  function onKey(str: string | undefined, key: KeypressKey): void {
    if (key === undefined || key === null) return;
    if (key.ctrl === true && key.name === 'c') {
      teardown();
      process.exit(0);
    }
    handler(str, key);
  }

  function teardown(): void {
    process.stdin.removeListener('keypress', onKey);
    if (process.stdin.isTTY === true) {
      process.stdin.setRawMode(wasRaw);
    }
    process.stdout.write('\x1B[?25h');
    process.stdin.pause();
  }

  process.stdin.on('keypress', onKey);
  return { teardown };
}

function createDrawFn(renderFn: () => string): (editing: boolean) => void {
  let first = true;
  return (editing: boolean): void => {
    process.stdout.write(first ? '\x1B[2J\x1B[H' : '\x1B[H');
    first = false;
    process.stdout.write(editing ? '\x1B[?25h' : '\x1B[?25l');
    process.stdout.write(renderFn() + '\x1B[J\n');
  };
}

/* ═══════════════════════════════════════════════════════
   PANEL FORM (config)
   ═══════════════════════════════════════════════════════ */

interface PanelState {
  focusIndex: number;
  editing: boolean;
  editBuffer: string;
  error: string;
  hasToken: boolean;
  token: string;
  repoUrl: string;
  layoutIndex: number;
  panesIndex: number;
  cleanupIndex: number;
  colorIndex: number;
}

function getPanelNav(state: PanelState): number[] {
  const fields: number[] = [FIELD.HAS_TOKEN];
  if (state.hasToken) {
    fields.push(FIELD.TOKEN);
  }
  fields.push(FIELD.REPO, FIELD.LAYOUT, FIELD.PANES, FIELD.CLEANUP, FIELD.COLOR, FIELD.SUBMIT);
  return fields;
}

function renderPanel(state: PanelState): string {
  const W = 58;
  const LBL_W = 17;
  const lines: string[] = [];
  const pal = getPalette(COLOR_OPTIONS[state.colorIndex].value);

  function fRow(id: number, label: string, value: string): string {
    const focused = state.focusIndex === id;
    const ptr = focused ? pal.primary('❯') : ' ';
    const lbl = focused ? pal.primaryBold(label.padEnd(LBL_W)) : chalk.white(label.padEnd(LBL_W));
    return boxLine(`  ${ptr} ${lbl} ${value}`, W);
  }

  lines.push(boxTop(' BranchNexus ', W, pal));
  lines.push(boxLine('  ' + chalk.dim('Multi-Branch Workspace Manager'), W));
  lines.push(boxMid(W));
  lines.push(boxLine('', W));

  // 1) GitHub Token toggle
  const tokLabel = state.hasToken ? 'Evet' : 'Hayır';
  lines.push(
    fRow(
      FIELD.HAS_TOKEN,
      'GitHub Token',
      selectDisplay(tokLabel, state.focusIndex === FIELD.HAS_TOKEN, pal)
    )
  );

  // 2) Token input (conditional)
  if (state.hasToken) {
    let tv: string;
    if (state.focusIndex === FIELD.TOKEN && state.editing) {
      tv = pal.primary(state.editBuffer + '█');
    } else if (state.token !== '') {
      tv = chalk.dim('*'.repeat(Math.min(state.token.length, 20)));
    } else {
      tv = chalk.dim('(Enter ile girin)');
    }
    lines.push(fRow(FIELD.TOKEN, '  Token', tv));
  }

  // 3) Repository URL
  let rv: string;
  if (state.focusIndex === FIELD.REPO && state.editing) {
    const buf = state.editBuffer;
    rv = pal.primary((buf.length > 28 ? '...' + buf.slice(-25) : buf) + '█');
  } else if (state.repoUrl !== '') {
    const s = state.repoUrl;
    rv = chalk.white(s.length > 30 ? s.slice(0, 27) + '...' : s);
  } else {
    rv = chalk.dim('(Enter ile girin)');
  }
  lines.push(fRow(FIELD.REPO, 'Repository URL', rv));

  // 4) Layout
  lines.push(
    fRow(
      FIELD.LAYOUT,
      'Layout',
      selectDisplay(LAYOUTS[state.layoutIndex].label, state.focusIndex === FIELD.LAYOUT, pal)
    )
  );

  // 5) Pane Count
  lines.push(
    fRow(
      FIELD.PANES,
      'Pane Sayısı',
      selectDisplay(String(PANE_OPTIONS[state.panesIndex]), state.focusIndex === FIELD.PANES, pal)
    )
  );

  // 6) Cleanup
  lines.push(
    fRow(
      FIELD.CLEANUP,
      'Cleanup',
      selectDisplay(
        CLEANUP_OPTIONS[state.cleanupIndex].label,
        state.focusIndex === FIELD.CLEANUP,
        pal
      )
    )
  );

  // 7) Color Theme
  const colorLabel = COLOR_OPTIONS[state.colorIndex].label;
  const colorPreview = pal.primary('■ ') + colorLabel;
  lines.push(
    fRow(FIELD.COLOR, 'Renk', selectDisplay(colorPreview, state.focusIndex === FIELD.COLOR, pal))
  );

  lines.push(boxLine('', W));

  if (state.error !== '') {
    lines.push(boxLine('  ' + chalk.red('⚠ ' + state.error), W));
    lines.push(boxLine('', W));
  }

  lines.push(renderButton('BAŞLAT', state.focusIndex === FIELD.SUBMIT, W, pal));
  lines.push(boxLine('', W));
  lines.push(boxMid(W));
  const help = state.editing
    ? 'Yazın...  Enter Onayla  Esc İptal  Ctrl+U Temizle'
    : '↑↓ Gezin  ←→ Değiştir  Enter Düzenle  P Preset  G GitHub  Esc Çıkış';
  lines.push(boxLine('  ' + chalk.dim(help), W));
  lines.push(boxBottom(W));

  return lines.join('\n');
}

export async function showPanel(): Promise<PanelResult | null> {
  const config = loadConfig();

  let layoutIdx = LAYOUTS.findIndex((l) => l.value === config.defaultLayout);
  if (layoutIdx < 0) layoutIdx = 0;
  let panesIdx = PANE_OPTIONS.indexOf(config.defaultPanes > 0 ? config.defaultPanes : 4);
  if (panesIdx < 0) panesIdx = 3; // default 4
  let cleanupIdx = CLEANUP_OPTIONS.findIndex((o) => o.value === config.cleanupPolicy);
  if (cleanupIdx < 0) cleanupIdx = 0;

  let colorIdx = PALETTE_KEYS.indexOf(config.colorTheme);
  if (colorIdx < 0) colorIdx = 0;

  const state: PanelState = {
    focusIndex: FIELD.REPO,
    editing: false,
    editBuffer: '',
    error: '',
    hasToken: config.githubToken !== undefined && config.githubToken !== '',
    token: '',
    repoUrl: '',
    layoutIndex: layoutIdx,
    panesIndex: panesIdx,
    cleanupIndex: cleanupIdx,
    colorIndex: colorIdx,
  };

  return new Promise<PanelResult | null>((resolve) => {
    const draw = createDrawFn(() => renderPanel(state));
    const { teardown } = attachKeypress((str, key) => {
      state.error = '';
      if (state.editing) {
        panelEdit(str, key);
      } else {
        panelNav(str, key);
      }
    });

    function done(result: PanelResult | null): void {
      teardown();
      console.clear();
      resolve(result);
    }

    function panelEdit(str: string | undefined, key: KeypressKey): void {
      if (key.name === 'return') {
        if (state.focusIndex === FIELD.TOKEN) state.token = state.editBuffer;
        else if (state.focusIndex === FIELD.REPO) state.repoUrl = state.editBuffer;
        state.editing = false;
        draw(false);
        return;
      }
      if (key.name === 'escape') {
        state.editing = false;
        draw(false);
        return;
      }
      if (key.name === 'backspace') {
        state.editBuffer = state.editBuffer.slice(0, -1);
        draw(true);
        return;
      }
      if (key.ctrl === true && key.name === 'u') {
        state.editBuffer = '';
        draw(true);
        return;
      }
      if (str !== undefined && str !== '' && key.ctrl !== true && key.meta !== true) {
        state.editBuffer += str;
        draw(true);
      }
    }

    function panelNav(str: string | undefined, key: KeypressKey): void {
      const nav = getPanelNav(state);
      const idx = nav.indexOf(state.focusIndex);

      if (key.name === 'escape') {
        done(null);
        return;
      }

      if (key.name === 'up' || (key.name === 'tab' && key.shift === true)) {
        if (idx > 0) state.focusIndex = nav[idx - 1];
        draw(false);
        return;
      }
      if (key.name === 'down' || key.name === 'tab') {
        if (idx < nav.length - 1) state.focusIndex = nav[idx + 1];
        draw(false);
        return;
      }

      if (key.name === 'left' || key.name === 'right') {
        const d = key.name === 'right' ? 1 : -1;
        panelCycle(d);
        draw(false);
        return;
      }
      if (key.name === 'space') {
        panelCycle(1);
        draw(false);
        return;
      }

      // P key → load preset
      if (str === 'p' || str === 'P') {
        const presets = loadPresets();
        const names = Object.keys(presets);
        if (names.length === 0) {
          state.error = 'Kayıtlı preset yok';
          draw(false);
          return;
        }
        // Cycle through presets: apply next one
        const currentConfig = `${LAYOUTS[state.layoutIndex].value}-${PANE_OPTIONS[state.panesIndex]}-${CLEANUP_OPTIONS[state.cleanupIndex].value}`;
        let nextIdx = 0;
        for (let i = 0; i < names.length; i++) {
          const pr = presets[names[i]];
          const key = `${pr.layout}-${pr.panes}-${pr.cleanup}`;
          if (key === currentConfig && i < names.length - 1) {
            nextIdx = i + 1;
            break;
          }
        }
        const preset = applyPreset(names[nextIdx]);
        const li = LAYOUTS.findIndex((l) => l.value === preset.layout);
        if (li >= 0) state.layoutIndex = li;
        const pi = PANE_OPTIONS.indexOf(preset.panes);
        if (pi >= 0) state.panesIndex = pi;
        const ci = CLEANUP_OPTIONS.findIndex((o) => o.value === preset.cleanup);
        if (ci >= 0) state.cleanupIndex = ci;
        state.error = `Preset: ${names[nextIdx]}`;
        draw(false);
        return;
      }

      // G key → GitHub browser
      if (str === 'g' || str === 'G') {
        const token = state.hasToken && state.token !== '' ? state.token : loadConfig().githubToken;
        if (token === '') {
          state.error = 'GitHub token gerekli';
          draw(false);
          return;
        }
        // Temporarily teardown panel keypress to give control to browser
        teardown();
        showGitHubBrowser(token)
          .then((result) => {
            if (result !== null) {
              state.repoUrl = result.cloneUrl;
            }
            // Re-attach panel keypress
            const reattached = attachKeypress((s, k) => {
              state.error = '';
              if (state.editing) {
                panelEdit(s, k);
              } else {
                panelNav(s, k);
              }
            });
            // Replace teardown reference
            Object.assign({ teardown: reattached.teardown });
            draw(false);
          })
          .catch(() => {
            draw(false);
          });
        return;
      }

      if (key.name === 'return') {
        panelEnter();
        return;
      }
    }

    function panelCycle(d: number): void {
      switch (state.focusIndex) {
        case FIELD.HAS_TOKEN:
          state.hasToken = !state.hasToken;
          break;
        case FIELD.LAYOUT:
          state.layoutIndex = (state.layoutIndex + d + LAYOUTS.length) % LAYOUTS.length;
          break;
        case FIELD.PANES:
          state.panesIndex = (state.panesIndex + d + PANE_OPTIONS.length) % PANE_OPTIONS.length;
          break;
        case FIELD.CLEANUP:
          state.cleanupIndex =
            (state.cleanupIndex + d + CLEANUP_OPTIONS.length) % CLEANUP_OPTIONS.length;
          break;
        case FIELD.COLOR:
          state.colorIndex = (state.colorIndex + d + COLOR_OPTIONS.length) % COLOR_OPTIONS.length;
          break;
      }
    }

    function panelEnter(): void {
      if (state.focusIndex === FIELD.TOKEN || state.focusIndex === FIELD.REPO) {
        state.editing = true;
        state.editBuffer = state.focusIndex === FIELD.TOKEN ? state.token : state.repoUrl;
        draw(true);
        return;
      }
      if (state.focusIndex === FIELD.HAS_TOKEN) {
        state.hasToken = !state.hasToken;
        draw(false);
        return;
      }

      if (state.focusIndex === FIELD.SUBMIT) {
        if (state.repoUrl.trim() === '') {
          state.error = 'Repository URL gerekli';
          state.focusIndex = FIELD.REPO;
          draw(false);
          return;
        }
        const url = state.repoUrl.trim();
        if (
          !url.includes('github.com') &&
          !url.includes('gitlab.com') &&
          !url.includes('bitbucket.org')
        ) {
          state.error = 'Geçerli bir Git URL girin';
          state.focusIndex = FIELD.REPO;
          draw(false);
          return;
        }
        if (state.hasToken && state.token !== '') {
          setGithubToken(state.token);
        }
        // Persist color theme to config
        const selectedColor = COLOR_OPTIONS[state.colorIndex].value;
        const cfg = loadConfig();
        cfg.colorTheme = selectedColor;
        saveConfig(cfg);

        // Support multiple repos separated by comma
        const urls = url
          .split(',')
          .map((u) => u.trim())
          .filter((u) => u !== '');

        done({
          token: state.hasToken && state.token !== '' ? state.token : null,
          repoUrl: urls[0],
          repoUrls: urls,
          layout: LAYOUTS[state.layoutIndex].value,
          paneCount: PANE_OPTIONS[state.panesIndex],
          cleanup: CLEANUP_OPTIONS[state.cleanupIndex].value,
          colorTheme: selectedColor,
        });
        return;
      }
      draw(false);
    }

    draw(false);
  });
}

/* ═══════════════════════════════════════════════════════
   BRANCH SELECTION FORM (per-pane)
   ═══════════════════════════════════════════════════════ */

export interface BranchSelectionResult {
  branches: string[];
  paneNames: string[];
  startupCommands?: string[];
}

const RANDOM_NAMES = [
  'Alpha',
  'Beta',
  'Gamma',
  'Delta',
  'Epsilon',
  'Zeta',
  'Nova',
  'Orion',
  'Vega',
  'Atlas',
  'Comet',
  'Pulsar',
  'Spark',
  'Blaze',
  'Storm',
  'Frost',
  'Lunar',
  'Solar',
];

function pickRandomNames(count: number): string[] {
  const shuffled = [...RANDOM_NAMES].sort(() => Math.random() - 0.5);
  return shuffled.slice(0, count);
}

interface BranchFormState {
  focusIndex: number; // 0..paneCount-1 = pane rows, paneCount = submit
  branchIndices: number[]; // selected branch index per pane
  paneNames: string[]; // custom name per pane
  startupCommands: string[]; // startup command per pane
  editing: boolean; // editing pane name
  editingCommand: boolean; // editing startup command
  editBuffer: string;
  error: string;
}

function renderBranchForm(
  state: BranchFormState,
  branches: string[],
  paneCount: number,
  pal: ColorPalette
): string {
  const W = 62;
  const lines: string[] = [];
  const submitIdx = paneCount;

  lines.push(boxTop(' Branch Seçimi ', W, pal));
  lines.push(boxLine('  ' + chalk.dim('←→ Branch  N İsim  C Komut'), W));
  lines.push(boxMid(W));
  lines.push(boxLine('', W));

  // Count how many times each branch is used to show duplicate hint
  const usageCount = new Map<number, number>();
  for (const bi of state.branchIndices) {
    usageCount.set(bi, (usageCount.get(bi) ?? 0) + 1);
  }

  for (let i = 0; i < paneCount; i++) {
    const focused = state.focusIndex === i;
    const ptr = focused ? pal.primary('❯') : ' ';

    // If editing this pane's name
    if (focused && state.editing) {
      const editLabel = pal.primaryBold('İsim: ');
      const cursor = pal.primary(state.editBuffer + '█');
      lines.push(boxLine(`  ${ptr} ${editLabel}${cursor}`, W));
      continue;
    }

    // If editing startup command
    if (focused && state.editingCommand) {
      const editLabel = pal.primaryBold('Cmd:  ');
      const cursor = pal.primary(state.editBuffer + '█');
      lines.push(boxLine(`  ${ptr} ${editLabel}${cursor}`, W));
      continue;
    }

    // Name | Branch on one line
    const name = state.paneNames[i];
    const nameDisplay = focused ? pal.primaryBold(name.padEnd(10)) : chalk.white(name.padEnd(10));
    const branchName = branches[state.branchIndices[i]];
    const shortBranch = branchName.length > 22 ? '...' + branchName.slice(-19) : branchName;
    const isDuplicate = (usageCount.get(state.branchIndices[i]) ?? 0) > 1;
    const dupHint = isDuplicate ? chalk.yellow(' +fork') : '';
    const cmdHint = state.startupCommands[i] !== '' ? chalk.dim(' $') : '';
    const branchDisplay = selectDisplay(shortBranch, focused, pal) + dupHint + cmdHint;
    lines.push(boxLine(`  ${ptr} ${nameDisplay} ${chalk.dim('│')} ${branchDisplay}`, W));
  }

  lines.push(boxLine('', W));

  if (state.error !== '') {
    lines.push(boxLine('  ' + chalk.red('⚠ ' + state.error), W));
    lines.push(boxLine('', W));
  }

  lines.push(renderButton('ONAYLA', state.focusIndex === submitIdx, W, pal));
  lines.push(boxLine('', W));
  lines.push(boxMid(W));
  const help =
    state.editing || state.editingCommand
      ? 'Yazın...  Enter Onayla  Esc İptal  Ctrl+U Temizle'
      : '↑↓ Gezin  ←→ Branch  N İsim  C Komut  Enter Onayla  Esc Çıkış';
  lines.push(boxLine('  ' + chalk.dim(help), W));
  lines.push(boxBottom(W));

  return lines.join('\n');
}

export async function showBranchSelection(
  availableBranches: string[],
  paneCount: number
): Promise<BranchSelectionResult | null> {
  const submitIdx = paneCount;

  // Assign initial branches: each pane gets a different branch
  const initialIndices: number[] = [];
  for (let i = 0; i < paneCount; i++) {
    initialIndices.push(i % availableBranches.length);
  }

  const randomNames = pickRandomNames(paneCount);

  const state: BranchFormState = {
    focusIndex: 0,
    branchIndices: initialIndices,
    paneNames: randomNames,
    startupCommands: Array.from({ length: paneCount }, () => ''),
    editing: false,
    editingCommand: false,
    editBuffer: '',
    error: '',
  };

  const pal = getPalette(loadConfig().colorTheme);

  return new Promise<BranchSelectionResult | null>((resolve) => {
    const draw = createDrawFn(() => renderBranchForm(state, availableBranches, paneCount, pal));
    const { teardown } = attachKeypress((str, key) => {
      state.error = '';

      // Name editing mode
      if (state.editing) {
        if (key.name === 'return') {
          const val = state.editBuffer.trim();
          state.paneNames[state.focusIndex] = val !== '' ? val : randomNames[state.focusIndex];
          state.editing = false;
          draw(false);
          return;
        }
        if (key.name === 'escape') {
          state.editing = false;
          draw(false);
          return;
        }
        if (key.name === 'backspace') {
          state.editBuffer = state.editBuffer.slice(0, -1);
          draw(true);
          return;
        }
        if (key.ctrl === true && key.name === 'u') {
          state.editBuffer = '';
          draw(true);
          return;
        }
        if (str !== undefined && str !== '' && key.ctrl !== true && key.meta !== true) {
          state.editBuffer += str;
          draw(true);
        }
        return;
      }

      // Command editing mode
      if (state.editingCommand) {
        if (key.name === 'return') {
          state.startupCommands[state.focusIndex] = state.editBuffer.trim();
          state.editingCommand = false;
          draw(false);
          return;
        }
        if (key.name === 'escape') {
          state.editingCommand = false;
          draw(false);
          return;
        }
        if (key.name === 'backspace') {
          state.editBuffer = state.editBuffer.slice(0, -1);
          draw(true);
          return;
        }
        if (key.ctrl === true && key.name === 'u') {
          state.editBuffer = '';
          draw(true);
          return;
        }
        if (str !== undefined && str !== '' && key.ctrl !== true && key.meta !== true) {
          state.editBuffer += str;
          draw(true);
        }
        return;
      }

      if (key.name === 'escape') {
        teardown();
        console.clear();
        resolve(null);
        return;
      }

      // Navigation
      if (key.name === 'up' || (key.name === 'tab' && key.shift === true)) {
        if (state.focusIndex > 0) state.focusIndex--;
        draw(false);
        return;
      }
      if (key.name === 'down' || key.name === 'tab') {
        if (state.focusIndex < submitIdx) state.focusIndex++;
        draw(false);
        return;
      }

      // N key → edit name
      if ((str === 'n' || str === 'N') && state.focusIndex < paneCount) {
        state.editing = true;
        state.editBuffer = state.paneNames[state.focusIndex];
        draw(true);
        return;
      }

      // C key → edit startup command
      if ((str === 'c' || str === 'C') && state.focusIndex < paneCount) {
        state.editingCommand = true;
        state.editBuffer = state.startupCommands[state.focusIndex];
        draw(true);
        return;
      }

      // ←→ cycle branch
      if (key.name === 'left' || key.name === 'right') {
        if (state.focusIndex < paneCount) {
          const d = key.name === 'right' ? 1 : -1;
          const cur = state.branchIndices[state.focusIndex];
          state.branchIndices[state.focusIndex] =
            (cur + d + availableBranches.length) % availableBranches.length;
        }
        draw(false);
        return;
      }

      if (key.name === 'space' && state.focusIndex < paneCount) {
        const cur = state.branchIndices[state.focusIndex];
        state.branchIndices[state.focusIndex] = (cur + 1) % availableBranches.length;
        draw(false);
        return;
      }

      // Enter
      if (key.name === 'return') {
        if (state.focusIndex === submitIdx) {
          const selected = state.branchIndices.map((bi) => availableBranches[bi]);
          teardown();
          console.clear();
          resolve({
            branches: selected,
            paneNames: [...state.paneNames],
            startupCommands: [...state.startupCommands],
          });
          return;
        }
        // On a pane row, Enter cycles branch forward
        if (state.focusIndex < paneCount) {
          const cur = state.branchIndices[state.focusIndex];
          state.branchIndices[state.focusIndex] = (cur + 1) % availableBranches.length;
          draw(false);
        }
      }
    });

    draw(false);
  });
}

/* ── Other exports (unchanged) ────────────────────────── */

export function showPreview(data: {
  repoUrl: string;
  layout: string;
  branchCount: number;
  branches: string[];
  cleanup: string;
}): void {
  console.log();
  console.log(chalk.dim('─'.repeat(50)));
  console.log(chalk.bold('📋 ÖNİZLEME'));
  console.log(chalk.dim('─'.repeat(50)));
  console.log();
  console.log(formatPreview('Repo', data.repoUrl));
  console.log(formatPreview('Layout', data.layout.toUpperCase()));
  console.log(formatPreview('Branches', `${data.branchCount} adet`));
  data.branches.forEach((b, i) => {
    console.log(chalk.dim(`   ${i + 1}. ${b}`));
  });
  console.log(formatPreview('Cleanup', data.cleanup === 'session' ? 'Session' : 'Persistent'));
  console.log();
}

export async function confirmStart(): Promise<boolean> {
  const confirm = await p.confirm({
    message: 'Başlatmak için onayla',
    initialValue: true,
  });

  return confirm === true;
}

export function showProgress(steps: string[]): void {
  const s = p.spinner();

  for (const step of steps) {
    s.start(step);
  }
}

export function showSuccess(message: string): void {
  p.outro(chalk.green('✓ ') + message);
}

export function showError(message: string, hint?: string): void {
  console.log();
  console.log(chalk.red('✕ ') + message);
  if (hint !== undefined && hint !== '') {
    console.log(chalk.dim('  → ' + hint));
  }
}

export function showInfo(message: string): void {
  p.log.info(message);
}
