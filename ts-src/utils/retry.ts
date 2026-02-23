export class RecoverableError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'RecoverableError';
  }
}

export class FatalError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'FatalError';
  }
}

export interface RetryPolicy {
  maxAttempts: number;
  initialBackoffMs: number;
  multiplier: number;
}

export const DEFAULT_RETRY_POLICY: RetryPolicy = {
  maxAttempts: 3,
  initialBackoffMs: 500,
  multiplier: 2,
};

export async function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function runWithRetry<T>(
  operation: () => Promise<T>,
  policy: RetryPolicy = DEFAULT_RETRY_POLICY
): Promise<T> {
  let attempt = 0;
  let backoff = policy.initialBackoffMs;
  let lastError: Error | null = null;

  while (attempt < policy.maxAttempts) {
    attempt++;
    try {
      return await operation();
    } catch (error) {
      if (error instanceof FatalError) {
        throw error;
      }
      if (error instanceof RecoverableError) {
        lastError = error;
        if (attempt >= policy.maxAttempts) {
          break;
        }
        await sleep(backoff);
        backoff *= policy.multiplier;
      } else {
        throw error;
      }
    }
  }

  if (lastError) {
    throw lastError;
  }
  throw new Error('Retry policy exhausted without executing operation.');
}
