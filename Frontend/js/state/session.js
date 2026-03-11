const SESSION_KEY = "jaila_auth_user";
const ACTIVE_TAB_KEY = "jaila_active_tab";
const CHAT_SESSION_KEY = "jaila_chat_session_id";

export function getActiveUser() {
  try {
    return localStorage.getItem(SESSION_KEY);
  } catch (_err) {
    return null;
  }
}

export function setActiveUser(user) {
  try {
    localStorage.setItem(SESSION_KEY, user);
  } catch (_err) {
    // Ignorer localStorage-fejl.
  }
}

export function clearActiveUser() {
  try {
    localStorage.removeItem(SESSION_KEY);
  } catch (_err) {
    // Ignorer localStorage-fejl.
  }
}

export function getActiveTab(defaultTab) {
  try {
    const raw = localStorage.getItem(ACTIVE_TAB_KEY);
    if (raw === "analyse" || raw === "sagsbehandling" || raw === "chat") {
      return raw;
    }
  } catch (_err) {
    // Ignorer localStorage-fejl.
  }
  return defaultTab;
}

export function setActiveTab(tabId) {
  try {
    localStorage.setItem(ACTIVE_TAB_KEY, tabId);
  } catch (_err) {
    // Ignorer localStorage-fejl.
  }
}

function createSessionId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID().replace(/-/g, "");
  }
  return String(Date.now()) + String(Math.floor(Math.random() * 1_000_000));
}

export function getOrCreateChatSessionId() {
  try {
    const existing = localStorage.getItem(CHAT_SESSION_KEY);
    if (existing && /^[a-zA-Z0-9_-]{8,80}$/.test(existing)) {
      return existing;
    }
    const created = createSessionId();
    localStorage.setItem(CHAT_SESSION_KEY, created);
    return created;
  } catch (_err) {
    return createSessionId();
  }
}

export function resetChatSessionId() {
  const created = createSessionId();
  try {
    localStorage.setItem(CHAT_SESSION_KEY, created);
  } catch (_err) {
    // Ignorer localStorage-fejl.
  }
  return created;
}

export function setChatSessionId(sessionId) {
  const value = String(sessionId || "").trim();
  if (!/^[a-zA-Z0-9_-]{8,80}$/.test(value)) {
    return null;
  }
  try {
    localStorage.setItem(CHAT_SESSION_KEY, value);
  } catch (_err) {
    // Ignorer localStorage-fejl.
  }
  return value;
}
