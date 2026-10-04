import { lazy, Suspense, useEffect, useState } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'react-hot-toast';
import { AuthProvider } from './contexts/AuthContext';
import { useAuth } from './contexts/authState';
import { AuthPage } from './pages/AuthPage';
import './App.css';
const Board = lazy(() => import('./components/Board'));
function AppContent({ invitation, onAccepted }: { invitation: string; onAccepted: () => void }) {
  const { user } = useAuth();
  return user ? (
    <Suspense
      fallback={
        <p role="status" className="empty-state">
          Opening workspace…
        </p>
      }
    >
      <Board key={user.id} initialInviteToken={invitation} onInviteAccepted={onAccepted} />
    </Suspense>
  ) : (
    <AuthPage />
  );
}
export default function App() {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: { retry: false, staleTime: 15000 },
          mutations: { retry: false },
        },
      }),
  );
  const [invitation, setInvitation] = useState(
    () =>
      new URLSearchParams(window.location.search).get('invite') ||
      new URLSearchParams(window.location.hash.slice(1)).get('invite') ||
      '',
  );
  useEffect(() => {
    if (invitation) window.history.replaceState(null, '', window.location.pathname);
  }, [invitation]);
  return (
    <QueryClientProvider client={client}>
      <AuthProvider>
        <AppContent invitation={invitation} onAccepted={() => setInvitation('')} />
        <Toaster position="bottom-right" />
      </AuthProvider>
    </QueryClientProvider>
  );
}
