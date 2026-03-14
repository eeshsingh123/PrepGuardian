import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../lib/auth';
import { submitOnboarding } from '../lib/api';

interface OnboardingProps {
  isDarkMode: boolean;
}

export function Onboarding({ isDarkMode }: OnboardingProps) {
  const [name, setName] = useState('');
  const [experience, setExperience] = useState('');
  const [preferences, setPreferences] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const { user, setUser } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user) return;

    setError('');
    setLoading(true);

    try {
      const updated = await submitOnboarding(user.user_id, {
        name,
        experience,
        preferences,
      });
      setUser(updated);
      navigate('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong');
    } finally {
      setLoading(false);
    }
  };

  const dark = isDarkMode;

  const inputClasses = `w-full px-3 py-2.5 rounded-lg border text-sm outline-none transition-colors ${dark
    ? 'bg-[#0a0a0a] border-gray-700 text-white focus:border-gray-500 placeholder-gray-600'
    : 'bg-gray-50 border-gray-200 text-gray-900 focus:border-gray-400 placeholder-gray-400'
  }`;

  return (
    <div className="flex items-center justify-center h-[calc(100vh-73px)]">
      <div className={`w-full max-w-md p-8 rounded-xl border ${dark ? 'bg-[#111] border-gray-800' : 'bg-white border-gray-200'}`}>
        <h2 className={`text-2xl font-semibold mb-1 tracking-tight ${dark ? 'text-white' : 'text-gray-900'}`}>
          Let's Get Started
        </h2>
        <p className={`text-sm mb-6 ${dark ? 'text-gray-500' : 'text-gray-400'}`}>
          Tell us a bit about yourself so we can personalize your experience
        </p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label className={`block text-xs font-medium uppercase tracking-wider mb-1.5 ${dark ? 'text-gray-400' : 'text-gray-500'}`}>
              Name
            </label>
            <input
              id="onboarding-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className={inputClasses}
              placeholder="Your name"
            />
          </div>

          <div>
            <label className={`block text-xs font-medium uppercase tracking-wider mb-1.5 ${dark ? 'text-gray-400' : 'text-gray-500'}`}>
              Experience Level
            </label>
            <input
              id="onboarding-experience"
              type="text"
              value={experience}
              onChange={(e) => setExperience(e.target.value)}
              required
              className={inputClasses}
              placeholder="e.g. 3 years in software engineering"
            />
          </div>

          <div>
            <label className={`block text-xs font-medium uppercase tracking-wider mb-1.5 ${dark ? 'text-gray-400' : 'text-gray-500'}`}>
              What would you like to prepare for?
            </label>
            <textarea
              id="onboarding-preferences"
              value={preferences}
              onChange={(e) => setPreferences(e.target.value)}
              required
              rows={4}
              className={`${inputClasses} resize-none`}
              placeholder="Tell us about your learning goals, topics of interest, preferred style of learning…"
            />
          </div>

          {error && (
            <p className="text-red-400 text-sm">{error}</p>
          )}

          <button
            id="onboarding-submit"
            type="submit"
            disabled={loading}
            className={`w-full py-2.5 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 ${dark
              ? 'bg-white text-black hover:bg-gray-200'
              : 'bg-black text-white hover:bg-gray-800'
            }`}
          >
            {loading ? 'Saving…' : 'Continue'}
          </button>
        </form>
      </div>
    </div>
  );
}
