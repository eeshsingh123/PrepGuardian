import type { AuthSession, UserData } from './session';

const AUTH_STATE_KEY = 'prepguardian.auth.state';
const AUTH_STATE_ACTIVE = 'active';
const AUTH_STATE_SIGNED_OUT = 'signed-out';

function isLoopbackHost(hostname: string): boolean {
  return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '[::1]' || hostname === '::1';
}

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, '');
}

function resolveApiBaseUrl(): string {
  const configuredUrl = import.meta.env.VITE_API_BASE_URL as string | undefined;
  const defaultUrl = typeof window === 'undefined'
    ? 'http://localhost:8000'
    : `${window.location.protocol}//${window.location.hostname}:8000`;
  const rawUrl = trimTrailingSlash(configuredUrl || defaultUrl);

  if (typeof window === 'undefined') {
    return rawUrl;
  }

  try {
    const apiUrl = new URL(rawUrl);
    const appHostname = window.location.hostname;

    if (isLoopbackHost(appHostname) && isLoopbackHost(apiUrl.hostname)) {
      apiUrl.hostname = appHostname;
    }

    return trimTrailingSlash(apiUrl.toString());
  } catch {
    return rawUrl;
  }
}

const API_BASE_URL = resolveApiBaseUrl();

interface SignupPayload {
  username: string;
  password: string;
}

interface LoginPayload {
  username: string;
  password: string;
}

interface OnboardingPayload {
  name: string;
  experience: string;
  target_company: string;
  target_level: string;
  preferences: string;
}

export type { AuthSession, UserData };

export interface ConversationSummary {
  session_id: string;
  user_id: string;
  started_at: string;
  ended_at: string | null;
  duration_seconds: number;
  turn_count: number;
  preview: string;
}

export interface ConversationTurn {
  role: 'user' | 'agent';
  text: string;
  timestamp: string;
}

export interface ConversationFull {
  session_id: string;
  user_id: string;
  started_at: string;
  ended_at: string | null;
  duration_seconds: number;
  turn_count: number;
  user_turn_count: number;
  agent_turn_count: number;
  turns: ConversationTurn[];
  confidence_data?: {
    scores: Array<{ turn: number; score: number; note: string }>;
    peak_turn: number;
    drop_turn: number;
    average_score: number;
    trend: string;
  } | null;
  radar_data?: {
    pillars: Record<string, number>;
    strongest: string;
    weakest: string;
    avoided: string[];
  } | null;
  market_gap_data?: {
    target_role: string;
    target_company: string;
    target_level: string;
    dimensions: Array<{
      name: string;
      market_bar: number;
      candidate_score: number;
      gap: number;
      verdict: string;
    }>;
    readiness_percentage: number;
    readiness_label: string;
    summary: string;
  } | null;
  report_text?: string | null;
}

let currentAccessToken: string | null = null;
let authListener: ((session: AuthSession | null) => void) | null = null;

function notifyAuthListener(session: AuthSession | null) {
  authListener?.(session);
}

function getStoredAuthState(): string | null {
  try {
    return window.localStorage.getItem(AUTH_STATE_KEY);
  } catch {
    return null;
  }
}

function rememberAuthState(state: typeof AUTH_STATE_ACTIVE | typeof AUTH_STATE_SIGNED_OUT) {
  try {
    window.localStorage.setItem(AUTH_STATE_KEY, state);
  } catch {
    // If storage is unavailable, the HttpOnly cookie still remains the source of truth.
  }
}

function shouldBootstrapFromRefreshCookie(): boolean {
  if (typeof window === 'undefined') {
    return true;
  }

  return getStoredAuthState() !== AUTH_STATE_SIGNED_OUT;
}

export function registerAuthListener(listener: ((session: AuthSession | null) => void) | null) {
  authListener = listener;
}

export function setInMemoryAccessToken(token: string | null) {
  currentAccessToken = token;

  if (typeof window !== 'undefined') {
    rememberAuthState(token ? AUTH_STATE_ACTIVE : AUTH_STATE_SIGNED_OUT);
  }
}

async function parseError(response: Response): Promise<Error> {
  const error = await response.json().catch(() => ({ detail: 'Request failed' }));
  return new Error(error.detail || `HTTP ${response.status}`);
}

async function parseJson<T>(response: Response): Promise<T> {
  return response.json() as Promise<T>;
}

let refreshPromise: Promise<AuthSession | null> | null = null;

async function refreshSessionFromCookie(): Promise<AuthSession | null> {
  if (refreshPromise) {
    return refreshPromise;
  }

  refreshPromise = (async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
      });

      if (!response.ok) {
        currentAccessToken = null;
        rememberAuthState(AUTH_STATE_SIGNED_OUT);
        notifyAuthListener(null);
        return null;
      }

      const session = await parseJson<AuthSession>(response);
      currentAccessToken = session.access_token;
      rememberAuthState(AUTH_STATE_ACTIVE);
      notifyAuthListener(session);
      return session;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

async function request<T>(path: string, options: RequestInit = {}, requiresAuth = true, allowRetry = true): Promise<T> {
  const headers = new Headers(options.headers ?? {});

  if (!headers.has('Content-Type') && options.body) {
    headers.set('Content-Type', 'application/json');
  }

  if (requiresAuth && currentAccessToken) {
    headers.set('Authorization', `Bearer ${currentAccessToken}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
    credentials: 'include',
  });

  if (response.status === 401 && requiresAuth && allowRetry) {
    const refreshedSession = await refreshSessionFromCookie();
    if (refreshedSession) {
      return request<T>(path, options, requiresAuth, false);
    }
  }

  if (!response.ok) {
    throw await parseError(response);
  }

  return parseJson<T>(response);
}

export async function bootstrapAuthSession(): Promise<AuthSession | null> {
  if (!shouldBootstrapFromRefreshCookie()) {
    return null;
  }

  return refreshSessionFromCookie();
}

export async function signup(payload: SignupPayload): Promise<AuthSession> {
  const session = await request<AuthSession>('/auth/signup', {
    method: 'POST',
    body: JSON.stringify(payload),
  }, false);
  currentAccessToken = session.access_token;
  rememberAuthState(AUTH_STATE_ACTIVE);
  return session;
}

export async function login(payload: LoginPayload): Promise<AuthSession> {
  const session = await request<AuthSession>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  }, false);
  currentAccessToken = session.access_token;
  rememberAuthState(AUTH_STATE_ACTIVE);
  return session;
}

export async function logoutSession(): Promise<void> {
  try {
    await request<{ ok: boolean }>('/auth/logout', { method: 'POST' });
  } finally {
    currentAccessToken = null;
    rememberAuthState(AUTH_STATE_SIGNED_OUT);
    notifyAuthListener(null);
  }
}

export async function fetchCurrentUser(): Promise<UserData> {
  return request<UserData>('/auth/me');
}

export async function submitOnboarding(payload: OnboardingPayload): Promise<UserData> {
  return request<UserData>('/users/me/onboarding', {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export async function fetchConversations(): Promise<ConversationSummary[]> {
  return request<ConversationSummary[]>('/conversations/');
}

export async function fetchConversation(sessionId: string): Promise<ConversationFull> {
  return request<ConversationFull>(`/conversations/${sessionId}`);
}

export async function generateInsights(sessionId: string): Promise<void> {
  await request<{ ok: boolean }>(`/conversations/${sessionId}/generate-insights`, { method: 'POST' });
}
