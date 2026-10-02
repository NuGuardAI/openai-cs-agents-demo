export function apiUrl(path: string) {
  const base = (process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8250").replace(/\/$/, "");
  return `${base}${path}`;
}

// Include Azure's ARR affinity cookie on every backend request so ChatKit and
// legacy login/conversation state stay on the same application instance.
export const apiFetch: typeof fetch = (input, init) =>
  fetch(input, { ...init, credentials: "include" });

// Fetch ChatKit thread state for the Agent panel
export async function fetchThreadState(threadId: string) {
  try {
    const res = await apiFetch(apiUrl(`/chatkit/state?thread_id=${encodeURIComponent(threadId)}`));
    if (!res.ok) throw new Error(`State API error: ${res.status}`);
    return res.json();
  } catch (err) {
    console.error("Error fetching thread state:", err);
    return null;
  }
}

export async function fetchBootstrapState() {
  try {
    const res = await apiFetch(apiUrl("/chatkit/bootstrap"));
    if (!res.ok) throw new Error(`Bootstrap API error: ${res.status}`);
    return res.json();
  } catch (err) {
    console.error("Error bootstrapping state:", err);
    return null;
  }
}

// Helper to call the server
export async function callLoginAPI(username: string, password: string) {
  try {
    const url = apiUrl("/login");
    const res = await apiFetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (res.status === 401) return null;
    if (!res.ok) throw new Error(`Login API error: ${res.status}`);
    return res.json();
  } catch (err) {
    console.error("Error logging in:", err);
    return null;
  }
}

export async function callLogoutAPI(token: string) {
  try {
    const url = apiUrl("/logout");
    await apiFetch(url, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
  } catch {
    // best-effort
  }
}

export async function callChatAPI(message: string, conversationId: string, token?: string) {
  try {
    const url = apiUrl("/chat");
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const res = await apiFetch(url, {
      method: "POST",
      headers,
      body: JSON.stringify({ conversation_id: conversationId, message }),
    });
    if (!res.ok) throw new Error(`Chat API error: ${res.status}`);
    return res.json();
  } catch (err) {
    console.error("Error sending message:", err);
    return null;
  }
}
