'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import { ArrowLeft, Loader2, CheckCircle2, Mail } from 'lucide-react';
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

export function PageForgotPassword() {
  const navigate = usePartnerStore((s) => s.navigate);

  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [email, setEmail] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFieldError(null);

    if (!email.trim()) {
      setFieldError('Please enter your email address.');
      return;
    }

    setLoading(true);

    try {
      // Always show success (anti-enumeration) — even if request fails
      try {
        await fetch('/api/auth/forgot-password', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: email.trim() }),
        });
      } catch {
        // Swallow network errors — still show success
      }

      setSubmitted(true);
      toast.success('Reset link sent — check your inbox');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-1 items-center justify-center px-4 py-12 sm:py-16">
      <div className="w-full max-w-sm">
        <motion.div
          initial="hidden"
          animate="visible"
          className="rounded-lg border border-border/60 bg-background p-6 sm:p-8"
        >
          {/* Header */}
          <motion.div variants={fadeUp} custom={0} className="mb-8 text-center">
            <button
              onClick={() => navigate('login')}
              className="mb-6 mx-auto inline-flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              <ArrowLeft className="size-3" />
              Back to sign in
            </button>
            <div className="mx-auto mb-5 flex items-center justify-center size-12 rounded-full border border-border/60 bg-muted/30">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <rect x="3" y="11" width="18" height="11" rx="2" stroke="currentColor" strokeWidth="1.5" />
                <path d="M7 11V7a5 5 0 0 1 10 0v4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
              </svg>
            </div>
            <h1 className="text-xl font-semibold tracking-tight text-foreground">
              Reset your password
            </h1>
            <p className="mt-1.5 text-sm text-muted-foreground">
              Enter the email associated with your partner account.
            </p>
          </motion.div>

          {/* Success state */}
          {submitted ? (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className="py-6 text-center"
            >
              <div className="mx-auto mb-5 flex items-center justify-center size-12 rounded-full border border-border/60 bg-muted/30">
                <CheckCircle2 className="size-6 text-foreground" />
              </div>
              <h2 className="text-base font-semibold tracking-tight text-foreground mb-2">
                Check your email
              </h2>
              <p className="text-sm text-muted-foreground mb-1 leading-relaxed">
                If an account exists for
              </p>
              <p className="font-mono text-sm text-foreground mb-4">
                {email}
              </p>
              <p className="text-sm text-muted-foreground mb-6 leading-relaxed">
                you will receive a password reset link shortly.
              </p>
              <Button
                variant="default"
                onClick={() => navigate('login')}
                className="w-full text-sm"
              >
                Return to sign in
              </Button>
            </motion.div>
          ) : (
            <>
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
                  <Label htmlFor="forgot-email" className="text-xs font-mono uppercase tracking-wider">
                    Email
                  </Label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 size-3.5 text-muted-foreground/60" />
                    <Input
                      id="forgot-email"
                      type="email"
                      placeholder="you@company.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      autoComplete="email"
                      className="pl-9 font-mono text-sm"
                      autoFocus
                    />
                  </div>
                </div>

                <Button type="submit" disabled={loading} className="w-full">
                  {loading ? (
                    <>
                      <Loader2 className="size-4 animate-spin" />
                      Sending...
                    </>
                  ) : (
                    'Send reset link'
                  )}
                </Button>
              </motion.form>

              {/* Help text */}
              <motion.div variants={fadeUp} custom={2} className="mt-6 text-center">
                <p className="text-xs text-muted-foreground">
                  Remember your password?{' '}
                  <button
                    onClick={() => navigate('login')}
                    className="font-medium text-foreground underline-offset-4 transition-colors hover:underline"
                  >
                    Sign in
                  </button>
                </p>
              </motion.div>
            </>
          )}
        </motion.div>
      </div>
    </div>
  );
}
