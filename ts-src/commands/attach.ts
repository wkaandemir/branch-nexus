import chalk from 'chalk';
import * as p from '@clack/prompts';
import { listSessions } from '../tmux/session.js';
import { loadConfig } from '../core/config.js';
import { execa } from 'execa';

const SESSION_PREFIX = 'branchnexus';

export async function attachCommand(sessionName?: string): Promise<void> {
  const config = loadConfig();
  const distribution = config.wslDistribution || undefined;

  const allSessions = await listSessions(distribution);
  const bnSessions = allSessions.filter((s) => s.startsWith(SESSION_PREFIX));

  if (bnSessions.length === 0) {
    console.log(chalk.yellow('\nAktif BranchNexus session bulunamadı.\n'));
    console.log(chalk.dim('Yeni session başlatmak için: branchnexus'));
    console.log();
    return;
  }

  let target: string;

  if (sessionName !== undefined && sessionName !== '') {
    if (!bnSessions.includes(sessionName)) {
      console.error(chalk.red(`\nSession "${sessionName}" bulunamadı.\n`));
      console.log(chalk.dim('Aktif session\'lar:'));
      for (const s of bnSessions) {
        console.log(chalk.dim(`  - ${s}`));
      }
      console.log();
      process.exit(1);
    }
    target = sessionName;
  } else if (bnSessions.length === 1) {
    target = bnSessions[0];
  } else {
    const selected = await p.select({
      message: 'Hangi session\'a bağlanılsın?',
      options: bnSessions.map((s) => ({ value: s, label: s })),
    });

    if (p.isCancel(selected)) {
      p.cancel('İptal edildi.');
      return;
    }

    target = selected;
  }

  console.log(chalk.cyan(`\nSession "${target}" bağlanılıyor...\n`));

  try {
    await execa('tmux', ['attach-session', '-t', target], {
      stdio: 'inherit',
      timeout: 0,
    });
  } catch {
    // User detached or session ended — normal
    console.log();
    console.log(chalk.dim('tmux session devam ediyor. Tekrar bağlanmak için:'));
    console.log(chalk.cyan(`  branchnexus attach ${target}`));
    console.log();
  }
}
