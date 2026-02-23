import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { AppConfig } from '../../ts-src/types/config.js';
import { ExitCode, BranchNexusError } from '../../ts-src/types/errors.js';

const DEFAULT_MOCK_CONFIG: AppConfig = {
  defaultRoot: '',
  remoteRepoUrl: '',
  githubToken: '',
  githubRepositoriesCache: [],
  githubBranchesCache: {},
  defaultLayout: 'grid',
  defaultPanes: 4,
  cleanupPolicy: 'session',
  tmuxAutoInstall: true,
  wslDistribution: '',
  terminalDefaultRuntime: 'wsl',
  terminalMaxCount: 16,
  sessionRestoreEnabled: true,
  lastSession: {},
  colorTheme: 'cyan',
  presets: {},
  commandHooks: {},
};

let mockConfig: AppConfig;

vi.mock('../../ts-src/core/config.js', () => ({
  loadConfig: vi.fn(() => mockConfig),
  saveConfig: vi.fn((config: AppConfig) => {
    mockConfig = config;
  }),
}));

import {
  TERMINAL_TEMPLATE_CATALOG,
  TERMINAL_TEMPLATE_MIN,
  TERMINAL_TEMPLATE_MAX,
  TERMINAL_TEMPLATE_CUSTOM,
  terminalTemplateChoices,
  validateTerminalCount,
  resolveTerminalTemplate,
  savePreset,
  loadPresets,
  applyPreset,
  deletePreset,
  renamePreset,
  presetExists,
  createPresetFromCurrentConfig,
} from '../../ts-src/core/presets.js';

beforeEach(() => {
  mockConfig = structuredClone(DEFAULT_MOCK_CONFIG);
});

describe('presets', () => {
  describe('constants', () => {
    it('should export the correct terminal template catalog', () => {
      expect(TERMINAL_TEMPLATE_CATALOG).toEqual([2, 4, 6, 8, 12, 16]);
    });

    it('should export the correct min and max', () => {
      expect(TERMINAL_TEMPLATE_MIN).toBe(2);
      expect(TERMINAL_TEMPLATE_MAX).toBe(16);
    });

    it('should export the custom sentinel value', () => {
      expect(TERMINAL_TEMPLATE_CUSTOM).toBe('custom');
    });
  });

  describe('terminalTemplateChoices', () => {
    it('should return catalog values as strings plus custom', () => {
      expect(terminalTemplateChoices()).toEqual(['2', '4', '6', '8', '12', '16', 'custom']);
    });

    it('should return a new array each time', () => {
      const a = terminalTemplateChoices();
      const b = terminalTemplateChoices();
      expect(a).not.toBe(b);
      expect(a).toEqual(b);
    });
  });

  describe('validateTerminalCount', () => {
    it('should accept the minimum value (2)', () => {
      expect(validateTerminalCount(2)).toBe(2);
    });

    it('should accept a mid-range value (8)', () => {
      expect(validateTerminalCount(8)).toBe(8);
    });

    it('should accept the maximum value (16)', () => {
      expect(validateTerminalCount(16)).toBe(16);
    });

    it('should accept values not in the catalog but within range', () => {
      expect(validateTerminalCount(3)).toBe(3);
      expect(validateTerminalCount(10)).toBe(10);
      expect(validateTerminalCount(15)).toBe(15);
    });

    it('should throw for 0', () => {
      expect(() => validateTerminalCount(0)).toThrow(BranchNexusError);
    });

    it('should throw for 1', () => {
      expect(() => validateTerminalCount(1)).toThrow(BranchNexusError);
    });

    it('should throw for 17', () => {
      expect(() => validateTerminalCount(17)).toThrow(BranchNexusError);
    });

    it('should throw for negative numbers', () => {
      expect(() => validateTerminalCount(-1)).toThrow(BranchNexusError);
    });

    it('should throw with VALIDATION_ERROR exit code', () => {
      try {
        validateTerminalCount(0);
        expect.unreachable('should have thrown');
      } catch (error) {
        expect(error).toBeInstanceOf(BranchNexusError);
        expect((error as BranchNexusError).code).toBe(ExitCode.VALIDATION_ERROR);
      }
    });

    it('should include the invalid value in the error message', () => {
      try {
        validateTerminalCount(99);
        expect.unreachable('should have thrown');
      } catch (error) {
        expect((error as BranchNexusError).message).toContain('99');
      }
    });

    it('should include a hint about valid range', () => {
      try {
        validateTerminalCount(0);
        expect.unreachable('should have thrown');
      } catch (error) {
        const hint = (error as BranchNexusError).hint;
        expect(hint).toContain('2');
        expect(hint).toContain('16');
      }
    });
  });

  describe('resolveTerminalTemplate', () => {
    describe('number input', () => {
      it('should return valid numbers directly', () => {
        expect(resolveTerminalTemplate(4)).toBe(4);
        expect(resolveTerminalTemplate(2)).toBe(2);
        expect(resolveTerminalTemplate(16)).toBe(16);
      });

      it('should throw for out-of-range numbers', () => {
        expect(() => resolveTerminalTemplate(0)).toThrow(BranchNexusError);
        expect(() => resolveTerminalTemplate(1)).toThrow(BranchNexusError);
        expect(() => resolveTerminalTemplate(17)).toThrow(BranchNexusError);
      });
    });

    describe('custom template', () => {
      it('should use customValue when template is "custom"', () => {
        expect(resolveTerminalTemplate('custom', 6)).toBe(6);
      });

      it('should validate the customValue', () => {
        expect(() => resolveTerminalTemplate('custom', 0)).toThrow(BranchNexusError);
        expect(() => resolveTerminalTemplate('custom', 20)).toThrow(BranchNexusError);
      });

      it('should throw when customValue is undefined for "custom"', () => {
        expect(() => resolveTerminalTemplate('custom')).toThrow(BranchNexusError);
      });

      it('should throw with VALIDATION_ERROR for missing customValue', () => {
        try {
          resolveTerminalTemplate('custom');
          expect.unreachable('should have thrown');
        } catch (error) {
          expect((error as BranchNexusError).code).toBe(ExitCode.VALIDATION_ERROR);
          expect((error as BranchNexusError).message).toContain('Custom template');
        }
      });

      it('should handle case-insensitive "Custom"', () => {
        expect(resolveTerminalTemplate('Custom', 8)).toBe(8);
      });

      it('should handle "CUSTOM" with uppercase', () => {
        expect(resolveTerminalTemplate('CUSTOM', 4)).toBe(4);
      });

      it('should handle "custom" with leading/trailing whitespace', () => {
        expect(resolveTerminalTemplate('  custom  ', 10)).toBe(10);
      });
    });

    describe('numeric string input', () => {
      it('should parse and validate numeric strings', () => {
        expect(resolveTerminalTemplate('4')).toBe(4);
        expect(resolveTerminalTemplate('12')).toBe(12);
        expect(resolveTerminalTemplate('2')).toBe(2);
        expect(resolveTerminalTemplate('16')).toBe(16);
      });

      it('should throw for out-of-range numeric strings', () => {
        expect(() => resolveTerminalTemplate('0')).toThrow(BranchNexusError);
        expect(() => resolveTerminalTemplate('1')).toThrow(BranchNexusError);
        expect(() => resolveTerminalTemplate('17')).toThrow(BranchNexusError);
      });
    });

    describe('invalid string input', () => {
      it('should throw for non-numeric, non-custom strings', () => {
        expect(() => resolveTerminalTemplate('abc')).toThrow(BranchNexusError);
      });

      it('should throw with VALIDATION_ERROR for invalid strings', () => {
        try {
          resolveTerminalTemplate('notvalid');
          expect.unreachable('should have thrown');
        } catch (error) {
          expect((error as BranchNexusError).code).toBe(ExitCode.VALIDATION_ERROR);
          expect((error as BranchNexusError).message).toContain('notvalid');
        }
      });

      it('should include available choices in the hint', () => {
        try {
          resolveTerminalTemplate('invalid');
          expect.unreachable('should have thrown');
        } catch (error) {
          const hint = (error as BranchNexusError).hint;
          expect(hint).toContain('custom');
          expect(hint).toContain('2');
          expect(hint).toContain('16');
        }
      });

      it('should throw for empty string', () => {
        expect(() => resolveTerminalTemplate('')).toThrow(BranchNexusError);
      });

      it('should throw for whitespace-only string', () => {
        expect(() => resolveTerminalTemplate('   ')).toThrow(BranchNexusError);
      });
    });
  });

  describe('savePreset', () => {
    it('should save a valid preset', () => {
      savePreset('myPreset', { layout: 'horizontal', panes: 3, cleanup: 'session' });
      expect(mockConfig.presets['myPreset']).toEqual({
        layout: 'horizontal',
        panes: 3,
        cleanup: 'session',
      });
    });

    it('should overwrite an existing preset with the same name', () => {
      savePreset('dup', { layout: 'grid', panes: 4, cleanup: 'session' });
      savePreset('dup', { layout: 'vertical', panes: 2, cleanup: 'persistent' });
      expect(mockConfig.presets['dup']).toEqual({
        layout: 'vertical',
        panes: 2,
        cleanup: 'persistent',
      });
    });

    it('should reject a preset with invalid panes', () => {
      expect(() => savePreset('bad', { layout: 'grid', panes: 1, cleanup: 'session' })).toThrow();
    });

    it('should reject a preset with invalid layout', () => {
      expect(() =>
        savePreset('bad', { layout: 'diagonal' as 'grid', panes: 4, cleanup: 'session' })
      ).toThrow();
    });
  });

  describe('loadPresets', () => {
    it('should return an empty object when no presets exist', () => {
      expect(loadPresets()).toEqual({});
    });

    it('should return a copy of saved presets', () => {
      const preset = { layout: 'grid' as const, panes: 4, cleanup: 'session' as const };
      savePreset('first', preset);
      const presets = loadPresets();
      expect(presets['first']).toEqual(preset);
    });

    it('should return a shallow copy (not the original reference)', () => {
      savePreset('test', { layout: 'grid', panes: 4, cleanup: 'session' });
      const a = loadPresets();
      const b = loadPresets();
      expect(a).not.toBe(b);
      expect(a).toEqual(b);
    });
  });

  describe('applyPreset', () => {
    it('should return the preset for an existing name', () => {
      const preset = { layout: 'vertical' as const, panes: 3, cleanup: 'persistent' as const };
      savePreset('myPreset', preset);
      expect(applyPreset('myPreset')).toEqual(preset);
    });

    it('should throw BranchNexusError for a non-existent preset', () => {
      expect(() => applyPreset('doesNotExist')).toThrow(BranchNexusError);
    });

    it('should throw with VALIDATION_ERROR exit code for missing preset', () => {
      try {
        applyPreset('ghost');
        expect.unreachable('should have thrown');
      } catch (error) {
        expect((error as BranchNexusError).code).toBe(ExitCode.VALIDATION_ERROR);
        expect((error as BranchNexusError).message).toContain('ghost');
      }
    });

    it('should include a helpful hint for missing presets', () => {
      try {
        applyPreset('missing');
        expect.unreachable('should have thrown');
      } catch (error) {
        expect((error as BranchNexusError).hint).toBeTruthy();
      }
    });
  });

  describe('deletePreset', () => {
    it('should remove an existing preset', () => {
      savePreset('toDelete', { layout: 'grid', panes: 4, cleanup: 'session' });
      expect(presetExists('toDelete')).toBe(true);
      deletePreset('toDelete');
      expect(presetExists('toDelete')).toBe(false);
    });

    it('should not throw when deleting a non-existent preset', () => {
      expect(() => deletePreset('nonExistent')).not.toThrow();
    });

    it('should not affect other presets', () => {
      savePreset('keep', { layout: 'grid', panes: 4, cleanup: 'session' });
      savePreset('remove', { layout: 'vertical', panes: 2, cleanup: 'persistent' });
      deletePreset('remove');
      expect(presetExists('keep')).toBe(true);
      expect(presetExists('remove')).toBe(false);
    });
  });

  describe('renamePreset', () => {
    it('should rename an existing preset', () => {
      const preset = { layout: 'horizontal' as const, panes: 3, cleanup: 'session' as const };
      savePreset('oldName', preset);
      renamePreset('oldName', 'newName');
      expect(presetExists('oldName')).toBe(false);
      expect(presetExists('newName')).toBe(true);
      expect(applyPreset('newName')).toEqual(preset);
    });

    it('should throw BranchNexusError when renaming a non-existent preset', () => {
      expect(() => renamePreset('noSuchPreset', 'newName')).toThrow(BranchNexusError);
    });

    it('should throw with VALIDATION_ERROR exit code for missing source', () => {
      try {
        renamePreset('missing', 'target');
        expect.unreachable('should have thrown');
      } catch (error) {
        expect((error as BranchNexusError).code).toBe(ExitCode.VALIDATION_ERROR);
        expect((error as BranchNexusError).message).toContain('missing');
      }
    });

    it('should include a hint when source preset is not found', () => {
      try {
        renamePreset('gone', 'new');
        expect.unreachable('should have thrown');
      } catch (error) {
        expect((error as BranchNexusError).hint).toBeTruthy();
      }
    });

    it('should preserve the preset data after renaming', () => {
      const preset = { layout: 'grid' as const, panes: 6, cleanup: 'persistent' as const };
      savePreset('alpha', preset);
      renamePreset('alpha', 'beta');
      const loaded = applyPreset('beta');
      expect(loaded.layout).toBe('grid');
      expect(loaded.panes).toBe(6);
      expect(loaded.cleanup).toBe('persistent');
    });
  });

  describe('presetExists', () => {
    it('should return false for non-existent preset', () => {
      expect(presetExists('nope')).toBe(false);
    });

    it('should return true for existing preset', () => {
      savePreset('exists', { layout: 'grid', panes: 4, cleanup: 'session' });
      expect(presetExists('exists')).toBe(true);
    });

    it('should return false after deleting a preset', () => {
      savePreset('temp', { layout: 'grid', panes: 4, cleanup: 'session' });
      deletePreset('temp');
      expect(presetExists('temp')).toBe(false);
    });
  });

  describe('createPresetFromCurrentConfig', () => {
    it('should create a preset from the current config defaults', () => {
      const preset = createPresetFromCurrentConfig('fromConfig');
      expect(preset).toEqual({
        layout: 'grid',
        panes: 4,
        cleanup: 'session',
      });
    });

    it('should save the created preset so it can be loaded later', () => {
      createPresetFromCurrentConfig('saved');
      expect(presetExists('saved')).toBe(true);
      expect(applyPreset('saved')).toEqual({
        layout: 'grid',
        panes: 4,
        cleanup: 'session',
      });
    });

    it('should reflect custom config values', () => {
      mockConfig.defaultLayout = 'vertical';
      mockConfig.defaultPanes = 2;
      mockConfig.cleanupPolicy = 'persistent';
      const preset = createPresetFromCurrentConfig('custom');
      expect(preset).toEqual({
        layout: 'vertical',
        panes: 2,
        cleanup: 'persistent',
      });
    });

    it('should reflect horizontal layout from config', () => {
      mockConfig.defaultLayout = 'horizontal';
      mockConfig.defaultPanes = 6;
      mockConfig.cleanupPolicy = 'session';
      const preset = createPresetFromCurrentConfig('horiz');
      expect(preset.layout).toBe('horizontal');
      expect(preset.panes).toBe(6);
      expect(preset.cleanup).toBe('session');
    });
  });

  describe('round-trip integration', () => {
    it('should support a full save-load-apply-rename-delete lifecycle', () => {
      const preset = { layout: 'grid' as const, panes: 4, cleanup: 'session' as const };

      // Save
      savePreset('lifecycle', preset);
      expect(presetExists('lifecycle')).toBe(true);

      // Load
      const allPresets = loadPresets();
      expect(allPresets['lifecycle']).toEqual(preset);

      // Apply
      const applied = applyPreset('lifecycle');
      expect(applied).toEqual(preset);

      // Rename
      renamePreset('lifecycle', 'renamed');
      expect(presetExists('lifecycle')).toBe(false);
      expect(presetExists('renamed')).toBe(true);
      expect(applyPreset('renamed')).toEqual(preset);

      // Delete
      deletePreset('renamed');
      expect(presetExists('renamed')).toBe(false);
      expect(loadPresets()).toEqual({});
    });

    it('should support multiple presets simultaneously', () => {
      savePreset('a', { layout: 'grid', panes: 4, cleanup: 'session' });
      savePreset('b', { layout: 'vertical', panes: 2, cleanup: 'persistent' });
      savePreset('c', { layout: 'horizontal', panes: 6, cleanup: 'session' });

      const all = loadPresets();
      expect(Object.keys(all)).toHaveLength(3);
      expect(all['a']?.layout).toBe('grid');
      expect(all['b']?.layout).toBe('vertical');
      expect(all['c']?.layout).toBe('horizontal');

      deletePreset('b');
      const remaining = loadPresets();
      expect(Object.keys(remaining)).toHaveLength(2);
      expect(remaining['b']).toBeUndefined();
    });
  });
});
