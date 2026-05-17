/** Shared learner id with TacticalDuel (same MemPalace / profile namespace). */

import { resolveLearnerId as resolveFromGameAuth } from "./gameAuth";

const STORAGE_KEY = "game_user_id";

export function getLearnerId(): string {
  const fromAuth = resolveFromGameAuth();
  if (fromAuth) return fromAuth;
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) return stored;
  } catch {
    /* ignore */
  }
  const id = `user_${Date.now()}_${Math.floor(Math.random() * 100000)}`;
  try {
    localStorage.setItem(STORAGE_KEY, id);
  } catch {
    /* ignore */
  }
  return id;
}

export function setLearnerId(learnerId: string): void {
  const v = learnerId.trim();
  if (!v) return;
  try {
    localStorage.setItem(STORAGE_KEY, v);
  } catch {
    /* ignore */
  }
}
