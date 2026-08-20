'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import { Loader2, ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { usePartnerStore } from '@/stores/partner-store';
import { toast } from 'sonner';

const fadeUp = {
  hidden: { opacity: 0, y: 16 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.08, duration: 0.5, ease: [0.25, 0.1, 0.25, 1] },
  }),
};

export function PageLogin() {
  const navigate = usePartnerStore((s) => s.navigate);
  const [loading, setLoading] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fieldError, setFieldError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFieldError(null);

    if (!email || !password) {
      setFieldError('Please enter your email and password.');
      return;
    }

    setLoading(true);
    const store = usePartnerStore.getState();

    try {
      // Step 1: Login — returns { access_token, refresh_token, token_type, expires_in }
      const loginRes = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });

      if (!loginRes.ok) {
        const data = await loginRes.json().catch(() => ({}));
        throw new Error(data.error || 'Login failed');
      }

      const tokens = await loginRes.json();
      store.setTokens(tokens.access_token, tokens.refresh_token);

      // Step 2: Get current user info — UserResponse (snake_case, not wrapped)
      const meRes = await fetch('/api/auth/me', {
        headers: { Authorization: `Bearer ${tokens.access_token}` },
      });

      if (meRes.ok) {
        const user = await meRes.json();
        store.setUser({
          id: user.id,
          email: user.email,
          fullName: user.full_name,
        });
        store.setAuthStatus('authenticated');
      } else {
        store.setAuthStatus('authenticated');
      }

      // Step 3: Check if user is already a partner
      const partnerRes = await fetch('/api/partners/me', {
        headers: { Authorization: `Bearer ${tokens.access_token}` },
      });

      if (partnerRes.ok) {
        const partnerData = await partnerRes.json();
        store.setPartner({
          partnerId: partnerData.partner_id,
          referralCode: partnerData.referral_code,
          referralLink: partnerData.referral_link,
          commissionRate: partnerData.commission_rate,
          status: partnerData.status,
          createdAt: partnerData.created_at,
        });
        toast.success('Welcome back');
        navigate('dashboard');
      } else {
        // Not a partner yet (404 or other)
        toast.success('Signed in — activate your partner account');
        navigate('apply');
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : '';
      if (message.includes('reach') || message.includes('fetch')) {
        setFieldError("We couldn't reach RELIASTRA. Check your connection and try again.");
        toast.error('Connection failed — check your network');
      } else {
        setFieldError("We couldn't sign you in. Check your email and password and try again.");
        toast.error('Invalid credentials — try again');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-1 items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <motion.div
          initial="hidden"
          animate="visible"
          className="rounded-lg border border-border/60 bg-background p-6 sm:p-8"
        >
          {/* Logo */}
          <motion.div variants={fadeUp} custom={0} className="mb-8 text-center">
            <button
              onClick={() => navigate('home')}
              className="mx-auto mb-6 flex items-center gap-2 transition-opacity hover:opacity-70"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <rect x="2" y="2" width="20" height="20" rx="4" stroke="currentColor" strokeWidth="1.5" />
                <path d="M8 12L11 15L16 9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span className="font-mono text-xs font-semibold tracking-widest uppercase text-foreground">
                RELIASTRA
              </span>
            </button>
            <h1 className="text-xl font-semibold text-foreground">Welcome back.</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Your RELIASTRA referral network is waiting.
            </p>
          </motion.div>

          {/* Error */}
          {fieldError && (
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-4 rounded-md border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950/40 px-3 py-2 text-sm text-red-700 dark:text-red-400"
            >
              {fieldError}
            </motion.div>
          )}

          {/* Form */}
          <motion.form variants={fadeUp} custom={1} onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="login-email" className="text-xs font-mono uppercase tracking-wider">
                Email
              </Label>
              <Input
                id="login-email"
                type="email"
                placeholder="you@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="login-password" className="text-xs font-mono uppercase tracking-wider">
                Password
              </Label>
              <Input
                id="login-password"
                type="password"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
              <div className="flex justify-end">
                <button
                  onClick={() => navigate('forgot-password')}
                  className="text-xs text-muted-foreground underline-offset-4 transition-colors hover:text-foreground hover:underline"
                >
                  Forgot password?
                </button>
              </div>
            </div>

            <Button type="submit" disabled={loading} className="w-full">
              {loading ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  Authenticating...
                </>
              ) : (
                'Sign In'
              )}
            </Button>
          </motion.form>

          {/* Footer */}
          <motion.div variants={fadeUp} custom={2} className="mt-6 text-center">
            <p className="text-sm text-muted-foreground">
              Don&apos;t have an account?{' '}
              <button
                onClick={() => navigate('signup')}
                className="font-medium text-foreground underline-offset-4 transition-colors hover:underline"
              >
                Create one
              </button>
            </p>
          </motion.div>

          {/* Back link */}
          <motion.div variants={fadeUp} custom={3} className="mt-4 text-center">
            <button
              onClick={() => navigate('home')}
              className="inline-flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              <ArrowLeft className="size-3" />
              Back to Partner Network
            </button>
          </motion.div>
        </motion.div>
      </div>
    </div>
  );
}
