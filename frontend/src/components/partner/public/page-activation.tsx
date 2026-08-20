'use client';

import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ArrowRight, Loader2, Check } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { usePartnerStore } from '@/stores/partner-store';
import { getReferralLink } from '@/lib/format';

const stages = ['ACTIVATING...', 'CREATING YOUR REFERRAL LINK...', 'READY'];

type ActivationStage = 'idle' | 'activating' | 'ready' | 'error';

export function PageActivation() {
  const navigate = usePartnerStore((s) => s.navigate);
  const [stage, setStage] = useState<ActivationStage>('idle');
  const [stageIndex, setStageIndex] = useState(0);
  const [referralCode, setReferralCode] = useState('');

  useEffect(() => {
    let cancelled = false;

    const activate = async () => {
      setStage('activating');
      setStageIndex(0);

      // Simulate staged activation
      const t1 = setTimeout(() => { if (!cancelled) setStageIndex(1); }, 800);
      const t2 = setTimeout(() => { if (!cancelled) setStageIndex(2); }, 1600);

      try {
        const res = await fetch('/api/partners/apply', { method: 'POST' });
        if (cancelled) return;
        clearTimeout(t1);
        clearTimeout(t2);

        if (!res.ok) {
          const data = await res.json();
          // Handle 409 (already a partner) or 401 (demo API double-call) gracefully
          if (data.error === 'Already a partner' || res.status === 401) {
            setStage('ready');
            setStageIndex(2);
            const meRes = await fetch('/api/partners/me');
            if (cancelled) return;
            if (meRes.ok) {
              const meData = await meRes.json();
              setReferralCode(meData.partner.referralCode);
            } else {
              setReferralCode('PARTNER');
            }
            return;
          }
          throw new Error(data.error || 'Activation failed');
        }

        const data = await res.json();
        if (cancelled) return;
        setReferralCode(data.partner.referralCode);
        setStage('ready');
        setStageIndex(2);
      } catch {
        if (!cancelled) setStage('error');
      }
    };

    activate();
    return () => { cancelled = true; };
  }, []);

  const referralLink = referralCode ? getReferralLink(referralCode) : '';

  return (
    <div className="flex flex-1 items-center justify-center px-4">
      <div className="w-full max-w-lg text-center">
        <AnimatePresence mode="wait">
          {/* Activating state */}
          {stage === 'activating' && (
            <motion.div
              key="activating"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              <div className="mb-8 flex justify-center">
                <div className="relative flex h-16 w-16 items-center justify-center rounded-full border border-border/60">
                  <Loader2 className="size-7 animate-spin text-foreground" />
                  {/* Pulse ring */}
                  <motion.div
                    className="absolute inset-0 rounded-full border border-foreground/20"
                    animate={{ scale: [1, 1.4], opacity: [0.5, 0] }}
                    transition={{ duration: 1.5, repeat: Infinity, ease: 'easeOut' }}
                  />
                </div>
              </div>

              <div className="space-y-2">
                {stages.map((s, i) => (
                  <motion.p
                    key={s}
                    initial={{ opacity: 0 }}
                    animate={{
                      opacity: i === stageIndex ? 1 : i < stageIndex ? 0.4 : 0.15,
                    }}
                    className={`font-mono text-xs uppercase tracking-widest transition-all ${
                      i === stageIndex ? 'text-foreground' : 'text-muted-foreground'
                    }`}
                  >
                    {s}
                    {i === stageIndex && (
                      <motion.span
                        animate={{ opacity: [1, 0.4, 1] }}
                        transition={{ duration: 1.2, repeat: Infinity }}
                      >
                        {' '}•
                      </motion.span>
                    )}
                    {i < stageIndex && (
                      <Check className="inline-block size-3 ml-1 text-emerald-500" />
                    )}
                  </motion.p>
                ))}
              </div>
            </motion.div>
          )}

          {/* Ready state - referral link reveal */}
          {stage === 'ready' && referralLink && (
            <motion.div
              key="ready"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.6, ease: [0.25, 0.1, 0.25, 1] }}
            >
              <div className="mb-6 flex justify-center">
                <div className="flex h-16 w-16 items-center justify-center rounded-full border-2 border-emerald-500/40 bg-emerald-50">
                  <Check className="size-8 text-emerald-600" strokeWidth={2} />
                </div>
              </div>

              <motion.h1
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 }}
                className="text-2xl font-bold tracking-tight text-foreground"
              >
                You&apos;re ready.
              </motion.h1>

              <motion.p
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3 }}
                className="mt-2 text-sm text-muted-foreground"
              >
                Your referral link:
              </motion.p>

              {/* Referral Link Block */}
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.5, duration: 0.5 }}
                className="mt-6"
              >
                <p className="mb-3 font-mono text-xs uppercase tracking-widest text-muted-foreground">
                  Your RELIASTRA link
                </p>
                <div className="rounded-lg border-2 border-foreground/80 bg-muted/30 p-6">
                  <p className="font-mono text-lg sm:text-xl text-foreground tracking-tight break-all">
                    {referralLink}
                  </p>
                </div>
              </motion.div>

              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.7 }}
                className="mt-4 text-sm text-muted-foreground"
              >
                Share this link with anyone who could benefit from RELIASTRA.
              </motion.p>

              {/* Actions */}
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.9 }}
                className="mt-8 flex flex-col items-center gap-3"
              >
                <CopyButton link={referralLink} />
                <Button
                  variant="outline"
                  onClick={() => navigate('dashboard')}
                  className="gap-2"
                >
                  GO TO DASHBOARD
                  <ArrowRight className="size-4" />
                </Button>
              </motion.div>
            </motion.div>
          )}

          {/* Error state */}
          {stage === 'error' && (
            <motion.div
              key="error"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
            >
              <p className="text-sm text-muted-foreground">
                Could not activate your account. Please try again.
              </p>
              <Button
                variant="outline"
                onClick={() => navigate('apply')}
                className="mt-6"
              >
                Try again
              </Button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

function CopyButton({ link }: { link: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = link;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    }
  };

  return (
    <Button
      size="lg"
      onClick={handleCopy}
      className="min-w-[160px]"
    >
      {copied ? (
        <>
          <Check className="size-4" />
          COPIED
        </>
      ) : (
        'COPY LINK'
      )}
    </Button>
  );
}
