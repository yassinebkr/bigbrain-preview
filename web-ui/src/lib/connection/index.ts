// Connection factory — picks the adapter for the backend.
// Default: BigBrain. Set localStorage aplot_backend = 'scratchy' to target
// a Scratchy/OpenClaw gateway with the same UI (docs/WEBUI-APLOT-PORT.md).

import type { ConnectionLike } from './types';
import { BigBrainConnection } from './bigbrain';
import { ScratchyConnection } from './scratchy';

export function createConnection(): ConnectionLike {
  let backend = 'bigbrain';
  try {
    backend = localStorage.getItem('aplot_backend') || 'bigbrain';
  } catch (e) { /* storage unavailable */ }
  if (backend === 'scratchy') {
    return new ScratchyConnection();
  }
  return new BigBrainConnection();
}

export { BigBrainConnection, ScratchyConnection };
export type { ConnectionCallbacks, ConnectionLike } from './types';
