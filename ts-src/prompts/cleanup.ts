import chalk from 'chalk';
import * as p from '@clack/prompts';
import { ExitChoice } from '../types/index.js';

export async function promptCleanup(dirtyPaths: string[]): Promise<ExitChoice> {
  console.log();
  console.log(chalk.yellow('⚠ Kaydedilmemiş değişiklikler tespit edildi:'));
  console.log();

  for (const path of dirtyPaths) {
    const short = path.split('/').slice(-2).join('/');
    console.log(chalk.dim(`  ● ${short}`));
  }

  console.log();

  const choice = await p.select({
    message: 'Ne yapmak istersiniz?',
    options: [
      {
        value: ExitChoice.PRESERVE,
        label: 'Koruyarak Çık',
        hint: "Dirty worktree'ler korunur, temizler silinir",
      },
      {
        value: ExitChoice.CLEAN,
        label: 'Temizleyerek Çık',
        hint: "Tüm worktree'ler silinir (değişiklikler kaybolur!)",
      },
      {
        value: ExitChoice.CANCEL,
        label: 'Vazgeç',
        hint: 'Hiçbir şey yapma',
      },
    ],
  });

  if (p.isCancel(choice)) {
    return ExitChoice.CANCEL;
  }

  return choice;
}
