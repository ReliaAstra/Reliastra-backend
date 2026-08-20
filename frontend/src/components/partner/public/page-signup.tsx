'use client';

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Loader2, ArrowLeft, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { usePartnerStore } from '@/stores/partner-store';
import { toast } from 'sonner';
import { getStoredReferralCode } from './referral-banner';

const fadeUp = {
  hidden: { opacity: 0, y: 16 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.07, duration: 0.5, ease: [0.25, 0.1, 0.25, 1] },
  }),
};

export function PageSignup() {
  const navigate = usePartnerStore((s) => s.navigate);
  const [loading, setLoading] = useState(false);
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [referralCode, setReferralCode] = useState<string | null>(null);

  // Check for referral cookie on mount
  useEffect(() => {
    const code = getStoredReferralCode();
    if (code) setReferralCode(code);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFieldError(null);

    if (!name || !email || !password) {
      setFieldError('Please fill in all required fields.');
      return;
    }

    if (password.length < 8) {
      setFieldError('Password must be at least 8 characters.');
      return;
    }

    setLoading(true);
    const store = usePartnerStore.getState();

    try {
      // Call real register endpoint with snake_case fields
      const res = await fetch('/api/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email,
          password,
          full_name: name,
          ref_code: referralCode || undefined,
        }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || 'Signup failed');
      }

      // Response: { user: UserResponseLite, organization: OrganizationLite, tokens: TokenResponse }
      const data = await res.json();
      store.setTokens(data.tokens.access_token, data.tokens.refresh_token);
      store.setUser({
        id: data.user.id,
        email: data.user.email,
        fullName: data.user.full_name,
      });
      store.setAuthStatus('authenticated');

      toast.success('Account created — welcome to RELIASTRA');
      navigate('apply');
    } catch (err) {
      const message = err instanceof Error ? err.message : '';
      if (message.includes('already exists')) {
        setFieldError('An account with this email already exists.');
      } else if (message.includes('reach') || message.includes('fetch')) {
        setFieldError("We couldn't reach RELIASTRA. Check your connection and try again.");
      } else {
        setFieldError('Something went wrong. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-1 items-center justify-center px-4 py-8">
      <div className="w-full max-w-4xl grid lg:grid-cols-2 gap-0 rounded-lg border border-border/60 overflow-hidden">
        {/* LEFT: Value proposition */}
        <motion.div
          initial="hidden"
          animate="visible"
          className="hidden lg:flex flex-col justify-between p-10 bg-neutral-950 text-neutral-50"
        >
          <div>
            <motion.div variants={fadeUp} custom={0} className="flex items-center gap-2 mb-12">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <rect x="2" y="2" width="20" height="20" rx="4" stroke="currentColor" strokeWidth="1.5" />
                <path d="M8 12L11 15L16 9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span className="font-mono text-xs font-semibold tracking-widest uppercase">
                RELIASTRA Partner Network
              </span>
            </motion.div>

            <motion.h2 variants={fadeUp} custom={1} className="text-3xl font-bold tracking-tight leading-tight mb-4">
              Start earning with RELIASTRA.
            </motion.h2>
            <motion.p variants={fadeUp} custom={2} className="text-base leading-relaxed text-neutral-400">
              Share RELIASTRA with someone who needs it. When they become a paying customer, you earn 30% every month they remain subscribed.
            </motion.p>
          </div>

          <motion.div variants={fadeUp} custom={3} className="mt-12">
            <div className="flex items-center gap-4 text-sm text-neutral-500">
              <div className="flex items-center gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                <span>30% recurring</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                <span>No caps</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                <span>Monthly payouts</span>
              </div>
            </div>
          </motion.div>
        </motion.div>

        {/* RIGHT: Form */}
        <motion.div
          initial="hidden"
          animate="visible"
          className="p-6 sm:p-10 bg-background"
        >
          {/* Mobile logo */}
          <motion.div variants={fadeUp} custom={0} className="mb-8 lg:hidden">
            <button
              onClick={() => navigate('home')}
              className="flex items-center gap-2 transition-opacity hover:opacity-70"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <rect x="2" y="2" width="20" height="20" rx="4" stroke="currentColor" strokeWidth="1.5" />
                <path d="M8 12L11 15L16 9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span className="font-mono text-xs font-semibold tracking-widest uppercase text-foreground">
                RELIASTRA
              </span>
            </button>
          </motion.div>

          <motion.div variants={fadeUp} custom={1} className="mb-8">
            <h1 className="text-xl font-semibold text-foreground">Start earning with RELIASTRA.</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Create your account to get started.
            </p>
            {referralCode && (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                className="mt-3 flex items-center gap-2 rounded-md border border-emerald-500/20 bg-emerald-50/40 dark:bg-emerald-950/30 px-3 py-2"
              >
                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" />
                <span className="text-xs text-emerald-800 dark:text-emerald-300">
                  Referred by <span className="font-mono font-medium">{referralCode}</span>
                </span>
              </motion.div>
            )}
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

          <motion.form variants={fadeUp} custom={2} onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="signup-name" className="text-xs font-mono uppercase tracking-wider">
                Name
              </Label>
              <Input
                id="signup-name"
                type="text"
                placeholder="Jane Doe"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoComplete="name"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="signup-email" className="text-xs font-mono uppercase tracking-wider">
                Email
              </Label>
              <Input
                id="signup-email"
                type="email"
                placeholder="you@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="signup-password" className="text-xs font-mono uppercase tracking-wider">
                Password
              </Label>
              <Input
                id="signup-password"
                type="password"
                placeholder="Min. 8 characters"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
              />
            </div>

            <Button type="submit" disabled={loading} className="w-full mt-6">
              {loading ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  Creating account...
                </>
              ) : (
                <>
                  CREATE ACCOUNT
                  <ArrowRight className="size-4" />
                </>
              )}
            </Button>
          </motion.form>

          <motion.div variants={fadeUp} custom={3} className="mt-6">
            <p className="text-sm text-muted-foreground">
              Already have an account?{' '}
              <button
                onClick={() => navigate('login')}
                className="font-medium text-foreground underline-offset-4 transition-colors hover:underline"
              >
                Sign in
              </button>
            </p>
          </motion.div>

          <motion.div variants={fadeUp} custom={4} className="mt-4">
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
