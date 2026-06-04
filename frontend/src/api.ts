import type { AirSensorCurrent, AirSensorSettings, BackupCreateResponse, BackupInfo, CurrentValuesApiSettings, Device, FinanceSettings, KindleDisplaySettings, Measurement, HistorySeries, HistoryTotals, PublicDashboardSettings, RetentionSettings, ResetValuesResponse, SimulationSettings, Summary, UiSettings, User } from './types';

type RuntimeConfig = {
  API_BASE_URL?: string;
};

function getRuntimeConfig(): RuntimeConfig {
  return ((window as unknown as { __BPSTRACKER_CONFIG__?: RuntimeConfig }).__BPSTRACKER_CONFIG__) || {};
}

function isLoopbackHost(hostname: string): boolean {
  return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1' || hostname === '0.0.0.0';
}

function resolveApiBase(): string {
  const runtimeConfig = getRuntimeConfig();
  const configured = String(runtimeConfig.API_BASE_URL || import.meta.env.VITE_API_BASE_URL || '').trim();
  // Default/recommended mode: Same-Origin. The browser calls /api/... on the frontend host/port.
  // nginx inside the frontend container proxies /api/ to http://backend:8000.
  // This avoids localhost/LAN/CORS problems completely.
  if (!configured || ['auto', 'same-origin', 'relative'].includes(configured.toLowerCase())) {
    return '';
  }

  // Backwards compatibility: values like ":8000" or "localhost:8000" from older deployments
  // are treated as auto/same-origin instead of producing invalid URLs.
  if (configured.startsWith(':') || configured.includes('localhost') || configured.includes('127.0.0.1')) {
    const frontendHost = window.location.hostname;
    if (!isLoopbackHost(frontendHost)) return '';
  }

  try {
    const url = new URL(configured);
    const frontendHost = window.location.hostname;
    if (isLoopbackHost(url.hostname) && !isLoopbackHost(frontendHost)) return '';
    return configured.replace(/\/+$/, '');
  } catch {
    return '';
  }
}

const API_BASE = resolveApiBase();

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function clearLegacyTokenStorage(): void {
  try {
    localStorage.removeItem('bpstracker-token');
  } catch {
    // ignore unavailable storage
  }
}

clearLegacyTokenStorage();

function historyQuery(hours: number): string {
  const end = new Date();
  const start = new Date(end.getTime() - hours * 60 * 60 * 1000);
  const limit = historyLimit(hours);
  return `start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}&limit=${limit}`;
}

function historyLimit(hours: number): number {
  if (hours <= 24) return 50000;
  if (hours <= 168) return 150000;
  return 300000;
}

export function getToken(): string | null {
  // Access tokens are stored in an HttpOnly cookie and are intentionally not readable by JavaScript.
  return null;
}

export function setToken(_token: string | null): void {
  // Kept as a compatibility shim for older call sites while clearing any pre-v0.7.3 localStorage JWT.
  clearLegacyTokenStorage();
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers || {});
  if (!headers.has('Content-Type') && options.body) headers.set('Content-Type', 'application/json');
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers, credentials: 'include' });
  if (!response.ok) {
    let message = response.statusText;
    try {
      const data = await response.json();
      message = data.detail || message;
    } catch {
      // ignore
    }
    throw new ApiError(response.status, message);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

async function download(path: string): Promise<Blob> {
  const response = await fetch(`${API_BASE}${path}`, { credentials: 'include' });
  if (!response.ok) throw new ApiError(response.status, response.statusText);
  return response.blob();
}

export const api = {
  installStatus: () => request<{ install_required: boolean }>('/api/install/status'),
  installAdmin: (username: string, password: string, confirm_password: string) => request<{ ok: boolean }>('/api/install/admin', { method: 'POST', body: JSON.stringify({ username, password, confirm_password }) }),
  login: (username: string, password: string) => request<{ access_token?: string; requires_2fa: boolean; challenge_token?: string }>('/api/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
  verify2fa: (challenge_token: string, code: string) => request<{ access_token?: string; requires_2fa?: boolean }>('/api/auth/2fa/verify', { method: 'POST', body: JSON.stringify({ challenge_token, code }) }),
  logout: () => request<void>('/api/auth/logout', { method: 'POST' }),
  me: () => request<User>('/api/auth/me'),
  setup2fa: () => request<{ secret: string; provisioning_uri: string }>('/api/auth/2fa/setup', { method: 'POST' }),
  enable2fa: (code: string) => request<User & { recovery_codes?: string[] }>('/api/auth/2fa/enable', { method: 'POST', body: JSON.stringify({ code }) }),
  disable2fa: () => request<User>('/api/auth/2fa/disable', { method: 'POST' }),
  regenerateRecoveryCodes: () => request<{ recovery_codes: string[] }>('/api/auth/2fa/recovery-codes', { method: 'POST' }),
  users: () => request<User[]>('/api/users'),
  updateUserCredentials: (role: 'admin' | 'viewer', payload: { username: string; password?: string | null }) => request<User>(`/api/users/${role}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  uiSettings: () => request<UiSettings>('/api/settings/ui'),
  updateUiSettings: (payload: UiSettings) => request<UiSettings>('/api/settings/ui', { method: 'PUT', body: JSON.stringify(payload) }),
  financeSettings: () => request<FinanceSettings>('/api/settings/finance'),
  updateFinanceSettings: (payload: FinanceSettings) => request<FinanceSettings>('/api/settings/finance', { method: 'PUT', body: JSON.stringify(payload) }),
  retentionSettings: () => request<RetentionSettings>('/api/settings/retention'),
  updateRetentionSettings: (payload: RetentionSettings) => request<RetentionSettings>('/api/settings/retention', { method: 'PUT', body: JSON.stringify(payload) }),
  kindleDisplaySettings: () => request<KindleDisplaySettings>('/api/settings/kindle-display'),
  updateKindleDisplaySettings: (payload: KindleDisplaySettings) => request<KindleDisplaySettings>('/api/settings/kindle-display', { method: 'PUT', body: JSON.stringify(payload) }),
  publicDashboardSettings: () => request<PublicDashboardSettings>('/api/settings/public-dashboard'),
  updatePublicDashboardSettings: (settings: PublicDashboardSettings) => request<PublicDashboardSettings>('/api/settings/public-dashboard', { method: 'PUT', body: JSON.stringify(settings) }),
  currentValuesApiSettings: () => request<CurrentValuesApiSettings>('/api/settings/current-values-api'),
  updateCurrentValuesApiSettings: (payload: CurrentValuesApiSettings) => request<CurrentValuesApiSettings>('/api/settings/current-values-api', { method: 'PUT', body: JSON.stringify(payload) }),
  simulationSettings: () => request<SimulationSettings>('/api/settings/simulation'),
  updateSimulationSettings: (payload: SimulationSettings) => request<SimulationSettings>('/api/settings/simulation', { method: 'PUT', body: JSON.stringify(payload) }),
  airSensorSettings: () => request<AirSensorSettings>('/api/settings/air-sensor'),
  updateAirSensorSettings: (payload: AirSensorSettings) => request<AirSensorSettings>('/api/settings/air-sensor', { method: 'PUT', body: JSON.stringify(payload) }),
  airSensorCurrent: () => request<AirSensorCurrent>('/api/settings/air-sensor/current'),
  devices: () => request<Device[]>('/api/devices'),
  createDevice: (payload: Partial<Device> & { password?: string | null }) => request<Device>('/api/devices', { method: 'POST', body: JSON.stringify(payload) }),
  updateDevice: (id: number, payload: Partial<Device> & { password?: string | null; clear_password?: boolean }) => request<Device>(`/api/devices/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  deleteDevice: (id: number) => request<{ ok: boolean }>(`/api/devices/${id}`, { method: 'DELETE' }),
  testDevice: (id: number) => request<{ ok: boolean; message: string; detected_type?: string; generation?: string; model?: string; raw?: unknown }>(`/api/devices/${id}/test`, { method: 'POST' }),
  pollNow: (id: number) => request<Device>(`/api/devices/${id}/poll`, { method: 'POST' }),
  latest: () => request<Measurement[]>('/api/measurements/latest'),
  summary: () => request<Summary>('/api/measurements/summary'),
  publicSummary: () => request<Summary>('/api/measurements/public/summary'),
  publicAirSensorCurrent: () => request<AirSensorCurrent>('/api/settings/public/air-sensor/current'),
  currentValues: () => request<Record<string, unknown>>('/api/current-values'),
  history: (hours: number) => request<Measurement[]>(`/api/measurements/history?${historyQuery(hours)}`),
  historyTotals: (hours: number) => request<HistoryTotals>(`/api/measurements/history/totals?${historyQuery(hours)}`),
  historySeries: (hours: number) => request<HistorySeries>(`/api/measurements/history/series?${historyQuery(hours)}`),
  exportCsv: () => download('/api/measurements/export.csv'),
  backups: () => request<BackupInfo[]>('/api/backups'),
  createBackup: (password: string, confirm_password: string) => request<BackupCreateResponse>('/api/backups/create', { method: 'POST', body: JSON.stringify({ password, confirm_password }) }),
  downloadBackup: (filename: string) => download(`/api/backups/download/${encodeURIComponent(filename)}`),
  deleteBackup: (filename: string) => request<{ ok: boolean }>(`/api/backups/${encodeURIComponent(filename)}`, { method: 'DELETE' }),
  resetValues: (confirmation: string) => request<ResetValuesResponse>('/api/maintenance/reset-values', { method: 'POST', body: JSON.stringify({ confirmation }) }),
  kindlePreviewUrl: () => `${API_BASE}/api/kindle/display.png`
};
