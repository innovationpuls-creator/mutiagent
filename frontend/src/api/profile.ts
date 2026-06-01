import type { ProfileDashboardData } from '../types/profile';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';

interface ApiErrorResponse {
  detail?: string;
}

export async function fetchProfileDashboard(token: string): Promise<ProfileDashboardData> {
  const response = await fetch(`${API_BASE_URL}/api/profile/dashboard`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    const error = (await response.json().catch(() => null)) as ApiErrorResponse | null;
    throw new Error(error?.detail ?? '画像数据加载失败');
  }

  return (await response.json()) as ProfileDashboardData;
}
