/**
 * Shared auth with TacticalDuel — same localStorage keys and learner id (uid).
 */

export type GameUser = {
  uid: string;
  displayName: string;
  phoneNumber: string;
  gameName?: string;
};

export type SavedUserAuth = GameUser & {
  lastLogin?: number;
};

const KEYS = {
  currentUser: "currentUser",
  savedUserAuth: "savedUserAuth",
  gameUserId: "game_user_id",
  playerInfo: "playerInfo",
} as const;

export function getSavedQuickAuth(): SavedUserAuth | null {
  try {
    const raw = localStorage.getItem(KEYS.savedUserAuth);
    if (!raw) return null;
    const data = JSON.parse(raw) as SavedUserAuth;
    if (!data?.uid) return null;
    return {
      ...data,
      gameName: data.gameName || data.displayName,
    };
  } catch {
    return null;
  }
}

export function getCurrentUser(): GameUser | null {
  try {
    const raw = localStorage.getItem(KEYS.currentUser);
    if (!raw) return null;
    const data = JSON.parse(raw) as GameUser;
    if (!data?.uid) return null;
    return data;
  } catch {
    return null;
  }
}

export function resolveLearnerId(): string {
  const saved = getSavedQuickAuth();
  if (saved?.uid) return saved.uid;
  const cur = getCurrentUser();
  if (cur?.uid) return cur.uid;
  try {
    const pi = localStorage.getItem(KEYS.playerInfo);
    if (pi) {
      const p = JSON.parse(pi) as { userUid?: string; id?: string };
      if (p.userUid) return p.userUid;
      if (p.id) return p.id;
    }
  } catch {
    /* ignore */
  }
  try {
    return localStorage.getItem(KEYS.gameUserId) || "";
  } catch {
    return "";
  }
}

/** Persist session exactly like game LoginModal + App userUid wiring. */
export function persistGameSession(user: GameUser): void {
  const gameName = user.gameName || user.displayName;
  const payload: SavedUserAuth = {
    ...user,
    displayName: user.displayName,
    gameName,
    lastLogin: Date.now(),
  };
  localStorage.setItem(KEYS.currentUser, JSON.stringify({ ...user, displayName: user.displayName }));
  localStorage.setItem(KEYS.savedUserAuth, JSON.stringify(payload));
  localStorage.setItem(KEYS.gameUserId, user.uid);

  try {
    const existing = localStorage.getItem(KEYS.playerInfo);
    const base = existing ? (JSON.parse(existing) as Record<string, unknown>) : {};
    localStorage.setItem(
      KEYS.playerInfo,
      JSON.stringify({
        ...base,
        userUid: user.uid,
        id: user.uid,
        gameName,
        displayName: user.displayName,
      })
    );
  } catch {
    localStorage.setItem(
      KEYS.playerInfo,
      JSON.stringify({
        userUid: user.uid,
        id: user.uid,
        gameName,
        displayName: user.displayName,
      })
    );
  }
}

export function clearGameSession(): void {
  localStorage.removeItem(KEYS.savedUserAuth);
  localStorage.removeItem(KEYS.currentUser);
}

export function logoutKeepLearnerId(): void {
  clearGameSession();
}

const GAME_API = import.meta.env.VITE_GAME_API_URL || "";

export async function loginWithPhone(phoneNumber: string, password: string): Promise<GameUser> {
  const res = await fetch(`${GAME_API}/api/user/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phoneNumber, password }),
  });
  const data = (await res.json()) as {
    success?: boolean;
    message?: string;
    user?: { uid: string; displayName: string; phoneNumber: string };
  };
  if (!res.ok || !data.user) {
    throw new Error(data.message || "登录失败");
  }
  return {
    uid: data.user.uid,
    displayName: data.user.displayName,
    phoneNumber: data.user.phoneNumber,
    gameName: data.user.displayName,
  };
}

export async function registerUser(
  phoneNumber: string,
  password: string,
  displayName: string
): Promise<GameUser> {
  const res = await fetch(`${GAME_API}/api/user/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phoneNumber, password, displayName }),
  });
  const data = (await res.json()) as {
    success?: boolean;
    message?: string;
    user?: { uid: string; displayName: string; phoneNumber: string };
  };
  if (!res.ok || !data.user) {
    throw new Error(data.message || "注册失败");
  }
  return {
    uid: data.user.uid,
    displayName: data.user.displayName,
    phoneNumber: data.user.phoneNumber,
    gameName: data.user.displayName,
  };
}
