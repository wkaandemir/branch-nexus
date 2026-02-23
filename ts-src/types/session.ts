export type RuntimeKind = 'wsl' | 'powershell' | 'native';

export interface SessionTerminalSnapshot {
  terminalId: string;
  title: string;
  runtime: RuntimeKind;
  repoPath: string;
  branch: string;
}

export interface RuntimeSessionSnapshot {
  layout: string;
  templateCount: number;
  focusedTerminalId: string;
  terminals: SessionTerminalSnapshot[];
}

export function createTerminalSnapshot(
  terminalId: string,
  title: string,
  runtime: RuntimeKind,
  repoPath: string,
  branch: string
): SessionTerminalSnapshot {
  return { terminalId, title, runtime, repoPath, branch };
}

export function createSessionSnapshot(
  layout: string,
  templateCount: number,
  terminals: SessionTerminalSnapshot[],
  focusedTerminalId = ''
): RuntimeSessionSnapshot {
  return {
    layout,
    templateCount,
    focusedTerminalId,
    terminals,
  };
}

export function isSessionSnapshot(value: unknown): value is RuntimeSessionSnapshot {
  if (typeof value !== 'object' || value === null) {
    return false;
  }
  const snapshot = value as Record<string, unknown>;
  return (
    typeof snapshot['layout'] === 'string' &&
    typeof snapshot['templateCount'] === 'number' &&
    Array.isArray(snapshot['terminals'])
  );
}

export enum ExitChoice {
  CANCEL = 'Vazgec',
  PRESERVE = 'Koruyarak Cik',
  CLEAN = 'Temizleyerek Cik',
}

export interface SessionCleanupResult {
  closed: boolean;
  cancelled: boolean;
  removed: string[];
  preservedDirty: string[];
}
