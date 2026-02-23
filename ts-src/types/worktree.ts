export interface WorktreeAssignment {
  pane: number;
  repoPath: string;
  branch: string;
}

export interface ManagedWorktree {
  pane: number;
  repoPath: string;
  branch: string;
  path: string;
}

export function createWorktreeAssignment(
  pane: number,
  repoPath: string,
  branch: string
): WorktreeAssignment {
  return { pane, repoPath, branch };
}

export function createManagedWorktree(
  assignment: WorktreeAssignment,
  path: string
): ManagedWorktree {
  return {
    pane: assignment.pane,
    repoPath: assignment.repoPath,
    branch: assignment.branch,
    path,
  };
}
