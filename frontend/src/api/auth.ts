export interface SessionInfo {
  authenticated: boolean;
  username?: string;
  email?: string;
  roles?: string[];
}


export const login = (): void => {
  const returnTo = window.location.origin;
  window.location.href = `/auth/login?return_to=${encodeURIComponent(returnTo)}`;
};

export const logout = async (): Promise<void> => {
  await fetch(`/auth/logout`, {
    method: 'POST',
    credentials: 'include',
  });
  window.location.reload();
};

export const getSession = async (): Promise<SessionInfo> => {
  const response = await fetch(`/auth/me`, {
    method: 'GET',
    credentials: 'include',
  });

  if (!response.ok) {
    return { authenticated: false };
  }

  return response.json();
};

export const downloadReport = async (): Promise<void> => {
  const response = await fetch(`/reports`, {
    method: 'GET',
    credentials: 'include',
  });

  if (response.status === 401) {
    throw new Error('Not authenticated');
  }

  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }

  const contentType = response.headers.get('Content-Type') || '';

  if (contentType.includes('application/json')) {
    const data = await response.json();
    if (data.report_url) {
      const anchor = document.createElement('a');
      anchor.href = data.report_url;
      anchor.download = '';
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      return;
    }
    throw new Error('No report URL in response');
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