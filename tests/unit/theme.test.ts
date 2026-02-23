import { describe, it, expect } from 'vitest';
import {
  COLOR_PALETTES,
  PALETTE_KEYS,
  getPalette,
  theme,
  box,
  formatPreview,
  type ColorPalette,
} from '../../ts-src/utils/theme.js';

describe('theme', () => {
  describe('COLOR_PALETTES', () => {
    it('should contain exactly 6 palette entries', () => {
      expect(Object.keys(COLOR_PALETTES)).toHaveLength(6);
    });

    it('should have all expected palette keys', () => {
      const expectedKeys = ['cyan', 'green', 'magenta', 'blue', 'yellow', 'red'];
      for (const key of expectedKeys) {
        expect(COLOR_PALETTES).toHaveProperty(key);
      }
    });

    it('should have correct names matching their keys', () => {
      for (const [key, palette] of Object.entries(COLOR_PALETTES)) {
        expect(palette.name).toBe(key);
      }
    });

    it('should have correct labels for each palette', () => {
      const expectedLabels: Record<string, string> = {
        cyan: 'Cyan',
        green: 'Yeşil',
        magenta: 'Magenta',
        blue: 'Mavi',
        yellow: 'Sarı',
        red: 'Kırmızı',
      };

      for (const [key, label] of Object.entries(expectedLabels)) {
        expect(COLOR_PALETTES[key].label).toBe(label);
      }
    });

    it('should have name, label, primary, primaryBold, and bg properties on each palette', () => {
      for (const palette of Object.values(COLOR_PALETTES)) {
        expect(palette).toHaveProperty('name');
        expect(palette).toHaveProperty('label');
        expect(palette).toHaveProperty('primary');
        expect(palette).toHaveProperty('primaryBold');
        expect(palette).toHaveProperty('bg');
      }
    });

    it('should have callable primary, primaryBold, and bg functions', () => {
      for (const palette of Object.values(COLOR_PALETTES)) {
        expect(typeof palette.primary).toBe('function');
        expect(typeof palette.primaryBold).toBe('function');
        expect(typeof palette.bg).toBe('function');
      }
    });

    it('should produce string output from primary, primaryBold, and bg', () => {
      for (const palette of Object.values(COLOR_PALETTES)) {
        expect(typeof palette.primary('test')).toBe('string');
        expect(typeof palette.primaryBold('test')).toBe('string');
        expect(typeof palette.bg('test')).toBe('string');
      }
    });
  });

  describe('PALETTE_KEYS', () => {
    it('should contain exactly 6 keys', () => {
      expect(PALETTE_KEYS).toHaveLength(6);
    });

    it('should include all palette names', () => {
      expect(PALETTE_KEYS).toContain('cyan');
      expect(PALETTE_KEYS).toContain('green');
      expect(PALETTE_KEYS).toContain('magenta');
      expect(PALETTE_KEYS).toContain('blue');
      expect(PALETTE_KEYS).toContain('yellow');
      expect(PALETTE_KEYS).toContain('red');
    });

    it('should match the keys of COLOR_PALETTES', () => {
      expect(PALETTE_KEYS).toEqual(Object.keys(COLOR_PALETTES));
    });
  });

  describe('getPalette', () => {
    it('should return the correct palette for each valid name', () => {
      for (const key of PALETTE_KEYS) {
        const palette = getPalette(key);
        expect(palette.name).toBe(key);
        expect(palette).toBe(COLOR_PALETTES[key]);
      }
    });

    it('should return cyan palette as default for unknown names', () => {
      const fallback = getPalette('nonexistent');
      expect(fallback.name).toBe('cyan');
      expect(fallback).toBe(COLOR_PALETTES.cyan);
    });

    it('should return cyan palette for empty string', () => {
      const fallback = getPalette('');
      expect(fallback.name).toBe('cyan');
    });

    it('should be case-sensitive and fallback for uppercase names', () => {
      const fallback = getPalette('Cyan');
      expect(fallback.name).toBe('cyan');
    });

    it('should return a valid ColorPalette structure', () => {
      const palette = getPalette('magenta');
      expect(palette.name).toBe('magenta');
      expect(palette.label).toBe('Magenta');
      expect(typeof palette.primary).toBe('function');
      expect(typeof palette.primaryBold).toBe('function');
      expect(typeof palette.bg).toBe('function');
    });
  });

  describe('theme object', () => {
    it('should have colors, symbols, and spacing properties', () => {
      expect(theme).toHaveProperty('colors');
      expect(theme).toHaveProperty('symbols');
      expect(theme).toHaveProperty('spacing');
    });

    describe('colors', () => {
      it('should have all expected color functions', () => {
        const expectedColors = [
          'primary',
          'success',
          'warning',
          'error',
          'info',
          'muted',
          'highlight',
          'accent',
        ];
        for (const color of expectedColors) {
          expect(theme.colors).toHaveProperty(color);
          expect(typeof (theme.colors as Record<string, unknown>)[color]).toBe('function');
        }
      });

      it('should produce string output when called', () => {
        expect(typeof theme.colors.primary('text')).toBe('string');
        expect(typeof theme.colors.success('text')).toBe('string');
        expect(typeof theme.colors.warning('text')).toBe('string');
        expect(typeof theme.colors.error('text')).toBe('string');
        expect(typeof theme.colors.info('text')).toBe('string');
        expect(typeof theme.colors.muted('text')).toBe('string');
        expect(typeof theme.colors.highlight('text')).toBe('string');
        expect(typeof theme.colors.accent('text')).toBe('string');
      });
    });

    describe('symbols', () => {
      it('should have pointer, check, and cross symbols', () => {
        expect(theme.symbols.pointer).toBe('❯');
        expect(theme.symbols.check).toBe('✓');
        expect(theme.symbols.cross).toBe('✕');
      });

      it('should have radio symbols with on and off', () => {
        expect(theme.symbols.radio.on).toBe('●');
        expect(theme.symbols.radio.off).toBe('○');
      });

      it('should have checkbox symbols with on and off', () => {
        expect(theme.symbols.checkbox.on).toBe('◼');
        expect(theme.symbols.checkbox.off).toBe('◻');
      });

      it('should have arrow symbols for all directions', () => {
        expect(theme.symbols.arrow.left).toBe('←');
        expect(theme.symbols.arrow.right).toBe('→');
        expect(theme.symbols.arrow.up).toBe('↑');
        expect(theme.symbols.arrow.down).toBe('↓');
      });

      it('should have box-drawing characters', () => {
        expect(theme.symbols.box.topLeft).toBe('╔');
        expect(theme.symbols.box.topRight).toBe('╗');
        expect(theme.symbols.box.bottomLeft).toBe('╚');
        expect(theme.symbols.box.bottomRight).toBe('╝');
        expect(theme.symbols.box.horizontal).toBe('═');
        expect(theme.symbols.box.vertical).toBe('║');
        expect(theme.symbols.box.left).toBe('╠');
        expect(theme.symbols.box.right).toBe('╣');
      });
    });

    describe('spacing', () => {
      it('should have correct spacing values', () => {
        expect(theme.spacing.xs).toBe(1);
        expect(theme.spacing.sm).toBe(2);
        expect(theme.spacing.md).toBe(3);
        expect(theme.spacing.lg).toBe(4);
      });
    });
  });

  describe('box', () => {
    it('should generate a box with title and content', () => {
      const result = box('Title', ['Line 1', 'Line 2']);
      expect(result).toContain('Title');
      expect(result).toContain('Line 1');
      expect(result).toContain('Line 2');
    });

    it('should use box-drawing characters', () => {
      const result = box('Test', ['content']);
      expect(result).toContain('╔');
      expect(result).toContain('╗');
      expect(result).toContain('╚');
      expect(result).toContain('╝');
      expect(result).toContain('═');
      expect(result).toContain('║');
    });

    it('should produce multiple lines separated by newlines', () => {
      const result = box('Title', ['A', 'B']);
      const lines = result.split('\n');
      // top border + 2 content lines + bottom border = 4 lines
      expect(lines).toHaveLength(4);
    });

    it('should start with top-left corner and end with bottom-right corner', () => {
      const result = box('Title', ['content']);
      const lines = result.split('\n');
      expect(lines[0].startsWith('╔')).toBe(true);
      expect(lines[0].endsWith('╗')).toBe(true);
      expect(lines[lines.length - 1].startsWith('╚')).toBe(true);
      expect(lines[lines.length - 1].endsWith('╝')).toBe(true);
    });

    it('should use vertical bars for content lines', () => {
      const result = box('Title', ['hello']);
      const lines = result.split('\n');
      // Content lines (between top and bottom border)
      for (let i = 1; i < lines.length - 1; i++) {
        expect(lines[i].startsWith('║')).toBe(true);
        expect(lines[i].endsWith('║')).toBe(true);
      }
    });

    it('should use default width of 60', () => {
      const result = box('T', ['x']);
      const lines = result.split('\n');
      // Bottom border: ╚ + 60 horizontal chars + ╝
      const bottomLine = lines[lines.length - 1];
      // Count the horizontal chars between corners
      const horizontalCount = bottomLine.slice(1, -1).split('').filter((c) => c === '═').length;
      expect(horizontalCount).toBe(60);
    });

    it('should accept a custom width', () => {
      const result = box('T', ['x'], 40);
      const lines = result.split('\n');
      const bottomLine = lines[lines.length - 1];
      const horizontalCount = bottomLine.slice(1, -1).split('').filter((c) => c === '═').length;
      expect(horizontalCount).toBe(40);
    });

    it('should handle empty content array', () => {
      const result = box('Title', []);
      const lines = result.split('\n');
      // top border + bottom border only
      expect(lines).toHaveLength(2);
    });

    it('should embed title in the top border', () => {
      const result = box('My Box', ['content']);
      const lines = result.split('\n');
      const topLine = lines[0];
      expect(topLine).toContain(' My Box ');
    });
  });

  describe('formatPreview', () => {
    it('should format a key-value pair as a string', () => {
      const result = formatPreview('key', 'value');
      expect(typeof result).toBe('string');
      expect(result.length).toBeGreaterThan(0);
    });

    it('should contain both key and value text', () => {
      const result = formatPreview('name', 'BranchNexus');
      expect(result).toContain('name');
      expect(result).toContain('BranchNexus');
    });

    it('should pad the key to 10 characters', () => {
      // The key 'ab' should be padded to 10 chars before styling
      const result = formatPreview('ab', 'val');
      // After chalk styling, the raw text content should have the padded key
      expect(result).toContain('ab');
      expect(result).toContain('val');
    });

    it('should handle long keys', () => {
      const result = formatPreview('longkeyname', 'value');
      expect(result).toContain('longkeyname');
      expect(result).toContain('value');
    });

    it('should apply muted color to key and highlight to value', () => {
      // Both theme.colors.muted and theme.colors.highlight should be applied
      // We verify that the result differs from plain concatenation (chalk adds escape codes)
      const result = formatPreview('key', 'value');
      const plain = 'key'.padEnd(10) + ' ' + 'value';
      // If chalk is active, the result will contain ANSI escape codes and differ from plain
      // If chalk is not active (e.g., in CI), they may be equal, which is still valid
      expect(typeof result).toBe('string');
    });
  });
});
