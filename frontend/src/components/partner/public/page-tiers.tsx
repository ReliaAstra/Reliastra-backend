'use client';

import { motion } from 'framer-motion';
import { Check, ArrowRight, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { usePartnerStore } from '@/stores/partner-store';
import { PARTNER_TIERS } from '@/types/partner';
import { TierBadge } from '../shared/tier-badge';
import { cn } from '@/lib/utils';

const fadeUp = {
  hidden: { opacity: 0, y: 16 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.08, duration: 0.5, ease: [0.25, 0.1, 0.25, 1] },
  }),
};

const tierCardBorder: Record<string, string> = {
  bronze: 'border-amber-700/30 dark:border-amber-500/20',
  silver: 'border-slate-500/30 dark:border-slate-400/20',
  gold: 'border-yellow-600/30 dark:border-yellow-400/20',
  platinum: 'border-foreground/20',
};

const tierCommissionColor: Record<string, string> = {
  bronze: 'text-amber-800 dark:text-amber-300',
  silver: 'text-slate-800 dark:text-slate-200',
  gold: 'text-yellow-700 dark:text-yellow-300',
  platinum: 'text-foreground',
};

export function PageTiers() {
  const navigate = usePartnerStore((s) => s.navigate);

  return (
    <div>
      {/* ===== HEADER ===== */}
      <section className="border-b border-border/40">
        <div className="mx-auto max-w-6xl px-4 pb-16 pt-20 sm:px-6 sm:pb-20 sm:pt-28 lg:px-8">
          <motion.div
            initial="hidden"
            animate="visible"
            className="mx-auto max-w-2xl"
          >
            <motion.p
              variants={fadeUp}
              custom={0}
              className="mb-3 font-mono text-xs uppercase tracking-widest text-muted-foreground"
            >
              Partner Tiers
            </motion.p>
            <motion.h1
              variants={fadeUp}
              custom={1}
              className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl"
            >
              Earn more as your network grows.
            </motion.h1>
            <motion.p
              variants={fadeUp}
              custom={2}
              className="mt-4 text-base leading-relaxed text-muted-foreground"
            >
              Every referral you bring moves you closer to a higher tier — and
              a higher commission rate. No application needed, you advance
              automatically.
            </motion.p>
          </motion.div>
        </div>
      </section>

      {/* ===== TIER COMPARISON ===== */}
      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
        <motion.div
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: '-60px' }}
        >
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            {PARTNER_TIERS.map((tier, idx) => (
              <motion.div
                key={tier.tier}
                variants={fadeUp}
                custom={idx}
                className={cn(
                  'relative rounded-lg border bg-background p-6 transition-colors hover:bg-muted/20',
                  tierCardBorder[tier.tier],
                  idx === 0 && 'ring-1 ring-foreground/10'
                )}
              >
                {/* Tier badge */}
                <div className="mb-4">
                  <TierBadge tier={tier} size="md" />
                </div>

                {/* Commission rate - large */}
                <div className="mb-4">
                  <motion.span
                    className={cn(
                      'text-5xl font-bold tracking-tight tabular-nums',
                      tierCommissionColor[tier.tier]
                    )}
                    initial={{ opacity: 0, scale: 0.9 }}
                    whileInView={{ opacity: 1, scale: 1 }}
                    viewport={{ once: true }}
                    transition={{
                      duration: 0.5,
                      delay: idx * 0.1,
                      ease: [0.25, 0.1, 0.25, 1],
                    }}
                  >
                    {tier.commissionRate}
                    <span className="text-2xl font-semibold text-muted-foreground ml-0.5">
                      %
                    </span>
                  </motion.span>
                  <p className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mt-1">
                    Recurring commission
                  </p>
                </div>

                {/* Min referrals */}
                <div className="mb-5 pb-4 border-b border-border/40">
                  <p className="text-sm">
                    <span className="font-mono font-medium text-foreground tabular-nums">
                      {tier.minReferrals === 0
                        ? 'No minimum'
                        : `${tier.minReferrals}+ referrals`}
                    </span>
                  </p>
                </div>

                {/* Benefits */}
                <ul className="space-y-2">
                  {tier.benefits.map((benefit) => (
                    <li
                      key={benefit}
                      className="flex items-start gap-2 text-sm text-muted-foreground"
                    >
                      <Check className="size-3.5 mt-0.5 shrink-0 text-foreground/50" />
                      <span className="leading-relaxed">{benefit}</span>
                    </li>
                  ))}
                </ul>
              </motion.div>
            ))}
          </div>
        </motion.div>
      </section>

      {/* ===== HOW ADVANCEMENT WORKS ===== */}
      <section className="border-t border-border/40 bg-muted/20">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: '-60px' }}
          >
            <motion.div variants={fadeUp} custom={0} className="mb-10 max-w-lg">
              <p className="mb-3 font-mono text-xs uppercase tracking-widest text-muted-foreground">
                Advancement
              </p>
              <h2 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
                Automatic tier upgrades
              </h2>
              <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                Your tier is calculated based on your total active referrals.
                When you reach the threshold for the next tier, you are
                upgraded immediately and the new commission rate applies to
                all future earnings.
              </p>
            </motion.div>

            <motion.div
              variants={fadeUp}
              custom={1}
              className="grid gap-3 sm:grid-cols-3"
            >
              {[
                {
                  step: '01',
                  title: 'Refer customers',
                  desc: 'Share your unique referral link with your network. Each signup counts toward your tier.',
                },
                {
                  step: '02',
                  title: 'Hit the threshold',
                  desc: 'When your active referral count reaches a tier minimum, you are automatically upgraded.',
                },
                {
                  step: '03',
                  title: 'Earn more',
                  desc: 'Your new commission rate applies immediately. No paperwork, no waiting.',
                },
              ].map((item) => (
                <div
                  key={item.step}
                  className="rounded-lg border border-border/60 bg-background p-5"
                >
                  <p className="font-mono text-xs text-muted-foreground/50 mb-2">
                    {item.step}
                  </p>
                  <p className="text-sm font-medium text-foreground mb-1.5">
                    {item.title}
                  </p>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    {item.desc}
                  </p>
                </div>
              ))}
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* ===== COMPARISON TABLE ===== */}
      <section className="border-t border-border/40">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: '-60px' }}
          >
            <motion.div variants={fadeUp} custom={0} className="mb-10 max-w-lg">
              <p className="mb-3 font-mono text-xs uppercase tracking-widest text-muted-foreground">
                Comparison
              </p>
              <h2 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
                Side by side
              </h2>
            </motion.div>

            <motion.div
              variants={fadeUp}
              custom={1}
              className="overflow-hidden rounded-lg border border-border/60 bg-background"
            >
              {/* Table header */}
              <div className="grid grid-cols-5 gap-2 border-b border-border/60 bg-muted/30 px-4 py-3 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                <span>Feature</span>
                {PARTNER_TIERS.map((t) => (
                  <span key={t.tier} className="text-center">
                    {t.name}
                  </span>
                ))}
              </div>

              {/* Rows */}
              {[
                {
                  label: 'Commission',
                  values: PARTNER_TIERS.map((t) => `${t.commissionRate}%`),
                },
                {
                  label: 'Min. referrals',
                  values: PARTNER_TIERS.map((t) =>
                    t.minReferrals === 0 ? '—' : String(t.minReferrals)
                  ),
                },
                {
                  label: 'Attribution window',
                  values: ['90-day', '120-day', '180-day', 'Lifetime'],
                },
                {
                  label: 'Payout frequency',
                  values: ['Monthly', 'Bi-weekly', 'Weekly', 'On-demand'],
                },
                {
                  label: 'Dedicated support',
                  values: ['—', '—', 'Account manager', '24/7 dedicated'],
                },
                {
                  label: 'API access',
                  values: ['—', '—', '—', 'Custom API'],
                },
                {
                  label: 'White-label',
                  values: ['—', '—', '—', 'Available'],
                },
              ].map((row) => (
                <div
                  key={row.label}
                  className="grid grid-cols-5 gap-2 border-b border-border/30 px-4 py-3 last:border-0 hover:bg-muted/20 transition-colors"
                >
                  <span className="text-sm font-medium text-foreground">
                    {row.label}
                  </span>
                  {row.values.map((val, i) => (
                    <span
                      key={`${row.label}-${i}`}
                      className={cn(
                        'text-center text-sm tabular-nums',
                        val === '—'
                          ? 'text-muted-foreground/40'
                          : 'text-foreground'
                      )}
                    >
                      {val}
                    </span>
                  ))}
                </div>
              ))}
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* ===== CTA ===== */}
      <section className="border-t border-border/40">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: '-60px' }}
            className="mx-auto max-w-xl text-center"
          >
            <motion.div variants={fadeUp} custom={0} className="mb-4">
              <Sparkles className="mx-auto size-5 text-muted-foreground" />
            </motion.div>
            <motion.h2
              variants={fadeUp}
              custom={1}
              className="mb-4 text-2xl font-semibold tracking-tight text-foreground"
            >
              Start at Bronze, grow to Platinum
            </motion.h2>
            <motion.p
              variants={fadeUp}
              custom={2}
              className="mb-8 text-sm text-muted-foreground"
            >
              Every partner starts at 30% commission and advances
              automatically. No negotiations, no waiting.
            </motion.p>
            <motion.div variants={fadeUp} custom={3}>
              <Button
                size="lg"
                onClick={() => navigate('apply')}
                className="gap-2 px-8"
              >
                Apply to the program
                <ArrowRight className="size-4" />
              </Button>
            </motion.div>
          </motion.div>
        </div>
      </section>
    </div>
  );
}
