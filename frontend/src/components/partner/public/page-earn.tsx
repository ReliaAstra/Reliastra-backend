'use client';

import { useState, useMemo } from 'react';
import { motion } from 'framer-motion';
import { ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { usePartnerStore } from '@/stores/partner-store';
import { cn } from '@/lib/utils';

const fadeUp = {
  hidden: { opacity: 0, y: 16 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.08, duration: 0.5, ease: [0.25, 0.1, 0.25, 1] },
  }),
};

const staggerContainer = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.12,
      delayChildren: 0.1,
    },
  },
};

const staggerChild = {
  hidden: { opacity: 0, y: 24 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.5, ease: [0.25, 0.1, 0.25, 1] },
  },
};

const steps = [
  {
    number: '1',
    title: 'GET YOUR LINK',
    description:
      'Receive a unique referral link upon approval. No setup, no configuration.',
  },
  {
    number: '2',
    title: 'SHARE IT',
    description:
      'Send it to people who depend on reliable infrastructure. Email, social, or directly.',
  },
  {
    number: '3',
    title: 'THEY SUBSCRIBE',
    description:
      'When someone signs up through your link and starts paying, the connection is made.',
  },
  {
    number: '4',
    title: 'YOU EARN 30% EVERY MONTH',
    description:
      'You receive 30% of their subscription every month they remain a customer.',
    accent: true,
  },
];

const mechanics = [
  {
    title: 'Monthly recurring commission',
    description:
      'You earn a commission every month for each active referral. The revenue compounds as your referral base grows.',
  },
  {
    title: 'No earning cap',
    description:
      'There is no upper limit on how much you can earn. Your revenue is directly proportional to the number of active referrals you maintain.',
  },
  {
    title: 'Lifetime attribution',
    description:
      'Once a customer is attributed to your referral, you continue earning from them for as long as their subscription is active.',
  },
  {
    title: 'Monthly payouts',
    description:
      'Commissions are calculated at the end of each calendar month and paid out within the first week of the following month.',
  },
];

const projections = [
  { month: '1', newRefs: '2', total: '2', earn: '$72' },
  { month: '3', newRefs: '2', total: '6', earn: '$216' },
  { month: '6', newRefs: '3', total: '15', earn: '$540' },
  { month: '12', newRefs: '3', total: '33', earn: '$1,188' },
  { month: '18', newRefs: '2', total: '45', earn: '$1,620' },
  { month: '24', newRefs: '3', total: '63', earn: '$2,268' },
];

// --- Interactive Earnings Calculator ---
function EarningsCalculator() {
  const [monthlyRefs, setMonthlyRefs] = useState(3);
  const [months, setMonths] = useState(12);
  const planPrice = 49;
  const commissionRate = 0.3;
  const perReferralMonthly = planPrice * commissionRate;

  const projectionData = useMemo(() => {
    const data: { month: number; totalActive: number; monthlyEarning: number; cumulativeEarning: number }[] = [];
    let total = 0;
    let cumulative = 0;
    for (let m = 1; m <= months; m++) {
      total += monthlyRefs;
      const monthly = total * perReferralMonthly;
      cumulative += monthly;
      data.push({ month: m, totalActive: total, monthlyEarning: monthly, cumulativeEarning: cumulative });
    }
    return data;
  }, [monthlyRefs, months, perReferralMonthly]);

  const finalMonth = projectionData[projectionData.length - 1];
  const annualEarning = finalMonth?.cumulativeEarning || 0;

  // Determine which milestone rows to highlight (every quarter)
  const milestoneMonths = [3, 6, 12, 18, 24].filter(m => m <= months);

  return (
    <section className="border-t border-border/40">
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
        <motion.div
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: '-60px' }}
        >
          <motion.div variants={fadeUp} custom={0} className="mb-10 max-w-lg">
            <p className="mb-3 font-mono text-xs uppercase tracking-widest text-muted-foreground">
              Calculator
            </p>
            <h2 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
              Model your earnings
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Adjust the inputs to see your projected earnings over time.
            </p>
          </motion.div>

          <motion.div variants={fadeUp} custom={1} className="grid gap-6 lg:grid-cols-[1fr_380px]">
            {/* Controls + Chart area */}
            <div className="space-y-6">
              {/* Sliders */}
              <div className="rounded-lg border border-border/60 bg-background p-6 space-y-6">
                {/* Monthly referrals slider */}
                <div>
                  <div className="mb-3 flex items-center justify-between">
                    <label className="text-sm font-medium text-foreground">
                      New referrals per month
                    </label>
                    <span className="font-mono text-lg font-semibold tabular-nums">
                      {monthlyRefs}
                    </span>
                  </div>
                  <input
                    type="range"
                    min={1}
                    max={20}
                    value={monthlyRefs}
                    onChange={(e) => setMonthlyRefs(Number(e.target.value))}
                    className="w-full h-1.5 appearance-none rounded-full bg-muted cursor-pointer accent-foreground [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-foreground [&::-webkit-slider-thumb]:cursor-pointer [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-background [&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:bg-foreground [&::-moz-range-thumb]:cursor-pointer [&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-background"
                  />
                  <div className="mt-1 flex justify-between font-mono text-[10px] text-muted-foreground/60">
                    <span>1</span>
                    <span>20</span>
                  </div>
                </div>

                {/* Time period slider */}
                <div>
                  <div className="mb-3 flex items-center justify-between">
                    <label className="text-sm font-medium text-foreground">
                      Time period
                    </label>
                    <span className="font-mono text-lg font-semibold tabular-nums">
                      {months} mo
                    </span>
                  </div>
                  <input
                    type="range"
                    min={3}
                    max={36}
                    step={3}
                    value={months}
                    onChange={(e) => setMonths(Number(e.target.value))}
                    className="w-full h-1.5 appearance-none rounded-full bg-muted cursor-pointer accent-foreground [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-foreground [&::-webkit-slider-thumb]:cursor-pointer [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-background [&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:bg-foreground [&::-moz-range-thumb]:cursor-pointer [&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-background"
                  />
                  <div className="mt-1 flex justify-between font-mono text-[10px] text-muted-foreground/60">
                    <span>3</span>
                    <span>36</span>
                  </div>
                </div>
              </div>

              {/* Mini chart - bar visualization */}
              <div className="rounded-lg border border-border/60 bg-background p-5">
                <p className="mb-3 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  Monthly earnings projection
                </p>
                <div className="flex items-end gap-[2px] h-32">
                  {projectionData.map((d) => {
                    const maxEarning = finalMonth?.monthlyEarning || 1;
                    const height = (d.monthlyEarning / maxEarning) * 100;
                    const isMilestone = milestoneMonths.includes(d.month);
                    return (
                      <div
                        key={d.month}
                        className="flex-1 group relative flex flex-col items-center justify-end h-full"
                      >
                        <div
                          className={cn(
                            'w-full rounded-t-sm transition-all duration-300',
                            isMilestone
                              ? 'bg-foreground'
                              : 'bg-foreground/15 group-hover:bg-foreground/30'
                          )}
                          style={{ height: `${Math.max(height, 2)}%` }}
                        />
                        {isMilestone && (
                          <span className="absolute -top-5 left-1/2 -translate-x-1/2 font-mono text-[9px] text-muted-foreground whitespace-nowrap">
                            M{d.month}
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
                <div className="mt-2 flex justify-between font-mono text-[9px] text-muted-foreground/50">
                  <span>M1</span>
                  <span>M{months}</span>
                </div>
              </div>
            </div>

            {/* Results summary card */}
            <div className="space-y-4">
              <div className="rounded-lg border border-border/60 bg-background p-6">
                <p className="mb-1 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  At month {months}
                </p>
                <p className="font-mono text-3xl font-semibold tabular-nums">
                  ${finalMonth?.monthlyEarning.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                  <span className="ml-1.5 text-sm font-normal text-muted-foreground">/mo</span>
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  from {finalMonth?.totalActive} active referrals
                </p>
              </div>

              <div className="rounded-lg border border-border/60 bg-background p-6">
                <p className="mb-1 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                  Cumulative earnings
                </p>
                <p className="font-mono text-3xl font-semibold tabular-nums">
                  ${annualEarning.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  total over {months} months
                </p>
              </div>

              <div className="rounded-lg border border-border/60 bg-muted/30 p-5">
                <div className="space-y-3">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Per referral</span>
                    <span className="font-mono font-medium">
                      ${perReferralMonthly.toFixed(2)}/mo
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Commission rate</span>
                    <span className="font-mono font-medium">
                      {(commissionRate * 100).toFixed(0)}%
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Plan price</span>
                    <span className="font-mono font-medium">
                      ${planPrice}/mo
                    </span>
                  </div>
                </div>
              </div>

              <p className="font-mono text-[10px] leading-relaxed text-muted-foreground/50 px-1">
                Projections assume 0% churn. Actual results vary. For illustration only.
              </p>
            </div>
          </motion.div>
        </motion.div>
      </div>
    </section>
  );
}

export function PageEarn() {
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
              Earnings
            </motion.p>
            <motion.h1
              variants={fadeUp}
              custom={1}
              className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl"
            >
              Bring RELIASTRA to the right people. Get paid every month.
            </motion.h1>
            <motion.p
              variants={fadeUp}
              custom={2}
              className="mt-4 text-base leading-relaxed text-muted-foreground"
            >
              The partner program uses a straightforward recurring commission
              model. There are no hidden thresholds, no tier negotiations, and
              no surprise deductions.
            </motion.p>
          </motion.div>
        </div>
      </section>

      {/* ===== 4-STEP MECHANISM (HERO) ===== */}
      <section className="mx-auto max-w-6xl px-4 py-20 sm:px-6 sm:py-28 lg:px-8">
        <motion.div
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: '-60px' }}
          variants={staggerContainer}
        >
          {/* Desktop: horizontal row with connectors */}
          <div className="hidden md:grid md:grid-cols-4 md:gap-0">
            {steps.map((step, i) => (
              <div key={step.number} className="flex items-stretch">
                {/* Connector line */}
                {i > 0 && (
                  <div className="relative flex w-8 shrink-0 items-center justify-center">
                    <div className="h-px w-full bg-border" />
                  </div>
                )}
                <motion.div
                  variants={staggerChild}
                  className={cn(
                    'flex-1 rounded-lg border bg-background p-6 transition-colors',
                    step.accent
                      ? 'border-emerald-500/40 bg-emerald-50/30'
                      : 'border-border/60'
                  )}
                >
                  <span className="mb-4 block font-mono text-[48px] font-extralight leading-none text-muted-foreground/30">
                    {step.number}
                  </span>
                  <h3 className="mb-2 text-xs font-semibold uppercase tracking-widest text-foreground">
                    {step.title}
                  </h3>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    {step.description}
                  </p>
                </motion.div>
              </div>
            ))}
          </div>

          {/* Mobile: vertical stack with arrows */}
          <div className="flex flex-col gap-4 md:hidden">
            {steps.map((step, i) => (
              <div key={step.number}>
                <motion.div
                  variants={staggerChild}
                  className={cn(
                    'rounded-lg border bg-background p-6',
                    step.accent
                      ? 'border-emerald-500/40 bg-emerald-50/30'
                      : 'border-border/60'
                  )}
                >
                  <div className="flex items-start gap-4">
                    <span className="shrink-0 font-mono text-[40px] font-extralight leading-none text-muted-foreground/30">
                      {step.number}
                    </span>
                    <div>
                      <h3 className="mb-1 text-xs font-semibold uppercase tracking-widest text-foreground">
                        {step.title}
                      </h3>
                      <p className="text-sm leading-relaxed text-muted-foreground">
                        {step.description}
                      </p>
                    </div>
                  </div>
                </motion.div>
                {i < steps.length - 1 && (
                  <div className="flex justify-center py-1">
                    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="text-muted-foreground/30">
                      <path d="M8 2v12M4 10l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </div>
                )}
              </div>
            ))}
          </div>
        </motion.div>
      </section>

      {/* ===== RECURRING COMMISSION CALLOUT ===== */}
      <section className="border-t border-border/40 bg-muted/20">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: '-60px' }}
            className="mx-auto max-w-xl text-center"
          >
            <motion.p
              variants={fadeUp}
              custom={0}
              className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl"
            >
              30% recurring commission
            </motion.p>
            <motion.p
              variants={fadeUp}
              custom={1}
              className="mt-3 text-base text-muted-foreground"
            >
              Every month a referred customer remains subscribed.
            </motion.p>
            <motion.p
              variants={fadeUp}
              custom={2}
              className="mt-4 font-mono text-xs leading-relaxed text-muted-foreground/60"
            >
              Based on $49/mo Pro plan. You would earn $14.70/mo per referral.
            </motion.p>
          </motion.div>
        </div>
      </section>

      {/* ===== MECHANICS DETAIL GRID (editorial with left border) ===== */}
      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
        <motion.div
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: '-60px' }}
        >
          <motion.div variants={fadeUp} custom={0} className="mb-10 max-w-lg">
            <p className="mb-3 font-mono text-xs uppercase tracking-widest text-muted-foreground">
              Mechanics
            </p>
            <h2 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
              How the commission works
            </h2>
          </motion.div>

          <motion.div
            variants={fadeUp}
            custom={1}
            className="grid gap-6 sm:grid-cols-2"
          >
            {mechanics.map((item) => (
              <div
                key={item.title}
                className="border-l-2 border-border/60 bg-background px-6 py-5 transition-colors hover:border-foreground/30"
              >
                <h3 className="mb-2 text-sm font-semibold text-foreground">
                  {item.title}
                </h3>
                <p className="text-sm leading-relaxed text-muted-foreground">
                  {item.description}
                </p>
              </div>
            ))}
          </motion.div>
        </motion.div>
      </section>

      {/* ===== PROJECTION TABLE (compact) ===== */}
      <section className="border-t border-border/40 bg-muted/30">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: '-60px' }}
          >
            <motion.div variants={fadeUp} custom={0} className="mb-8 max-w-lg">
              <p className="mb-3 font-mono text-xs uppercase tracking-widest text-muted-foreground">
                Projection model
              </p>
              <h2 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
                See the compounding effect
              </h2>
            </motion.div>

            <motion.div variants={fadeUp} custom={1}>
              <div className="overflow-hidden rounded-lg border border-border/60 bg-background">
                <div className="grid grid-cols-4 gap-4 border-b border-border/60 bg-muted/30 px-5 py-2.5 font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
                  <span>Month</span>
                  <span className="text-right">New refs</span>
                  <span className="text-right">Total active</span>
                  <span className="text-right">Monthly earn</span>
                </div>
                {projections.map((row) => (
                  <div
                    key={row.month}
                    className="grid grid-cols-4 gap-4 border-b border-border/30 px-5 py-3 last:border-0"
                  >
                    <span className="font-mono text-sm text-foreground">
                      {row.month}
                    </span>
                    <span className="text-right text-sm text-muted-foreground">
                      +{row.newRefs}
                    </span>
                    <span className="text-right text-sm font-medium text-foreground">
                      {row.total}
                    </span>
                    <span className="text-right font-mono text-sm font-semibold text-foreground">
                      {row.earn}
                    </span>
                  </div>
                ))}
              </div>
              <p className="mt-3 font-mono text-[11px] leading-relaxed text-muted-foreground/60">
                Assumes 30% commission on $120/mo average subscription. New referrals
                added monthly. Churn not modeled. For illustration only.
              </p>
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* ===== INTERACTIVE CALCULATOR ===== */}
      <EarningsCalculator />

      {/* ===== PAYOUT PROCESS ===== */}
      <section className="border-t border-border/40">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: '-60px' }}
          >
            <motion.div variants={fadeUp} custom={0} className="mb-10 max-w-lg">
              <p className="mb-3 font-mono text-xs uppercase tracking-widest text-muted-foreground">
                Payouts
              </p>
              <h2 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
                Getting paid
              </h2>
            </motion.div>

            <motion.div
              variants={fadeUp}
              custom={1}
              className="grid gap-6 sm:grid-cols-3"
            >
              {[
                {
                  step: '01',
                  title: 'Commissions accrue',
                  desc: 'Each month, your earned commissions from active referrals are calculated and recorded in your dashboard.',
                },
                {
                  step: '02',
                  title: 'Review and confirm',
                  desc: 'At the end of the month, review your commission statement. Disputes can be raised within 7 days.',
                },
                {
                  step: '03',
                  title: 'Payment processed',
                  desc: 'Approved commissions are paid out within the first 5 business days of the following month via bank transfer.',
                },
              ].map((item) => (
                <div
                  key={item.step}
                  className="rounded-lg border border-border/60 bg-background p-6"
                >
                  <span className="mb-4 block font-mono text-2xl font-light text-muted-foreground/40">
                    {item.step}
                  </span>
                  <h3 className="mb-2 text-sm font-semibold text-foreground">
                    {item.title}
                  </h3>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    {item.desc}
                  </p>
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
            <motion.h2
              variants={fadeUp}
              custom={0}
              className="mb-4 text-2xl font-semibold tracking-tight text-foreground"
            >
              Ready to start earning?
            </motion.h2>
            <motion.p
              variants={fadeUp}
              custom={1}
              className="mb-8 text-sm text-muted-foreground"
            >
              Apply to the partner program and receive your referral link within
              48 hours of approval.
            </motion.p>
            <motion.div variants={fadeUp} custom={2}>
              <Button
                size="lg"
                onClick={() => navigate('apply')}
                className="gap-2 px-8"
              >
                Apply now
                <ArrowRight className="size-4" />
              </Button>
            </motion.div>
          </motion.div>
        </div>
      </section>
    </div>
  );
}
