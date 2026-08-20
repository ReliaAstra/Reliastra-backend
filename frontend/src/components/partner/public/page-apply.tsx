'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import { ArrowLeft, Loader2, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
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

export function PageApply() {
  const navigate = usePartnerStore((s) => s.navigate);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleActivate = async () => {
    setLoading(true);
    setError(null);
    const store = usePartnerStore.getState();

    try {
      const token = localStorage.getItem('partner_access_token');
      const res = await fetch('/api/partners/apply', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ agree_terms: true }),
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        if (data.detail === 'Already a partner' || data.error === 'Already a partner') {
          // Already applied — fetch partner profile and go to dashboard
          try {
            const partnerRes = await fetch('/api/partners/me', {
              headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}) },
            });
            if (partnerRes.ok) {
              const p = await partnerRes.json();
              store.setPartner({
                partnerId: p.partner_id,
                referralCode: p.referral_code,
                referralLink: p.referral_link,
                commissionRate: p.commission_rate,
                status: p.status,
                createdAt: p.created_at,
              });
            }
          } catch { /* ignore */ }
          navigate('dashboard');
          return;
        }
        throw new Error(data.detail || data.error || 'Activation failed');
      }

      // Success — response is PartnerProfileResponse
      const data = await res.json();
      store.setPartner({
        partnerId: data.partner_id,
        referralCode: data.referral_code,
        referralLink: data.referral_link,
        commissionRate: data.commission_rate,
        status: data.status,
        createdAt: data.created_at,
      });
      toast.success('Partner account activated');
      navigate('dashboard');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex flex-1 items-center justify-center px-4">
      <div className="w-full max-w-md text-center">
        <motion.div initial="hidden" animate="visible">
          {/* Back link */}
          <motion.div variants={fadeUp} custom={0} className="mb-8">
            <button
              onClick={() => navigate('home')}
              className="inline-flex items-center gap-1.5 text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              <ArrowLeft className="size-3" />
              Back to Partner Network
            </button>
          </motion.div>

          <motion.h1
            variants={fadeUp}
            custom={1}
            className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl"
          >
            Activate your Partner account
          </motion.h1>

          <motion.p
            variants={fadeUp}
            custom={2}
            className="mt-3 text-sm leading-relaxed text-muted-foreground max-w-sm mx-auto"
          >
            Get your personal referral link and earn 30% of every referred customer&apos;s subscription each month.
          </motion.p>

          {error && (
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              className="mt-6 inline-block rounded-md border border-red-200 bg-red-50 px-4 py-2 text-sm text-red-700"
            >
              {error}
            </motion.div>
          )}

          <motion.div variants={fadeUp} custom={3} className="mt-8">
            <Button
              size="lg"
              onClick={handleActivate}
              disabled={loading}
              className="min-w-[260px]"
            >
              {loading ? (
                <>
                  <Loader2 className="size-4 animate-spin" />
                  ACTIVATING...
                </>
              ) : (
                <>
                  ACTIVATE PARTNER ACCOUNT
                  <ArrowRight className="size-4" />
                </>
              )}
            </Button>
          </motion.div>

          <motion.div variants={fadeUp} custom={4} className="mt-12 flex justify-center gap-8 text-xs text-muted-foreground">
            <div className="flex items-center gap-2">
              <span className="h-1 w-1 rounded-full bg-emerald-500" />
              No cost to join
            </div>
            <div className="flex items-center gap-2">
              <span className="h-1 w-1 rounded-full bg-emerald-500" />
              Instant activation
            </div>
            <div className="flex items-center gap-2">
              <span className="h-1 w-1 rounded-full bg-emerald-500" />
              30% recurring
            </div>
          </motion.div>
        </motion.div>
      </div>
    </div>
  );
}
