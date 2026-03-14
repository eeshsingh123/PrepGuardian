import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../lib/auth';
import { login, signup } from '../lib/api';

interface LoginProps {
  isDarkMode: boolean;
}

export function Login({ isDarkMode }: LoginProps) {
  const [isSignup, setIsSignup] = useState(true);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const { setUser } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const user = isSignup
        ? await signup({ username, password })
        : await login({ username, password });

      setUser(user);
      navigate(user.is_onboarded ? '/' : '/onboarding');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong');
    } finally {
      setLoading(false);
    }
  };

  const dark = isDarkMode;

  return (
    <div className="flex items-center justify-center h-[calc(100vh-73px)]">
      <div className={`w-full max-w-sm p-8 rounded-xl border ${dark ? 'bg-[#111] border-gray-800' : 'bg-white border-gray-200'}`}>
        <h2 className={`text-2xl font-semibold mb-1 tracking-tight ${dark ? 'text-white' : 'text-gray-900'}`}>
          {isSignup ? 'Create Account' : 'Welcome Back'}
        </h2>
        <p className={`text-sm mb-6 ${dark ? 'text-gray-500' : 'text-gray-400'}`}>
          {isSignup ? 'Sign up to start using PrepGuardian' : 'Log in to continue'}
        </p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label className={`block text-xs font-medium uppercase tracking-wider mb-1.5 ${dark ? 'text-gray-400' : 'text-gray-500'}`}>
              Username
            </label>
            <input
              id="login-username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              minLength={3}
              className={`w-full px-3 py-2.5 rounded-lg border text-sm outline-none transition-colors ${dark
                ? 'bg-[#0a0a0a] border-gray-700 text-white focus:border-gray-500 placeholder-gray-600'
                : 'bg-gray-50 border-gray-200 text-gray-900 focus:border-gray-400 placeholder-gray-400'
              }`}
              placeholder="Enter username"
            />
          </div>

          <div>
            <label className={`block text-xs font-medium uppercase tracking-wider mb-1.5 ${dark ? 'text-gray-400' : 'text-gray-500'}`}>
              Password
            </label>
            <input
              id="login-password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={4}
              className={`w-full px-3 py-2.5 rounded-lg border text-sm outline-none transition-colors ${dark
                ? 'bg-[#0a0a0a] border-gray-700 text-white focus:border-gray-500 placeholder-gray-600'
                : 'bg-gray-50 border-gray-200 text-gray-900 focus:border-gray-400 placeholder-gray-400'
              }`}
              placeholder="Enter password"
            />
          </div>

          {error && (
            <p className="text-red-400 text-sm">{error}</p>
          )}

          <button
            id="login-submit"
            type="submit"
            disabled={loading}
            className={`w-full py-2.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 ${dark
              ? 'bg-white text-black hover:bg-gray-200'
              : 'bg-black text-white hover:bg-gray-800'
            }`}
          >
            {loading ? 'Please wait…' : (isSignup ? 'Sign Up' : 'Log In')}
          </button>
        </form>

        <p className={`text-sm text-center mt-5 ${dark ? 'text-gray-500' : 'text-gray-400'}`}>
          {isSignup ? 'Already have an account?' : "Don't have an account?"}{' '}
          <button
            id="login-toggle-mode"
            onClick={() => { setIsSignup(!isSignup); setError(''); }}
            className={`font-medium transition-colors ${dark ? 'text-white hover:text-gray-300' : 'text-black hover:text-gray-600'}`}
          >
            {isSignup ? 'Log In' : 'Sign Up'}
          </button>
        </p>
      </div>
    </div>
  );
}
