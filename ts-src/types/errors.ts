export enum ExitCode {
  SUCCESS = 0,
  INVALID_ARGS = 2,
  CONFIG_ERROR = 3,
  RUNTIME_ERROR = 4,
  GIT_ERROR = 5,
  TMUX_ERROR = 6,
  VALIDATION_ERROR = 7,
  UNSUPPORTED_PLATFORM = 8,
}

export class BranchNexusError extends Error {
  public readonly code: ExitCode;
  public readonly hint: string;

  constructor(message: string, code: ExitCode = ExitCode.RUNTIME_ERROR, hint = '') {
    super(message);
    this.name = 'BranchNexusError';
    this.code = code;
    this.hint = hint;
  }

  public override toString(): string {
    if (this.hint !== '') {
      return `${this.message} Hint: ${this.hint}`;
    }
    return this.message;
  }
}

export function userFacingError(message: string, hint?: string): string {
  if (hint !== undefined && hint !== '') {
    return `Error: ${message}. Next step: ${hint}`;
  }
  return `Error: ${message}.`;
}

export function isBranchNexusError(error: unknown): error is BranchNexusError {
  return error instanceof BranchNexusError;
}
