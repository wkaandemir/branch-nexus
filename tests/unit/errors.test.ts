import { describe, it, expect } from 'vitest';
import {
  ExitCode,
  BranchNexusError,
  userFacingError,
  isBranchNexusError,
} from '../../ts-src/types/errors.js';

describe('errors', () => {
  describe('ExitCode', () => {
    it('should have correct numeric values', () => {
      expect(ExitCode.SUCCESS).toBe(0);
      expect(ExitCode.INVALID_ARGS).toBe(2);
      expect(ExitCode.CONFIG_ERROR).toBe(3);
      expect(ExitCode.RUNTIME_ERROR).toBe(4);
      expect(ExitCode.GIT_ERROR).toBe(5);
      expect(ExitCode.TMUX_ERROR).toBe(6);
      expect(ExitCode.VALIDATION_ERROR).toBe(7);
      expect(ExitCode.UNSUPPORTED_PLATFORM).toBe(8);
    });

    it('should have exactly 8 members', () => {
      const numericKeys = Object.keys(ExitCode).filter((k) => isNaN(Number(k)));
      expect(numericKeys).toHaveLength(8);
    });
  });

  describe('BranchNexusError', () => {
    it('should extend Error', () => {
      const error = new BranchNexusError('test');
      expect(error).toBeInstanceOf(Error);
      expect(error).toBeInstanceOf(BranchNexusError);
    });

    it('should set name to BranchNexusError', () => {
      const error = new BranchNexusError('test');
      expect(error.name).toBe('BranchNexusError');
    });

    it('should store the message', () => {
      const error = new BranchNexusError('something went wrong');
      expect(error.message).toBe('something went wrong');
    });

    it('should default code to RUNTIME_ERROR', () => {
      const error = new BranchNexusError('test');
      expect(error.code).toBe(ExitCode.RUNTIME_ERROR);
    });

    it('should default hint to empty string', () => {
      const error = new BranchNexusError('test');
      expect(error.hint).toBe('');
    });

    it('should accept a custom exit code', () => {
      const error = new BranchNexusError('bad args', ExitCode.INVALID_ARGS);
      expect(error.code).toBe(ExitCode.INVALID_ARGS);
    });

    it('should accept all three constructor parameters', () => {
      const error = new BranchNexusError('git failed', ExitCode.GIT_ERROR, 'check remote');
      expect(error.message).toBe('git failed');
      expect(error.code).toBe(ExitCode.GIT_ERROR);
      expect(error.hint).toBe('check remote');
    });

    it('should have readonly code and hint properties', () => {
      const error = new BranchNexusError('test', ExitCode.CONFIG_ERROR, 'fix config');
      // Verify the values are set correctly; readonly is enforced at compile time
      expect(error.code).toBe(ExitCode.CONFIG_ERROR);
      expect(error.hint).toBe('fix config');
    });

    describe('toString', () => {
      it('should return only the message when hint is empty', () => {
        const error = new BranchNexusError('something broke');
        expect(error.toString()).toBe('something broke');
      });

      it('should return message with hint when hint is provided', () => {
        const error = new BranchNexusError('tmux not found', ExitCode.TMUX_ERROR, 'install tmux');
        expect(error.toString()).toBe('tmux not found Hint: install tmux');
      });

      it('should return only the message when hint is explicitly empty string', () => {
        const error = new BranchNexusError('oops', ExitCode.RUNTIME_ERROR, '');
        expect(error.toString()).toBe('oops');
      });
    });
  });

  describe('userFacingError', () => {
    it('should format message without hint', () => {
      expect(userFacingError('file not found')).toBe('Error: file not found.');
    });

    it('should format message with hint', () => {
      expect(userFacingError('config invalid', 'run init again')).toBe(
        'Error: config invalid. Next step: run init again'
      );
    });

    it('should treat undefined hint the same as no hint', () => {
      expect(userFacingError('something failed', undefined)).toBe('Error: something failed.');
    });

    it('should treat empty string hint the same as no hint', () => {
      expect(userFacingError('something failed', '')).toBe('Error: something failed.');
    });
  });

  describe('isBranchNexusError', () => {
    it('should return true for BranchNexusError instances', () => {
      const error = new BranchNexusError('test');
      expect(isBranchNexusError(error)).toBe(true);
    });

    it('should return true for BranchNexusError with all params', () => {
      const error = new BranchNexusError('msg', ExitCode.GIT_ERROR, 'hint');
      expect(isBranchNexusError(error)).toBe(true);
    });

    it('should return false for a plain Error', () => {
      const error = new Error('plain error');
      expect(isBranchNexusError(error)).toBe(false);
    });

    it('should return false for a string', () => {
      expect(isBranchNexusError('not an error')).toBe(false);
    });

    it('should return false for null', () => {
      expect(isBranchNexusError(null)).toBe(false);
    });

    it('should return false for undefined', () => {
      expect(isBranchNexusError(undefined)).toBe(false);
    });

    it('should return false for a number', () => {
      expect(isBranchNexusError(42)).toBe(false);
    });

    it('should return false for a plain object with matching shape', () => {
      const fake = { message: 'test', code: 4, hint: '', name: 'BranchNexusError' };
      expect(isBranchNexusError(fake)).toBe(false);
    });
  });
});
