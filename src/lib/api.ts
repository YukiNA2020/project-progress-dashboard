import type {
  Project,
  ProjectDetailData,
  ProjectInput,
  ProviderInput,
  ProviderSettings,
  ProviderTest,
  ScanRun,
} from '../types'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail = body?.detail
    const message = Array.isArray(detail)
      ? detail.map((item: { msg: string }) => item.msg).join('；')
      : detail || `请求失败 (${response.status})`
    throw new Error(message)
  }
  return response.json() as Promise<T>
}

export const api = {
  listProjects: (includeArchived: boolean) =>
    request<Project[]>(`/api/projects?include_archived=${includeArchived}`),

  createProject: (payload: ProjectInput) =>
    request<Project>('/api/projects', { method: 'POST', body: JSON.stringify(payload) }),

  updateProject: (id: string, payload: ProjectInput) =>
    request<Project>(`/api/projects/${id}`, { method: 'PUT', body: JSON.stringify(payload) }),

  setArchived: (id: string, archived: boolean) =>
    request<Project>(`/api/projects/${id}/archive?archived=${archived}`, { method: 'PUT' }),

  projectDetail: (id: string) => request<ProjectDetailData>(`/api/projects/${id}/detail`),

  latestScan: () => request<{ run: ScanRun | null }>('/api/scan/latest'),

  scan: () => request<ScanRun>('/api/scan', { method: 'POST' }),

  decide: (pendingId: number, decision: 'accept' | 'dismiss') =>
    request<{ id: number; status: string }>(`/api/pending/${pendingId}/decision`, {
      method: 'POST',
      body: JSON.stringify({ decision }),
    }),

  getProvider: () => request<ProviderSettings>('/api/provider'),

  saveProvider: (payload: ProviderInput) =>
    request<ProviderSettings>('/api/provider', { method: 'PUT', body: JSON.stringify(payload) }),

  testProvider: (payload?: ProviderInput) =>
    request<ProviderTest>('/api/provider/test', {
      method: 'POST',
      body: JSON.stringify(payload ?? {}),
    }),
}
