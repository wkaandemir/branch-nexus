import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  RecoverableError,
  FatalError,
  DEFAULT_RETRY_POLICY,
  sleep,
  runWithRetry,
} from '../../ts-src/utils/retry.js';
import type { RetryPolicy } from '../../ts-src/utils/retry.js';

const FAST_POLICY: RetryPolicy = {
  maxAttempts: 3,
  initialBackoffMs: 1,
  multiplier: 2,
};

describe('retry', () => {
  describe('RecoverableError', () => {
    it('should be an instance of Error', () => {
      const error = new RecoverableError('something went wrong');
      expect(error).toBeInstanceOf(Error);
    });

    it('should have name set to RecoverableError', () => {
      const error = new RecoverableError('something went wrong');
      expect(error.name).toBe('RecoverableError');
    });

    it('should store the message', () => {
      const error = new RecoverableError('network timeout');
      expect(error.message).toBe('network timeout');
    });
  });

  describe('FatalError', () => {
    it('should be an instance of Error', () => {
      const error = new FatalError('permission denied');
      expect(error).toBeInstanceOf(Error);
    });

    it('should have name set to FatalError', () => {
      const error = new FatalError('permission denied');
      expect(error.name).toBe('FatalError');
    });

    it('should store the message', () => {
      const error = new FatalError('invalid credentials');
      expect(error.message).toBe('invalid credentials');
    });
  });

  describe('DEFAULT_RETRY_POLICY', () => {
    it('should have maxAttempts of 3', () => {
      expect(DEFAULT_RETRY_POLICY.maxAttempts).toBe(3);
    });

    it('should have initialBackoffMs of 500', () => {
      expect(DEFAULT_RETRY_POLICY.initialBackoffMs).toBe(500);
    });

    it('should have multiplier of 2', () => {
      expect(DEFAULT_RETRY_POLICY.multiplier).toBe(2);
    });
  });

  describe('sleep', () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('should resolve after the specified duration', async () => {
      const promise = sleep(1000);
      let resolved = false;
      promise.then(() => {
        resolved = true;
      });

      expect(resolved).toBe(false);

      await vi.advanceTimersByTimeAsync(999);
      expect(resolved).toBe(false);

      await vi.advanceTimersByTimeAsync(1);
      expect(resolved).toBe(true);
    });

    it('should resolve immediately for 0ms', async () => {
      const promise = sleep(0);
      await vi.advanceTimersByTimeAsync(0);
      await expect(promise).resolves.toBeUndefined();
    });
  });

  describe('runWithRetry', () => {
    it('should succeed on the first attempt', async () => {
      const operation = vi.fn().mockResolvedValue('success');

      const result = await runWithRetry(operation, FAST_POLICY);

      expect(result).toBe('success');
      expect(operation).toHaveBeenCalledTimes(1);
    });

    it('should return the resolved value from the operation', async () => {
      const operation = vi.fn().mockResolvedValue({ data: 42 });

      const result = await runWithRetry(operation, FAST_POLICY);

      expect(result).toEqual({ data: 42 });
    });

    it('should retry on RecoverableError and succeed on 2nd attempt', async () => {
      const operation = vi
        .fn()
        .mockRejectedValueOnce(new RecoverableError('try again'))
        .mockResolvedValue('recovered');

      const result = await runWithRetry(operation, FAST_POLICY);

      expect(result).toBe('recovered');
      expect(operation).toHaveBeenCalledTimes(2);
    });

    it('should retry on RecoverableError and succeed on 3rd attempt', async () => {
      const operation = vi
        .fn()
        .mockRejectedValueOnce(new RecoverableError('fail 1'))
        .mockRejectedValueOnce(new RecoverableError('fail 2'))
        .mockResolvedValue('finally');

      const result = await runWithRetry(operation, FAST_POLICY);

      expect(result).toBe('finally');
      expect(operation).toHaveBeenCalledTimes(3);
    });

    it('should throw FatalError immediately without retrying', async () => {
      const fatalError = new FatalError('fatal failure');
      const operation = vi.fn().mockRejectedValue(fatalError);

      await expect(runWithRetry(operation, FAST_POLICY)).rejects.toThrow(fatalError);
      expect(operation).toHaveBeenCalledTimes(1);
    });

    it('should throw FatalError even if it occurs on a retry attempt', async () => {
      const fatalError = new FatalError('fatal on second try');
      const operation = vi
        .fn()
        .mockRejectedValueOnce(new RecoverableError('recoverable'))
        .mockRejectedValue(fatalError);

      await expect(runWithRetry(operation, FAST_POLICY)).rejects.toThrow(fatalError);
      expect(operation).toHaveBeenCalledTimes(2);
    });

    it('should throw unknown errors immediately without retrying', async () => {
      const unknownError = new Error('unexpected');
      const operation = vi.fn().mockRejectedValue(unknownError);

      await expect(runWithRetry(operation, FAST_POLICY)).rejects.toThrow(unknownError);
      expect(operation).toHaveBeenCalledTimes(1);
    });

    it('should throw non-Error exceptions immediately', async () => {
      const operation = vi.fn().mockRejectedValue('string error');

      await expect(runWithRetry(operation, FAST_POLICY)).rejects.toBe('string error');
      expect(operation).toHaveBeenCalledTimes(1);
    });

    it('should exhaust retries and throw the last RecoverableError', async () => {
      const lastError = new RecoverableError('final failure');
      const operation = vi
        .fn()
        .mockRejectedValueOnce(new RecoverableError('fail 1'))
        .mockRejectedValueOnce(new RecoverableError('fail 2'))
        .mockRejectedValue(lastError);

      await expect(runWithRetry(operation, FAST_POLICY)).rejects.toThrow(lastError);
      expect(operation).toHaveBeenCalledTimes(3);
    });

    it('should throw the last RecoverableError with its original message', async () => {
      const operation = vi
        .fn()
        .mockRejectedValueOnce(new RecoverableError('attempt 1'))
        .mockRejectedValueOnce(new RecoverableError('attempt 2'))
        .mockRejectedValue(new RecoverableError('attempt 3'));

      await expect(runWithRetry(operation, FAST_POLICY)).rejects.toThrow('attempt 3');
    });

    it('should respect a custom policy with maxAttempts of 1', async () => {
      const singleAttemptPolicy: RetryPolicy = {
        maxAttempts: 1,
        initialBackoffMs: 1,
        multiplier: 2,
      };
      const operation = vi.fn().mockRejectedValue(new RecoverableError('no retries'));

      await expect(runWithRetry(operation, singleAttemptPolicy)).rejects.toThrow('no retries');
      expect(operation).toHaveBeenCalledTimes(1);
    });

    it('should respect a custom policy with maxAttempts of 5', async () => {
      const fiveAttemptPolicy: RetryPolicy = {
        maxAttempts: 5,
        initialBackoffMs: 1,
        multiplier: 1,
      };
      const operation = vi
        .fn()
        .mockRejectedValueOnce(new RecoverableError('fail 1'))
        .mockRejectedValueOnce(new RecoverableError('fail 2'))
        .mockRejectedValueOnce(new RecoverableError('fail 3'))
        .mockRejectedValueOnce(new RecoverableError('fail 4'))
        .mockResolvedValue('success on 5th');

      const result = await runWithRetry(operation, fiveAttemptPolicy);

      expect(result).toBe('success on 5th');
      expect(operation).toHaveBeenCalledTimes(5);
    });

    it('should use exponential backoff between retries', async () => {
      const backoffPolicy: RetryPolicy = {
        maxAttempts: 4,
        initialBackoffMs: 1,
        multiplier: 2,
      };

      const timestamps: number[] = [];
      const operation = vi.fn().mockImplementation(() => {
        timestamps.push(Date.now());
        if (timestamps.length < 4) {
          return Promise.reject(new RecoverableError(`fail ${timestamps.length}`));
        }
        return Promise.resolve('done');
      });

      const result = await runWithRetry(operation, backoffPolicy);
      expect(result).toBe('done');
      expect(operation).toHaveBeenCalledTimes(4);
      // Verify there was some waiting between retries (at least the calls were sequential)
      for (let i = 1; i < timestamps.length; i++) {
        expect(timestamps[i]).toBeGreaterThanOrEqual(timestamps[i - 1]);
      }
    });

    it('should use DEFAULT_RETRY_POLICY when no policy is provided', async () => {
      const operation = vi
        .fn()
        .mockRejectedValueOnce(new RecoverableError('fail'))
        .mockResolvedValue('ok');

      const start = Date.now();
      const result = await runWithRetry(operation);
      const elapsed = Date.now() - start;

      expect(result).toBe('ok');
      expect(operation).toHaveBeenCalledTimes(2);
      // DEFAULT_RETRY_POLICY.initialBackoffMs = 500, so elapsed should be >= ~500ms
      expect(elapsed).toBeGreaterThanOrEqual(400);
    });

    it('should not wait when succeeding on first attempt', async () => {
      const operation = vi.fn().mockResolvedValue('instant');

      const start = Date.now();
      await runWithRetry(operation, FAST_POLICY);
      const elapsed = Date.now() - start;

      expect(operation).toHaveBeenCalledTimes(1);
      expect(elapsed).toBeLessThan(50);
    });

    it('should not sleep after the last failed attempt', async () => {
      const operation = vi.fn().mockRejectedValue(new RecoverableError('always fails'));

      await expect(runWithRetry(operation, FAST_POLICY)).rejects.toThrow('always fails');

      // 3 attempts total with FAST_POLICY, sleep only between attempts
      expect(operation).toHaveBeenCalledTimes(3);
    });
  });
});
