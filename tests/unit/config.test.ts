import { describe, it, expect, vi, beforeEach } from 'vitest';
import { DEFAULT_CONFIG } from '../../ts-src/types/config.js';

// We test the config types and schemas directly since the config module
// relies on `conf` library which reads/writes files
describe('config types', () => {
  describe('DEFAULT_CONFIG', () => {
    it('should have all required fields', () => {
      expect(DEFAULT_CONFIG.defaultRoot).toBe('');
      expect(DEFAULT_CONFIG.remoteRepoUrl).toBe('');
      expect(DEFAULT_CONFIG.githubToken).toBe('');
      expect(DEFAULT_CONFIG.githubRepositoriesCache).toEqual([]);
      expect(DEFAULT_CONFIG.githubBranchesCache).toEqual({});
      expect(DEFAULT_CONFIG.defaultLayout).toBe('grid');
      expect(DEFAULT_CONFIG.defaultPanes).toBe(4);
      expect(DEFAULT_CONFIG.cleanupPolicy).toBe('session');
      expect(DEFAULT_CONFIG.tmuxAutoInstall).toBe(true);
      expect(DEFAULT_CONFIG.wslDistribution).toBe('');
      expect(DEFAULT_CONFIG.terminalDefaultRuntime).toBe('wsl');
      expect(DEFAULT_CONFIG.terminalMaxCount).toBe(16);
      expect(DEFAULT_CONFIG.sessionRestoreEnabled).toBe(true);
      expect(DEFAULT_CONFIG.lastSession).toEqual({});
      expect(DEFAULT_CONFIG.colorTheme).toBe('cyan');
      expect(DEFAULT_CONFIG.presets).toEqual({});
      expect(DEFAULT_CONFIG.commandHooks).toEqual({});
    });
  });
});

describe('AppConfigSchema', () => {
  let AppConfigSchema: typeof import('../../ts-src/types/config.js').AppConfigSchema;

  beforeEach(async () => {
    const mod = await import('../../ts-src/types/config.js');
    AppConfigSchema = mod.AppConfigSchema;
  });

  it('should parse valid complete config', () => {
    const result = AppConfigSchema.parse(DEFAULT_CONFIG);
    expect(result).toEqual(DEFAULT_CONFIG);
  });

  it('should apply defaults for missing fields', () => {
    const result = AppConfigSchema.parse({});
    expect(result.defaultLayout).toBe('grid');
    expect(result.defaultPanes).toBe(4);
    expect(result.cleanupPolicy).toBe('session');
    expect(result.colorTheme).toBe('cyan');
    expect(result.presets).toEqual({});
    expect(result.commandHooks).toEqual({});
  });

  it('should reject invalid layout', () => {
    expect(() => AppConfigSchema.parse({ defaultLayout: 'diagonal' })).toThrow();
  });

  it('should reject invalid pane count', () => {
    expect(() => AppConfigSchema.parse({ defaultPanes: 0 })).toThrow();
    expect(() => AppConfigSchema.parse({ defaultPanes: 7 })).toThrow();
  });

  it('should reject invalid cleanup policy', () => {
    expect(() => AppConfigSchema.parse({ cleanupPolicy: 'auto' })).toThrow();
  });

  it('should reject invalid color theme', () => {
    expect(() => AppConfigSchema.parse({ colorTheme: 'rainbow' })).toThrow();
  });

  it('should accept valid presets', () => {
    const result = AppConfigSchema.parse({
      presets: {
        myPreset: { layout: 'grid', panes: 4, cleanup: 'session' },
      },
    });
    expect(result.presets.myPreset).toEqual({
      layout: 'grid',
      panes: 4,
      cleanup: 'session',
    });
  });

  it('should reject invalid preset pane count', () => {
    expect(() =>
      AppConfigSchema.parse({
        presets: {
          bad: { layout: 'grid', panes: 1, cleanup: 'session' },
        },
      })
    ).toThrow();
  });

  it('should accept valid command hooks', () => {
    const result = AppConfigSchema.parse({
      commandHooks: {
        'post-setup': ['npm install', 'npm run dev'],
      },
    });
    expect(result.commandHooks['post-setup']).toEqual(['npm install', 'npm run dev']);
  });

  it('should accept valid terminal runtime', () => {
    const result = AppConfigSchema.parse({ terminalDefaultRuntime: 'native' });
    expect(result.terminalDefaultRuntime).toBe('native');
  });

  it('should reject invalid terminal runtime', () => {
    expect(() => AppConfigSchema.parse({ terminalDefaultRuntime: 'cmd' })).toThrow();
  });
});

describe('PresetConfigSchema', () => {
  let PresetConfigSchema: typeof import('../../ts-src/types/config.js').PresetConfigSchema;

  beforeEach(async () => {
    const mod = await import('../../ts-src/types/config.js');
    PresetConfigSchema = mod.PresetConfigSchema;
  });

  it('should parse valid preset', () => {
    const result = PresetConfigSchema.parse({ layout: 'horizontal', panes: 3, cleanup: 'persistent' });
    expect(result.layout).toBe('horizontal');
    expect(result.panes).toBe(3);
    expect(result.cleanup).toBe('persistent');
  });

  it('should reject missing fields', () => {
    expect(() => PresetConfigSchema.parse({})).toThrow();
    expect(() => PresetConfigSchema.parse({ layout: 'grid' })).toThrow();
  });

  it('should reject invalid pane count in preset', () => {
    expect(() => PresetConfigSchema.parse({ layout: 'grid', panes: 0, cleanup: 'session' })).toThrow();
    expect(() => PresetConfigSchema.parse({ layout: 'grid', panes: 7, cleanup: 'session' })).toThrow();
  });

  it('should accept boundary pane counts', () => {
    expect(PresetConfigSchema.parse({ layout: 'grid', panes: 2, cleanup: 'session' }).panes).toBe(2);
    expect(PresetConfigSchema.parse({ layout: 'grid', panes: 6, cleanup: 'session' }).panes).toBe(6);
  });
});

describe('LayoutSchema', () => {
  let LayoutSchema: typeof import('../../ts-src/types/config.js').LayoutSchema;

  beforeEach(async () => {
    const mod = await import('../../ts-src/types/config.js');
    LayoutSchema = mod.LayoutSchema;
  });

  it('should accept valid layouts', () => {
    expect(LayoutSchema.parse('horizontal')).toBe('horizontal');
    expect(LayoutSchema.parse('vertical')).toBe('vertical');
    expect(LayoutSchema.parse('grid')).toBe('grid');
  });

  it('should reject invalid layouts', () => {
    expect(() => LayoutSchema.parse('tiled')).toThrow();
    expect(() => LayoutSchema.parse('')).toThrow();
  });
});

describe('ColorThemeSchema', () => {
  let ColorThemeSchema: typeof import('../../ts-src/types/config.js').ColorThemeSchema;

  beforeEach(async () => {
    const mod = await import('../../ts-src/types/config.js');
    ColorThemeSchema = mod.ColorThemeSchema;
  });

  it('should accept all valid themes', () => {
    const themes = ['cyan', 'green', 'magenta', 'blue', 'yellow', 'red'];
    for (const t of themes) {
      expect(ColorThemeSchema.parse(t)).toBe(t);
    }
  });

  it('should reject invalid themes', () => {
    expect(() => ColorThemeSchema.parse('purple')).toThrow();
    expect(() => ColorThemeSchema.parse('orange')).toThrow();
  });
});
