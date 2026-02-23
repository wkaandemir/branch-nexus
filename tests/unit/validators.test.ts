import { describe, it, expect } from 'vitest';
import { ZodError } from 'zod';
import {
  validateConfig,
  validateLayout,
  validateCleanupPolicy,
  validatePresetConfig,
  isValidLayout,
  isValidCleanupPolicy,
  isValidPaneCount,
  isValidTerminalCount,
  sanitizePathSegment,
  normalizePath,
  posixPath,
} from '../../ts-src/utils/validators.js';

describe('validators', () => {
  describe('validateConfig', () => {
    it('should return defaults when given an empty object', () => {
      const config = validateConfig({});
      expect(config.defaultRoot).toBe('');
      expect(config.remoteRepoUrl).toBe('');
      expect(config.githubToken).toBe('');
      expect(config.githubRepositoriesCache).toEqual([]);
      expect(config.githubBranchesCache).toEqual({});
      expect(config.defaultLayout).toBe('grid');
      expect(config.defaultPanes).toBe(4);
      expect(config.cleanupPolicy).toBe('session');
      expect(config.tmuxAutoInstall).toBe(true);
      expect(config.wslDistribution).toBe('');
      expect(config.terminalDefaultRuntime).toBe('wsl');
      expect(config.terminalMaxCount).toBe(16);
      expect(config.sessionRestoreEnabled).toBe(true);
      expect(config.lastSession).toEqual({});
      expect(config.colorTheme).toBe('cyan');
      expect(config.presets).toEqual({});
      expect(config.commandHooks).toEqual({});
    });

    it('should accept a fully specified valid config', () => {
      const input = {
        defaultRoot: '/home/user/repos',
        remoteRepoUrl: 'https://github.com/user/repo.git',
        githubToken: 'ghp_abc123',
        githubRepositoriesCache: [
          { full_name: 'user/repo', clone_url: 'https://github.com/user/repo.git' },
        ],
        githubBranchesCache: { 'user/repo': ['main', 'develop'] },
        defaultLayout: 'horizontal',
        defaultPanes: 3,
        cleanupPolicy: 'persistent',
        tmuxAutoInstall: false,
        wslDistribution: 'Ubuntu',
        terminalDefaultRuntime: 'native',
        terminalMaxCount: 8,
        sessionRestoreEnabled: false,
        lastSession: { key: 'value' },
        colorTheme: 'magenta',
        presets: {
          myPreset: { layout: 'vertical', panes: 2, cleanup: 'session' },
        },
        commandHooks: { 'pre-run': ['echo hello'] },
      };
      const config = validateConfig(input);
      expect(config.defaultRoot).toBe('/home/user/repos');
      expect(config.defaultLayout).toBe('horizontal');
      expect(config.defaultPanes).toBe(3);
      expect(config.cleanupPolicy).toBe('persistent');
      expect(config.tmuxAutoInstall).toBe(false);
      expect(config.terminalDefaultRuntime).toBe('native');
      expect(config.terminalMaxCount).toBe(8);
      expect(config.colorTheme).toBe('magenta');
      expect(config.presets.myPreset).toEqual({
        layout: 'vertical',
        panes: 2,
        cleanup: 'session',
      });
    });

    it('should reject an invalid layout in config', () => {
      expect(() => validateConfig({ defaultLayout: 'diagonal' })).toThrow(ZodError);
    });

    it('should reject panes below minimum', () => {
      expect(() => validateConfig({ defaultPanes: 1 })).toThrow(ZodError);
    });

    it('should reject panes above maximum', () => {
      expect(() => validateConfig({ defaultPanes: 7 })).toThrow(ZodError);
    });

    it('should reject non-integer panes', () => {
      expect(() => validateConfig({ defaultPanes: 3.5 })).toThrow(ZodError);
    });

    it('should reject invalid cleanup policy in config', () => {
      expect(() => validateConfig({ cleanupPolicy: 'never' })).toThrow(ZodError);
    });

    it('should reject invalid color theme', () => {
      expect(() => validateConfig({ colorTheme: 'purple' })).toThrow(ZodError);
    });

    it('should reject invalid terminal runtime', () => {
      expect(() => validateConfig({ terminalDefaultRuntime: 'cmd' })).toThrow(ZodError);
    });

    it('should reject terminalMaxCount below minimum', () => {
      expect(() => validateConfig({ terminalMaxCount: 1 })).toThrow(ZodError);
    });

    it('should reject terminalMaxCount above maximum', () => {
      expect(() => validateConfig({ terminalMaxCount: 17 })).toThrow(ZodError);
    });

    it('should reject non-integer terminalMaxCount', () => {
      expect(() => validateConfig({ terminalMaxCount: 10.5 })).toThrow(ZodError);
    });

    it('should reject a non-object input', () => {
      expect(() => validateConfig('not-an-object')).toThrow(ZodError);
      expect(() => validateConfig(null)).toThrow(ZodError);
      expect(() => validateConfig(42)).toThrow(ZodError);
    });

    it('should reject invalid repository cache entries', () => {
      expect(() =>
        validateConfig({
          githubRepositoriesCache: [{ full_name: 'user/repo' }],
        })
      ).toThrow(ZodError);
    });

    it('should reject invalid preset within config', () => {
      expect(() =>
        validateConfig({
          presets: {
            bad: { layout: 'grid', panes: 10, cleanup: 'session' },
          },
        })
      ).toThrow(ZodError);
    });

    it('should accept boundary pane values in config', () => {
      const configMin = validateConfig({ defaultPanes: 2 });
      expect(configMin.defaultPanes).toBe(2);

      const configMax = validateConfig({ defaultPanes: 6 });
      expect(configMax.defaultPanes).toBe(6);
    });

    it('should accept boundary terminalMaxCount values in config', () => {
      const configMin = validateConfig({ terminalMaxCount: 2 });
      expect(configMin.terminalMaxCount).toBe(2);

      const configMax = validateConfig({ terminalMaxCount: 16 });
      expect(configMax.terminalMaxCount).toBe(16);
    });

    it('should accept all valid color themes', () => {
      for (const theme of ['cyan', 'green', 'magenta', 'blue', 'yellow', 'red']) {
        const config = validateConfig({ colorTheme: theme });
        expect(config.colorTheme).toBe(theme);
      }
    });

    it('should accept all valid terminal runtimes', () => {
      for (const runtime of ['wsl', 'powershell', 'native']) {
        const config = validateConfig({ terminalDefaultRuntime: runtime });
        expect(config.terminalDefaultRuntime).toBe(runtime);
      }
    });
  });

  describe('validateLayout', () => {
    it('should accept "horizontal"', () => {
      expect(validateLayout('horizontal')).toBe('horizontal');
    });

    it('should accept "vertical"', () => {
      expect(validateLayout('vertical')).toBe('vertical');
    });

    it('should accept "grid"', () => {
      expect(validateLayout('grid')).toBe('grid');
    });

    it('should reject an invalid layout string', () => {
      expect(() => validateLayout('diagonal')).toThrow(ZodError);
    });

    it('should reject an empty string', () => {
      expect(() => validateLayout('')).toThrow(ZodError);
    });

    it('should reject a layout with wrong casing', () => {
      expect(() => validateLayout('Grid')).toThrow(ZodError);
      expect(() => validateLayout('HORIZONTAL')).toThrow(ZodError);
      expect(() => validateLayout('Vertical')).toThrow(ZodError);
    });

    it('should reject a layout with extra whitespace', () => {
      expect(() => validateLayout(' grid ')).toThrow(ZodError);
      expect(() => validateLayout('grid ')).toThrow(ZodError);
    });
  });

  describe('validateCleanupPolicy', () => {
    it('should accept "session"', () => {
      expect(validateCleanupPolicy('session')).toBe('session');
    });

    it('should accept "persistent"', () => {
      expect(validateCleanupPolicy('persistent')).toBe('persistent');
    });

    it('should reject an invalid policy string', () => {
      expect(() => validateCleanupPolicy('never')).toThrow(ZodError);
    });

    it('should reject an empty string', () => {
      expect(() => validateCleanupPolicy('')).toThrow(ZodError);
    });

    it('should reject a policy with wrong casing', () => {
      expect(() => validateCleanupPolicy('Session')).toThrow(ZodError);
      expect(() => validateCleanupPolicy('PERSISTENT')).toThrow(ZodError);
    });

    it('should reject a policy with extra whitespace', () => {
      expect(() => validateCleanupPolicy(' session ')).toThrow(ZodError);
    });
  });

  describe('validatePresetConfig', () => {
    it('should accept a valid preset config', () => {
      const preset = validatePresetConfig({
        layout: 'grid',
        panes: 4,
        cleanup: 'session',
      });
      expect(preset.layout).toBe('grid');
      expect(preset.panes).toBe(4);
      expect(preset.cleanup).toBe('session');
    });

    it('should accept all layout types in presets', () => {
      for (const layout of ['horizontal', 'vertical', 'grid']) {
        const preset = validatePresetConfig({
          layout,
          panes: 3,
          cleanup: 'persistent',
        });
        expect(preset.layout).toBe(layout);
      }
    });

    it('should accept boundary pane counts', () => {
      const presetMin = validatePresetConfig({
        layout: 'grid',
        panes: 2,
        cleanup: 'session',
      });
      expect(presetMin.panes).toBe(2);

      const presetMax = validatePresetConfig({
        layout: 'grid',
        panes: 6,
        cleanup: 'session',
      });
      expect(presetMax.panes).toBe(6);
    });

    it('should reject panes below minimum', () => {
      expect(() =>
        validatePresetConfig({ layout: 'grid', panes: 1, cleanup: 'session' })
      ).toThrow(ZodError);
    });

    it('should reject panes above maximum', () => {
      expect(() =>
        validatePresetConfig({ layout: 'grid', panes: 7, cleanup: 'session' })
      ).toThrow(ZodError);
    });

    it('should reject non-integer panes', () => {
      expect(() =>
        validatePresetConfig({ layout: 'grid', panes: 3.5, cleanup: 'session' })
      ).toThrow(ZodError);
    });

    it('should reject an invalid layout', () => {
      expect(() =>
        validatePresetConfig({ layout: 'diagonal', panes: 4, cleanup: 'session' })
      ).toThrow(ZodError);
    });

    it('should reject an invalid cleanup policy', () => {
      expect(() =>
        validatePresetConfig({ layout: 'grid', panes: 4, cleanup: 'never' })
      ).toThrow(ZodError);
    });

    it('should reject missing required fields', () => {
      expect(() => validatePresetConfig({})).toThrow(ZodError);
      expect(() => validatePresetConfig({ layout: 'grid' })).toThrow(ZodError);
      expect(() => validatePresetConfig({ layout: 'grid', panes: 4 })).toThrow(ZodError);
    });

    it('should reject non-object input', () => {
      expect(() => validatePresetConfig('not-an-object')).toThrow(ZodError);
      expect(() => validatePresetConfig(null)).toThrow(ZodError);
      expect(() => validatePresetConfig(42)).toThrow(ZodError);
    });
  });

  describe('isValidLayout', () => {
    it('should return true for valid layouts', () => {
      expect(isValidLayout('horizontal')).toBe(true);
      expect(isValidLayout('vertical')).toBe(true);
      expect(isValidLayout('grid')).toBe(true);
    });

    it('should return false for invalid layouts', () => {
      expect(isValidLayout('diagonal')).toBe(false);
      expect(isValidLayout('')).toBe(false);
      expect(isValidLayout('Grid')).toBe(false);
      expect(isValidLayout('HORIZONTAL')).toBe(false);
      expect(isValidLayout(' grid')).toBe(false);
    });
  });

  describe('isValidCleanupPolicy', () => {
    it('should return true for valid policies', () => {
      expect(isValidCleanupPolicy('session')).toBe(true);
      expect(isValidCleanupPolicy('persistent')).toBe(true);
    });

    it('should return false for invalid policies', () => {
      expect(isValidCleanupPolicy('never')).toBe(false);
      expect(isValidCleanupPolicy('')).toBe(false);
      expect(isValidCleanupPolicy('Session')).toBe(false);
      expect(isValidCleanupPolicy('PERSISTENT')).toBe(false);
      expect(isValidCleanupPolicy(' session')).toBe(false);
    });
  });

  describe('isValidPaneCount', () => {
    it('should return true for valid pane counts (2-6)', () => {
      expect(isValidPaneCount(2)).toBe(true);
      expect(isValidPaneCount(3)).toBe(true);
      expect(isValidPaneCount(4)).toBe(true);
      expect(isValidPaneCount(5)).toBe(true);
      expect(isValidPaneCount(6)).toBe(true);
    });

    it('should return false for counts below minimum', () => {
      expect(isValidPaneCount(0)).toBe(false);
      expect(isValidPaneCount(1)).toBe(false);
      expect(isValidPaneCount(-1)).toBe(false);
    });

    it('should return false for counts above maximum', () => {
      expect(isValidPaneCount(7)).toBe(false);
      expect(isValidPaneCount(100)).toBe(false);
    });

    it('should return false for non-integer values', () => {
      expect(isValidPaneCount(2.5)).toBe(false);
      expect(isValidPaneCount(3.9)).toBe(false);
      expect(isValidPaneCount(5.1)).toBe(false);
    });

    it('should return false for special numeric values', () => {
      expect(isValidPaneCount(NaN)).toBe(false);
      expect(isValidPaneCount(Infinity)).toBe(false);
      expect(isValidPaneCount(-Infinity)).toBe(false);
    });
  });

  describe('isValidTerminalCount', () => {
    it('should return true for valid terminal counts (2-16)', () => {
      expect(isValidTerminalCount(2)).toBe(true);
      expect(isValidTerminalCount(8)).toBe(true);
      expect(isValidTerminalCount(16)).toBe(true);
    });

    it('should return false for counts below minimum', () => {
      expect(isValidTerminalCount(0)).toBe(false);
      expect(isValidTerminalCount(1)).toBe(false);
      expect(isValidTerminalCount(-1)).toBe(false);
    });

    it('should return false for counts above maximum', () => {
      expect(isValidTerminalCount(17)).toBe(false);
      expect(isValidTerminalCount(100)).toBe(false);
    });

    it('should return false for non-integer values', () => {
      expect(isValidTerminalCount(2.5)).toBe(false);
      expect(isValidTerminalCount(15.9)).toBe(false);
    });

    it('should return false for special numeric values', () => {
      expect(isValidTerminalCount(NaN)).toBe(false);
      expect(isValidTerminalCount(Infinity)).toBe(false);
      expect(isValidTerminalCount(-Infinity)).toBe(false);
    });

    it('should return true for all integers within the valid range', () => {
      for (let i = 2; i <= 16; i++) {
        expect(isValidTerminalCount(i)).toBe(true);
      }
    });
  });

  describe('sanitizePathSegment', () => {
    it('should return alphanumeric strings unchanged', () => {
      expect(sanitizePathSegment('abc123')).toBe('abc123');
    });

    it('should allow dots, hyphens, and underscores', () => {
      expect(sanitizePathSegment('my-branch')).toBe('my-branch');
      expect(sanitizePathSegment('my_branch')).toBe('my_branch');
      expect(sanitizePathSegment('v1.0.0')).toBe('v1.0.0');
      expect(sanitizePathSegment('my-branch_v1.0')).toBe('my-branch_v1.0');
    });

    it('should replace non-alphanumeric characters with hyphens', () => {
      expect(sanitizePathSegment('feature/branch')).toBe('feature-branch');
      expect(sanitizePathSegment('hello world')).toBe('hello-world');
      expect(sanitizePathSegment('a@b#c$d')).toBe('a-b-c-d');
    });

    it('should collapse consecutive invalid characters into a single hyphen', () => {
      expect(sanitizePathSegment('a///b')).toBe('a-b');
      expect(sanitizePathSegment('a   b')).toBe('a-b');
      expect(sanitizePathSegment('a@#$b')).toBe('a-b');
    });

    it('should trim leading and trailing hyphens', () => {
      expect(sanitizePathSegment('/branch/')).toBe('branch');
      expect(sanitizePathSegment('///branch///')).toBe('branch');
      expect(sanitizePathSegment('@@@branch@@@')).toBe('branch');
    });

    it('should return "default" for empty string', () => {
      expect(sanitizePathSegment('')).toBe('default');
    });

    it('should return "default" for strings that become empty after sanitization', () => {
      expect(sanitizePathSegment('///')).toBe('default');
      expect(sanitizePathSegment('@#$%')).toBe('default');
      expect(sanitizePathSegment('   ')).toBe('default');
    });

    it('should handle mixed valid and invalid characters', () => {
      expect(sanitizePathSegment('feat/my-branch_v2.0!!')).toBe('feat-my-branch_v2.0');
    });
  });

  describe('normalizePath', () => {
    it('should convert backslashes to forward slashes', () => {
      expect(normalizePath('C:\\Users\\name\\repo')).toBe('C:/Users/name/repo');
    });

    it('should leave forward slashes unchanged', () => {
      expect(normalizePath('/home/user/repo')).toBe('/home/user/repo');
    });

    it('should handle mixed slashes', () => {
      expect(normalizePath('C:\\Users/name\\repo/src')).toBe('C:/Users/name/repo/src');
    });

    it('should handle an empty string', () => {
      expect(normalizePath('')).toBe('');
    });

    it('should handle paths with no slashes', () => {
      expect(normalizePath('file.txt')).toBe('file.txt');
    });

    it('should convert consecutive backslashes', () => {
      expect(normalizePath('C:\\\\Users\\\\name')).toBe('C://Users//name');
    });

    it('should handle a single backslash', () => {
      expect(normalizePath('\\')).toBe('/');
    });
  });

  describe('posixPath', () => {
    it('should convert backslashes to forward slashes', () => {
      expect(posixPath('C:\\Users\\name\\repo')).toBe('C:/Users/name/repo');
    });

    it('should remove leading double slashes', () => {
      expect(posixPath('//server/share')).toBe('/server/share');
    });

    it('should remove multiple leading slashes', () => {
      expect(posixPath('///path/to/file')).toBe('/path/to/file');
      expect(posixPath('////path')).toBe('/path');
    });

    it('should not modify a single leading slash', () => {
      expect(posixPath('/home/user/repo')).toBe('/home/user/repo');
    });

    it('should handle backslashes that produce leading double slashes', () => {
      expect(posixPath('\\\\server\\share')).toBe('/server/share');
    });

    it('should preserve double slashes in the middle of the path', () => {
      expect(posixPath('/home//user')).toBe('/home//user');
    });

    it('should handle an empty string', () => {
      expect(posixPath('')).toBe('');
    });

    it('should handle paths with no slashes', () => {
      expect(posixPath('file.txt')).toBe('file.txt');
    });

    it('should handle a UNC-style path with backslashes', () => {
      expect(posixPath('\\\\server\\share\\folder')).toBe('/server/share/folder');
    });
  });
});
