export interface SessionInfo {
  authenticated: boolean;
  username?: string;
  email?: string;
  roles?: string[];
}

const AUTH_URL = '';

export const login = (): void => {
  const returnTo = window.location.origin;
  window.location.href = `${AUTH_URL}/auth/login?return_to=${encodeURIComponent(returnTo)}`;
};

export const logout = async (): Promise<void> => {
  await fetch(`${AUTH_URL}/auth/logout`, {
    method: 'POST',
    credentials: 'include',
  });
  window.location.reload();
};

export const getSession = async (): Promise<SessionInfo> => {
  const response = await fetch(`${AUTH_URL}/auth/me`, {
    method: 'GET',
    credentials: 'include',
  });

  if (!response.ok) {
    return { authenticated: false };
  }

  return response.json();
};

export const downloadReport = async (): Promise<void> => {
  const response = await fetch(`${AUTH_URL}/reports`, {
    method: 'GET',
    credentials: 'include',
  });

  if (response.status === 401) {
    throw new Error('Not authenticated');
  }

  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }

  const blob = await response.blob();
  const disposition = response.headers.get('Content-Disposition');
  const filenameMatch = disposition?.match(/filename="?([^"]+)"?/);
  const filename = filenameMatch?.[1] || 'report.bin';

  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
};