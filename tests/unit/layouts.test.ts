import { describe, it, expect } from 'vitest';
import { buildLayoutCommands, validateLayout } from '../../ts-src/tmux/layouts.js';
import { BranchNexusError, ExitCode } from '../../ts-src/types/errors.js';

describe('layouts', () => {
  describe('validateLayout', () => {
    it('should accept valid layouts', () => {
      expect(() => validateLayout('grid', 4)).not.toThrow();
      expect(() => validateLayout('horizontal', 2)).not.toThrow();
      expect(() => validateLayout('vertical', 6)).not.toThrow();
    });

    it('should reject invalid layouts', () => {
      expect(() => validateLayout('invalid', 4)).toThrow(BranchNexusError);
    });

    it('should reject invalid pane counts', () => {
      expect(() => validateLayout('grid', 0)).toThrow(BranchNexusError);
      expect(() => validateLayout('grid', 7)).toThrow(BranchNexusError);
    });
  });

  describe('buildLayoutCommands', () => {
    it('should generate grid layout commands for 4 panes', () => {
      const commands = buildLayoutCommands('test', 'grid', [
        '/path/0',
        '/path/1',
        '/path/2',
        '/path/3',
      ]);

      expect(commands.length).toBeGreaterThan(0);
      expect(commands[0]).toContainEqual('tmux');
      expect(commands[0]).toContainEqual('new-session');
      expect(commands[0]).toContainEqual('-s');
      expect(commands[0]).toContainEqual('test');
    });

    it('should generate horizontal layout commands', () => {
      const commands = buildLayoutCommands('test', 'horizontal', ['/path/0', '/path/1']);

      const splitCommands = commands.filter((cmd) => cmd.includes('split-window'));
      expect(splitCommands.every((cmd) => cmd.includes('-h'))).toBe(true);
    });

    it('should generate vertical layout commands', () => {
      const commands = buildLayoutCommands('test', 'vertical', ['/path/0', '/path/1']);

      const splitCommands = commands.filter((cmd) => cmd.includes('split-window'));
      expect(splitCommands.every((cmd) => cmd.includes('-v'))).toBe(true);
    });

    it('should include mouse on command', () => {
      const commands = buildLayoutCommands('test', 'grid', ['/path/0', '/path/1']);

      expect(
        commands.some(
          (cmd) => cmd.includes('set-option') && cmd.includes('mouse') && cmd.includes('on')
        )
      ).toBe(true);
    });

    it('should include select-layout command', () => {
      const commands = buildLayoutCommands('test', 'grid', ['/path/0', '/path/1']);

      expect(commands.some((cmd) => cmd.includes('select-layout'))).toBe(true);
    });
  });
});
