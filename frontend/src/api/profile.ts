import { isProfileDashboardData, type ProfileDashboardData } from '../types/profile';
import { API_BASE_URL, notifyAuthInvalidFromError, readApiError } from './http';

export async function fetchProfileDashboard(token: string): Promise<ProfileDashboardData> {
  const response = await fetch(`${API_BASE_URL}/api/profile/dashboard`, {
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  if (!response.ok) {
    const error = await readApiError(response);
    notifyAuthInvalidFromError(response.status, error);
    throw new Error((typeof error?.detail === 'string' ? error.detail : null) ?? '画像数据加载失败');
  }

  const payload = await response.json();
  if (!isProfileDashboardData(payload)) {
    throw new Error('画像数据格式不正确');
  }

  return payload;
}
