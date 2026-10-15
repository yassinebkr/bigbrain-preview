import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Loader2, AlertCircle, KeyRound, Eye, EyeOff } from 'lucide-react';
import { useAppStore } from '@/store/appStore';

const springEase = [0.34, 1.56, 0.64, 1] as [number, number, number, number];
const easeOut = [0, 0, 0.2, 1] as [number, number, number, number];

function getCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp('(?:^|; )' + name.replace(/([.$?*|{}()[\]\\/+^])/g, '\\$1') + '=([^;]*)'));
  return match ? decodeURIComponent(match[1]) : null;
}

export function LoginPage() {
  const { loginWithToken, isAuthLoading, authError, clearAuthError, theme } = useAppStore();
  const [token, setToken] = useState('');
  const [showToken, setShowToken] = useState(false);
  const [checkingCookie, setCheckingCookie] = useState(true);

  // Auto-detect auth from cookie on mount
  useEffect(() => {
    const cookieToken = getCookie('scratchy_session') || getCookie('scratchy_auth');
    if (cookieToken) {
      // Cookie found — authenticate silently
      loginWithToken(cookieToken);
    }
    setCheckingCookie(false);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token.trim() || isAuthLoading) return;
    await loginWithToken(token.trim());
  };

  if (checkingCookie) {
    return (
      <div data-theme={theme} className="flex items-center justify-center min-h-screen w-screen" style={{ backgroundColor: 'var(--bg-primary)' }}>
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex flex-col items-center gap-3">
          <Loader2 size={24} className="animate-spin" style={{ color: 'var(--accent-blue)' }} />
          <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>Checking authentication...</span>
        </motion.div>
      </div>
    );
  }

  return (
    <div data-theme={theme} className="flex items-center justify-center min-h-screen w-full px-4" style={{ backgroundColor: 'var(--bg-primary)' }}>
      <motion.div
        initial={{ opacity: 0, y: 30, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.5, ease: springEase }}
        className="w-full max-w-[420px]"
      >
        {/* Logo */}
        <motion.div
          initial={{ opacity: 0, scale: 0.8 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.4, delay: 0.1, ease: springEase }}
          className="flex justify-center mb-8"
        >
          <div
            className="w-16 h-16 rounded-2xl flex items-center justify-center"
            style={{ backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border-subtle)' }}
          >
            <img src="/robot-icon.png" alt="Aplot AI" className="w-9 h-9 object-contain" />
          </div>
        </motion.div>

        {/* Title */}
        <motion.div
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.2, ease: easeOut }}
          className="text-center mb-8"
        >
          <h1 className="text-xl font-semibold mb-1.5" style={{ color: 'var(--text-primary)', letterSpacing: '-0.01em' }}>
            Authenticate to Aplot AI
          </h1>
          <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>
            Enter your access token to connect to the OpenClaw gateway
          </p>
        </motion.div>

        {/* Form */}
        <motion.form
          initial={{ opacity: 0, y: 15 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.3, ease: easeOut }}
          onSubmit={handleSubmit}
          className="space-y-4"
        >
          {/* Error */}
          {authError && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              className="flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm"
              style={{ backgroundColor: 'rgba(255,59,48,0.1)', color: '#ff453a', border: '1px solid rgba(255,59,48,0.2)' }}
            >
              <AlertCircle size={16} />
              {authError}
            </motion.div>
          )}

          {/* Token Input */}
          <div>
            <label className="block text-xs font-medium mb-1.5 ml-0.5" style={{ color: 'var(--text-secondary)' }}>
              Access Token
            </label>
            <div className="relative">
              <input
                type={showToken ? 'text' : 'password'}
                value={token}
                onChange={(e) => { clearAuthError(); setToken(e.target.value); }}
                placeholder="Paste your access token here"
                required
                className="w-full h-11 px-3.5 pr-10 rounded-xl text-sm outline-none transition-all duration-200 font-mono"
                style={{
                  backgroundColor: 'var(--bg-input)',
                  border: '1px solid var(--border-subtle)',
                  color: 'var(--text-primary)',
                }}
                onFocus={(e) => { e.currentTarget.style.borderColor = 'rgba(0,113,227,0.5)'; }}
                onBlur={(e) => { e.currentTarget.style.borderColor = 'var(--border-subtle)'; }}
              />
              <button
                type="button"
                onClick={() => setShowToken(!showToken)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 p-1 rounded cursor-pointer"
                style={{ color: 'var(--text-tertiary)' }}
              >
                {showToken ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
            <p className="text-xs mt-1.5 ml-0.5" style={{ color: 'var(--text-tertiary)' }}>
              Your token is stored securely in your browser and never sent to third parties.
            </p>
          </div>

          {/* Submit */}
          <motion.button
            whileHover={{ scale: 1.01 }}
            whileTap={{ scale: 0.98 }}
            type="submit"
            disabled={isAuthLoading}
            className="w-full h-11 rounded-xl text-sm font-semibold transition-all duration-200 flex items-center justify-center gap-2 cursor-pointer mt-2"
            style={{
              backgroundColor: 'var(--accent-blue)',
              color: '#ffffff',
              opacity: isAuthLoading ? 0.7 : 1,
            }}
          >
            {isAuthLoading ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                Connecting...
              </>
            ) : (
              <>
                <KeyRound size={16} />
                Connect to Gateway
              </>
            )}
          </motion.button>
        </motion.form>

        {/* Footer */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.5 }}
          className="text-center mt-8 space-y-2"
        >
          <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
            Aplot AI v3 — OpenClaw Gateway Client
          </p>
          <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
            Token read from: cookie (scratchy_session) → cookie (scratchy_auth) → localStorage
          </p>
        </motion.div>
      </motion.div>
    </div>
  );
}
