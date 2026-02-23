import chalk from 'chalk';
import {
  savePreset,
  loadPresets,
  applyPreset,
  deletePreset,
  renamePreset,
  presetExists,
  createPresetFromCurrentConfig,
} from '../core/presets.js';
import { type PresetConfig } from '../types/index.js';

export function presetCommand(
  action?: string,
  name?: string,
  extra?: string
): void {
  switch (action) {
    case 'list': {
      const presets = loadPresets();
      const entries = Object.entries(presets);

      if (entries.length === 0) {
        console.log(chalk.yellow('\nKayıtlı preset bulunamadı.\n'));
        console.log(chalk.dim('Yeni preset: branchnexus preset save <isim>'));
        console.log();
        return;
      }

      console.log(chalk.bold('\n📋 Preset Listesi\n'));

      for (const [presetName, preset] of entries) {
        const p = preset;
        console.log(
          chalk.cyan(`  ${presetName}`) +
            chalk.dim(` — layout: ${p.layout}, panes: ${p.panes}, cleanup: ${p.cleanup}`)
        );
      }
      console.log();
      break;
    }

    case 'save': {
      if (name === undefined || name === '') {
        console.error(chalk.red('Kullanım: branchnexus preset save <isim>'));
        process.exit(1);
      }

      if (extra !== undefined && extra !== '') {
        // Parse inline: branchnexus preset save myPreset '{"layout":"grid","panes":4,"cleanup":"session"}'
        try {
          const parsed = JSON.parse(extra) as PresetConfig;
          savePreset(name, parsed);
          console.log(chalk.green(`\n✓ Preset "${name}" kaydedildi.\n`));
        } catch (error) {
          const msg = error instanceof Error ? error.message : String(error);
          console.error(chalk.red(`\nGeçersiz preset verisi: ${msg}\n`));
          process.exit(1);
        }
      } else {
        // Create from current config defaults
        const preset = createPresetFromCurrentConfig(name);
        console.log(chalk.green(`\n✓ Preset "${name}" mevcut ayarlardan oluşturuldu.`));
        console.log(
          chalk.dim(`  layout: ${preset.layout}, panes: ${preset.panes}, cleanup: ${preset.cleanup}`)
        );
        console.log();
      }
      break;
    }

    case 'load': {
      if (name === undefined || name === '') {
        console.error(chalk.red('Kullanım: branchnexus preset load <isim>'));
        process.exit(1);
      }

      try {
        const preset = applyPreset(name);
        console.log(chalk.green(`\n✓ Preset "${name}" yüklendi.`));
        console.log(
          chalk.dim(`  layout: ${preset.layout}, panes: ${preset.panes}, cleanup: ${preset.cleanup}`)
        );
        console.log();
      } catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        console.error(chalk.red(`\n${msg}\n`));
        process.exit(1);
      }
      break;
    }

    case 'delete': {
      if (name === undefined || name === '') {
        console.error(chalk.red('Kullanım: branchnexus preset delete <isim>'));
        process.exit(1);
      }

      if (!presetExists(name)) {
        console.error(chalk.red(`\nPreset "${name}" bulunamadı.\n`));
        process.exit(1);
      }

      deletePreset(name);
      console.log(chalk.green(`\n✓ Preset "${name}" silindi.\n`));
      break;
    }

    case 'rename': {
      if (name === undefined || name === '' || extra === undefined || extra === '') {
        console.error(chalk.red('Kullanım: branchnexus preset rename <eski-isim> <yeni-isim>'));
        process.exit(1);
      }

      try {
        renamePreset(name, extra);
        console.log(chalk.green(`\n✓ Preset "${name}" → "${extra}" olarak yeniden adlandırıldı.\n`));
      } catch (error) {
        const msg = error instanceof Error ? error.message : String(error);
        console.error(chalk.red(`\n${msg}\n`));
        process.exit(1);
      }
      break;
    }

    default:
      console.log(chalk.bold('\n📋 Preset Komutları\n'));
      console.log('  branchnexus preset list              Kayıtlı preset\'leri listele');
      console.log('  branchnexus preset save <isim>       Mevcut ayarlardan preset kaydet');
      console.log('  branchnexus preset load <isim>       Preset yükle');
      console.log('  branchnexus preset delete <isim>     Preset sil');
      console.log('  branchnexus preset rename <eski> <yeni>  Preset yeniden adlandır');
      console.log();
  }
}
