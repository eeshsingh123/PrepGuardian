import { useState, useEffect } from 'react';
import { Routes, Route, Navigate, Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from './lib/auth';
import { VoiceAgent } from './components/VoiceAgent';
import { Login } from './components/Login';
import { Onboarding } from './components/Onboarding';
import { Transcripts } from './components/Transcripts';
import { Moon, Sun, Mic, ScrollText, LogOut } from 'lucide-react';
import { logoutSession } from './lib/api';
import './App.css';

function App() {
  const [isDarkMode, setIsDarkMode] = useState(true);
  const { user, isLoading, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    if (isDarkMode) {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
  }, [isDarkMode]);

  // Pages that don't need the full nav bar
  const isAuthPage = location.pathname === '/login' || location.pathname === '/signup';
  const isOnboardingPage = location.pathname === '/onboarding';
  const authRedirectPath = user?.is_onboarded ? '/' : '/onboarding';

  const handleLogout = async () => {
    try {
      await logoutSession();
    } finally {
      logout();
      navigate('/login', { replace: true });
    }
  };

  const authLoading = (
    <div className="flex h-[calc(100vh-73px)] items-center justify-center">
      <div className={`rounded-lg border px-5 py-4 text-sm ${isDarkMode ? 'border-gray-800 bg-[#111] text-gray-400' : 'border-gray-200 bg-white text-gray-500'}`}>
        Welcome Back!
      </div>
    </div>
  );

  return (
    <div className={`min-h-screen transition-colors duration-300 ${isDarkMode ? 'bg-[#0a0a0a] text-gray-100' : 'bg-gray-50 text-gray-900'} font-sans`}>
      <header className={`border-b px-6 py-4 ${isDarkMode ? 'bg-[#0a0a0a] border-gray-800' : 'bg-white border-gray-200'}`}>
        <div className="max-w-[1600px] mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className={`w-8 h-8 flex items-center justify-center font-bold text-lg tracking-tighter ${isDarkMode ? 'bg-white text-black' : 'bg-black text-white'}`}>
              PG
            </div>
            <h1 className="text-xl font-medium tracking-tight">
              PrepGuardian
            </h1>
          </div>
          <div className="flex items-center gap-3">
            {/* Navigation links shown only when logged in and past onboarding */}
            {user && !isAuthPage && !isOnboardingPage && (
              <>
                <Link
                  to="/"
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium uppercase tracking-wider transition-colors ${location.pathname === '/'
                    ? (isDarkMode ? 'bg-gray-800 text-white' : 'bg-gray-200 text-black')
                    : (isDarkMode ? 'text-gray-500 hover:text-gray-300' : 'text-gray-400 hover:text-gray-600')
                    }`}
                >
                  <Mic className="w-3.5 h-3.5" />
                  Agent
                </Link>
                <Link
                  to="/transcripts"
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium uppercase tracking-wider transition-colors ${location.pathname === '/transcripts'
                    ? (isDarkMode ? 'bg-gray-800 text-white' : 'bg-gray-200 text-black')
                    : (isDarkMode ? 'text-gray-500 hover:text-gray-300' : 'text-gray-400 hover:text-gray-600')
                    }`}
                >
                  <ScrollText className="w-3.5 h-3.5" />
                  Transcripts
                </Link>
              </>
            )}
            <button
              onClick={() => setIsDarkMode(!isDarkMode)}
              className={`p-2 rounded-md border transition-colors ${isDarkMode ? 'border-gray-700 hover:bg-gray-800 text-gray-400 hover:text-white' : 'border-gray-200 hover:bg-gray-100 text-gray-500 hover:text-black'}`}
              aria-label="Toggle theme"
            >
              {isDarkMode ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            </button>
            {user && !isAuthPage && (
              <button
                onClick={() => void handleLogout()}
                className={`p-2 rounded-md border transition-colors ${isDarkMode ? 'border-gray-700 hover:bg-gray-800 text-gray-400 hover:text-white' : 'border-gray-200 hover:bg-gray-100 text-gray-500 hover:text-black'}`}
                aria-label="Logout"
                title="Logout"
              >
                <LogOut className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      </header>

      <main className="max-w-[1600px] mx-auto w-full px-4 sm:px-6 lg:px-8">
        <Routes>
          <Route path="/login" element={
            isLoading ? authLoading : user ? <Navigate to={authRedirectPath} replace /> : <Login isDarkMode={isDarkMode} mode="login" />
          } />
          <Route path="/signup" element={
            isLoading ? authLoading : user ? <Navigate to={authRedirectPath} replace /> : <Login isDarkMode={isDarkMode} mode="signup" />
          } />
          <Route path="/onboarding" element={
            isLoading ? authLoading : !user ? <Navigate to="/login" replace /> : <Onboarding isDarkMode={isDarkMode} />
          } />
          <Route path="/" element={
            isLoading ? authLoading :
              !user ? <Navigate to="/login" replace /> :
                !user.is_onboarded ? <Navigate to="/onboarding" replace /> :
                  <div className="h-[calc(100vh-73px)]"><VoiceAgent isDarkMode={isDarkMode} onSessionEnded={() => navigate('/transcripts')} /></div>
          } />
          <Route path="/transcripts" element={
            isLoading ? authLoading : !user ? <Navigate to="/login" replace /> : <Transcripts isDarkMode={isDarkMode} />
          } />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
