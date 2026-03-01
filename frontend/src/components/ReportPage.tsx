import React, { useEffect, useState } from 'react';
import { downloadReport, getSession, login, logout } from '../api/auth';

const ReportPage: React.FC = () => {
  const [initialized, setInitialized] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [username, setUsername] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>('');

  useEffect(() => {
    const loadSession = async () => {
      try {
        const session = await getSession();
        setAuthenticated(session.authenticated);
        setUsername(session.username || '');
      } catch (err) {
        setAuthenticated(false);
        setError(err instanceof Error ? err.message : 'Unable to check session');
      } finally {
        setInitialized(true);
      }
    };

    void loadSession();
  }, []);

  const handleDownload = async () => {
    try {
      setLoading(true);
      setError('');
      await downloadReport();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
      setAuthenticated(false);
    } finally {
      setLoading(false);
    }
  };

  if (!initialized) {
    return <div className="p-8 text-lg">Loading...</div>;
  }

  if (!authenticated) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="bg-white rounded-lg shadow-md p-8 w-full max-w-md text-center">
          <h1 className="text-2xl font-bold mb-6">Usage Reports</h1>
          <button
            onClick={login}
            className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
          >
            Login
          </button>
          {error && (
            <div className="mt-4 text-red-600">
              {error}
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <div className="bg-white rounded-lg shadow-md p-8 w-full max-w-md text-center">
        <h1 className="text-2xl font-bold mb-2">Usage Reports</h1>
        <div className="text-sm text-gray-500 mb-6">
          Logged in as {username || 'user'}
        </div>

        <div className="flex gap-3 justify-center">
          <button
            onClick={handleDownload}
            disabled={loading}
            className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:bg-blue-300"
          >
            {loading ? 'Generating Report...' : 'Download Report'}
          </button>

          <button
            onClick={() => void logout()}
            className="px-4 py-2 bg-gray-200 text-gray-900 rounded hover:bg-gray-300"
          >
            Logout
          </button>
        </div>

        {error && (
          <div className="mt-4 text-red-600">
            {error}
          </div>
        )}
      </div>
    </div>
  );
};

export default ReportPage;