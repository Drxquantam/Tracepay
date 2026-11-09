// Thin wrapper around fetch: adds the base URL and the login token, and turns API error
// responses into an ApiError with the server's plain-language message.

export const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "tracepay.token";

// The token lives in localStorage: simple for a demo. A production app would prefer an
// httpOnly cookie, which page scripts can't read (noted in the README's limitations).
export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable (private mode): the session just won't survive a reload */
  }
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

type Options = {
  method?: "GET" | "POST" | "PUT" | "PATCH";
  body?: unknown;
  headers?: Record<string, string>;
  asText?: boolean;
};

// Called on any 401 so the app can send the user back to the login screen.
let onUnauthorized: () => void = () => {};
export function setUnauthorizedHandler(fn: () => void): void {
  onUnauthorized = fn;
}

export async function api<T>(path: string, opts: Options = {}): Promise<T> {
  const token = getToken();
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      method: opts.method ?? "GET",
      headers: {
        ...(opts.body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...opts.headers,
      },
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
  } catch {
    // status 0 = we never got an answer (offline, server down). For a payment this is the
    // case where the money may or may not have moved, which is why retries reuse the key.
    throw new ApiError(0, "Couldn't reach TracePay. Check your connection.");
  }

  if (res.status === 401 && path !== "/auth/login") onUnauthorized();
  if (!res.ok) {
    let message = `Something went wrong (${res.status})`;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") message = data.detail;
      else if (Array.isArray(data.detail)) message = data.detail[0]?.msg ?? message;
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, message);
  }
  return (opts.asText ? await res.text() : await res.json()) as T;
}
