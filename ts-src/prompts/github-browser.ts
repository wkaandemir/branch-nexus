import * as readline from 'node:readline';
import chalk from 'chalk';
import { GitHubClient, type GitHubRepo } from '../github/api.js';
import { loadConfig } from '../core/config.js';
import { updateGithubRepoCache } from '../core/config.js';
import { type ColorPalette, getPalette } from '../utils/theme.js';

interface KeypressKey {
  name?: string;
  ctrl?: boolean;
  meta?: boolean;
  shift?: boolean;
}

/* eslint-disable no-control-regex */
const ANSI_RE =
  /[\u001B\u009B][[\]()#;?]*(?:(?:(?:[a-zA-Z\d]*(?:;[-a-zA-Z\d/#&.:=?%@~_]*)*)?\u0007)|(?:(?:\d{1,4}(?:;\d{0,4})*)?[\dA-PR-TZcf-nq-uy=><~]))/g;
/* eslint-enable no-control-regex */
const CLR = '\x1B[K';

function stripAnsi(str: string): number {
  return str.replace(ANSI_RE, '').length;
}

function padToWidth(content: string, width: number): string {
  const pad = Math.max(0, width - stripAnsi(content));
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

export interface GitHubBrowserResult {
  cloneUrl: string;
  fullName: string;
}

interface BrowserState {
  repos: GitHubRepo[];
  filteredRepos: GitHubRepo[];
  selectedIndex: number;
  scrollOffset: number;
  filterText: string;
  filtering: boolean;
  loading: boolean;
  error: string;
}

const MAX_VISIBLE = 12;

function renderBrowser(state: BrowserState, pal: ColorPalette): string {
  const W = 62;
  const lines: string[] = [];

  lines.push(boxTop(' GitHub Repositories ', W, pal));

  if (state.loading) {
    lines.push(boxLine('', W));
    lines.push(boxLine('  ' + chalk.dim('Yükleniyor...'), W));
    lines.push(boxLine('', W));
    lines.push(boxBottom(W));
    return lines.join('\n');
  }

  if (state.error !== '') {
    lines.push(boxLine('', W));
    lines.push(boxLine('  ' + chalk.red(state.error), W));
    lines.push(boxLine('', W));
    lines.push(boxBottom(W));
    return lines.join('\n');
  }

  // Filter bar
  if (state.filtering) {
    const cursor = pal.primary(state.filterText + '█');
    lines.push(boxLine('  ' + chalk.dim('Filtre: ') + cursor, W));
  } else if (state.filterText !== '') {
    lines.push(boxLine('  ' + chalk.dim('Filtre: ') + chalk.white(state.filterText), W));
  }
  lines.push(boxMid(W));

  // Repo list
  const repos = state.filteredRepos;
  if (repos.length === 0) {
    lines.push(boxLine('', W));
    lines.push(boxLine('  ' + chalk.dim('Eşleşen repo bulunamadı'), W));
    lines.push(boxLine('', W));
  } else {
    const start = state.scrollOffset;
    const end = Math.min(start + MAX_VISIBLE, repos.length);

    if (start > 0) {
      lines.push(boxLine('  ' + chalk.dim(`  ↑ ${start} daha...`), W));
    }

    for (let i = start; i < end; i++) {
      const focused = i === state.selectedIndex;
      const ptr = focused ? pal.primary('❯') : ' ';
      const name = repos[i].fullName;
      const display = name.length > 50 ? '...' + name.slice(-47) : name;
      const label = focused ? pal.primaryBold(display) : chalk.white(display);
      lines.push(boxLine(`  ${ptr} ${label}`, W));
    }

    if (end < repos.length) {
      lines.push(boxLine('  ' + chalk.dim(`  ↓ ${repos.length - end} daha...`), W));
    }
  }

  lines.push(boxLine('', W));
  lines.push(boxMid(W));
  const count = chalk.dim(`${repos.length} repo`);
  const help = state.filtering
    ? 'Yazın...  Enter Onayla  Esc İptal'
    : '↑↓ Gezin  / Filtrele  Enter Seç  Esc Çıkış';
  lines.push(boxLine('  ' + chalk.dim(help) + '  ' + count, W));
  lines.push(boxBottom(W));

  return lines.join('\n');
}

export async function showGitHubBrowser(token: string): Promise<GitHubBrowserResult | null> {
  const config = loadConfig();
  const pal = getPalette(config.colorTheme);

  const state: BrowserState = {
    repos: [],
    filteredRepos: [],
    selectedIndex: 0,
    scrollOffset: 0,
    filterText: '',
    filtering: false,
    loading: true,
    error: '',
  };

  return new Promise<GitHubBrowserResult | null>((resolve) => {
    let first = true;

    function draw(): void {
      process.stdout.write(first ? '\x1B[2J\x1B[H' : '\x1B[H');
      first = false;
      process.stdout.write(state.filtering ? '\x1B[?25h' : '\x1B[?25l');
      process.stdout.write(renderBrowser(state, pal) + '\x1B[J\n');
    }

    readline.emitKeypressEvents(process.stdin);
    const wasRaw = process.stdin.isRaw ?? false;
    if (process.stdin.isTTY === true) {
      process.stdin.setRawMode(true);
    }
    process.stdin.resume();

    function teardown(): void {
      process.stdin.removeListener('keypress', onKey);
      if (process.stdin.isTTY === true) {
        process.stdin.setRawMode(wasRaw);
      }
      process.stdout.write('\x1B[?25h');
      process.stdin.pause();
    }

    function done(result: GitHubBrowserResult | null): void {
      teardown();
      console.clear();
      resolve(result);
    }

    function applyFilter(): void {
      if (state.filterText === '') {
        state.filteredRepos = [...state.repos];
      } else {
        const lower = state.filterText.toLowerCase();
        state.filteredRepos = state.repos.filter((r) => r.fullName.toLowerCase().includes(lower));
      }
      state.selectedIndex = 0;
      state.scrollOffset = 0;
    }

    function ensureVisible(): void {
      if (state.selectedIndex < state.scrollOffset) {
        state.scrollOffset = state.selectedIndex;
      }
      if (state.selectedIndex >= state.scrollOffset + MAX_VISIBLE) {
        state.scrollOffset = state.selectedIndex - MAX_VISIBLE + 1;
      }
    }

    function onKey(str: string | undefined, key: KeypressKey): void {
      if (key === undefined || key === null) return;
      if (key.ctrl === true && key.name === 'c') {
        done(null);
        return;
      }

      if (state.loading) return;

      if (state.filtering) {
        if (key.name === 'return') {
          state.filtering = false;
          draw();
          return;
        }
        if (key.name === 'escape') {
          state.filtering = false;
          state.filterText = '';
          applyFilter();
          draw();
          return;
        }
        if (key.name === 'backspace') {
          state.filterText = state.filterText.slice(0, -1);
          applyFilter();
          draw();
          return;
        }
        if (key.ctrl === true && key.name === 'u') {
          state.filterText = '';
          applyFilter();
          draw();
          return;
        }
        if (str !== undefined && str !== '' && key.ctrl !== true && key.meta !== true) {
          state.filterText += str;
          applyFilter();
          draw();
        }
        return;
      }

      if (key.name === 'escape') {
        done(null);
        return;
      }

      if (key.name === 'up') {
        if (state.selectedIndex > 0) {
          state.selectedIndex--;
          ensureVisible();
        }
        draw();
        return;
      }

      if (key.name === 'down') {
        if (state.selectedIndex < state.filteredRepos.length - 1) {
          state.selectedIndex++;
          ensureVisible();
        }
        draw();
        return;
      }

      if (str === '/') {
        state.filtering = true;
        draw();
        return;
      }

      if (key.name === 'return') {
        if (state.filteredRepos.length > 0) {
          const repo = state.filteredRepos[state.selectedIndex];
          done({ cloneUrl: repo.cloneUrl, fullName: repo.fullName });
        }
        return;
      }
    }

    process.stdin.on('keypress', onKey);
    draw();

    // Fetch repos
    const client = new GitHubClient(token);
    client
      .listRepositories()
      .then((repos) => {
        state.repos = repos;
        state.filteredRepos = [...repos];
        state.loading = false;

        // Cache repos
        updateGithubRepoCache(repos.map((r) => ({ full_name: r.fullName, clone_url: r.cloneUrl })));

        draw();
      })
      .catch((error: unknown) => {
        state.loading = false;
        state.error = error instanceof Error ? error.message : String(error);
        draw();
      });
  });
}
