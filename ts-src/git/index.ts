export {
  listLocalBranches,
  getCurrentBranch,
  branchExists,
  remoteBranchExists,
  type BranchListResult,
} from './branch.js';

export { WorktreeManager } from './worktree.js';

export {
  materializeRemoteBranch,
  fetchRemote,
  cloneRepository,
  checkRepositoryAccess,
  type AccessCheckResult,
} from './clone.js';
