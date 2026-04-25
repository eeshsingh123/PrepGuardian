import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../lib/auth';
import { submitOnboarding } from '../lib/api';

interface OnboardingProps {
  isDarkMode: boolean;
}

const TARGET_LEVEL_OPTIONS = ['Mid-level', 'Senior', 'Staff+'] as const;

export function Onboarding({ isDarkMode }: OnboardingProps) {
  const { user, setUser } = useAuth();
  const [name, setName] = useState(user?.name ?? '');
  const [experience, setExperience] = useState(user?.experience ?? '');
  const [targetCompany, setTargetCompany] = useState(user?.target_company ?? '');
  const [targetLevel, setTargetLevel] = useState(user?.target_level ?? TARGET_LEVEL_OPTIONS[0]);
  const [preferences, setPreferences] = useState(user?.preferences ?? '');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user) return;

    setError('');
    setLoading(true);

    try {
      const updated = await submitOnboarding({
        name,
        experience,
        target_company: targetCompany,
        target_level: targetLevel,
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
    <div className="flex items-center justify-center min-h-[calc(100vh-73px)] px-4 py-8">
      <div className={`w-full max-w-2xl p-8 rounded-2xl border shadow-[0_18px_60px_-40px_rgba(0,0,0,0.45)] ${dark ? 'bg-[#111] border-gray-800' : 'bg-white border-gray-200'}`}>
        <h2 className={`text-2xl font-semibold mb-1 tracking-tight ${dark ? 'text-white' : 'text-gray-900'}`}>
          Let's Get Started
        </h2>
        <p className={`text-sm mb-6 ${dark ? 'text-gray-500' : 'text-gray-400'}`}>
          Tell us a bit about yourself so we can personalize your practice sessions and hiring bar
        </p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="grid gap-4 md:grid-cols-2">
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
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className={`block text-xs font-medium uppercase tracking-wider mb-1.5 ${dark ? 'text-gray-400' : 'text-gray-500'}`}>
                Target Company
              </label>
              <input
                id="onboarding-target-company"
                type="text"
                value={targetCompany}
                onChange={(e) => setTargetCompany(e.target.value)}
                required
                className={inputClasses}
                placeholder="e.g. Google, Stripe, Airbnb"
              />
            </div>

            <div>
              <label className={`block text-xs font-medium uppercase tracking-wider mb-1.5 ${dark ? 'text-gray-400' : 'text-gray-500'}`}>
                Target Level
              </label>
              <select
                id="onboarding-target-level"
                value={targetLevel}
                onChange={(e) => setTargetLevel(e.target.value)}
                required
                className={inputClasses}
              >
                {TARGET_LEVEL_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
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
              placeholder="Tell us about the role, interview loops, topics you want to practice, and where you want the coaching to push hardest..."
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
            {loading ? 'Saving...' : 'Continue'}
          </button>
        </form>
      </div>
    </div>
  );
}
