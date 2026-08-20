'use client';

import { motion } from 'framer-motion';
import { Check, Minus, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { usePartnerStore } from '@/stores/partner-store';

const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.07, duration: 0.6, ease: [0.25, 0.1, 0.25, 1] },
  }),
};

const benefits = [
  {
    title: 'Higher Commission Rates',
    description:
      'Earn up to 40% recurring commission on every referral. Premium partners are rewarded for their results.',
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
      </svg>
    ),
  },
  {
    title: 'Priority Support',
    description:
      'Dedicated account manager with 24/7 access. Your questions get answered first, every time.',
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
    ),
  },
  {
    title: 'Advanced Analytics',
    description:
      'Real-time dashboards, conversion funnels, and cohort analysis. Understand your audience like never before.',
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M18 20V10" /><path d="M12 20V4" /><path d="M6 20v-6" />
      </svg>
    ),
  },
  {
    title: 'Custom Branding',
    description:
      'Co-branded landing pages and marketing materials. Your audience sees your brand, powered by RELIASTRA.',
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" /><path d="M8 14s1.5 2 4 2 4-2 4-2" /><line x1="9" y1="9" x2="9.01" y2="9" /><line x1="15" y1="9" x2="15.01" y2="9" />
      </svg>
    ),
  },
  {
    title: 'Faster Payouts',
    description:
      'On-demand payouts with no minimum threshold. Your earnings, when you need them.',
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <rect x="1" y="4" width="22" height="16" rx="2" ry="2" /><line x1="1" y1="10" x2="23" y2="10" />
      </svg>
    ),
  },
  {
    title: 'Exclusive Access',
    description:
      'Early access to new features, partner-only events, and direct input into product roadmap.',
    icon: (
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
      </svg>
    ),
  },
];

const comparisonRows = [
  { feature: 'Commission rate', standard: '30%', premium: 'Up to 40%' },
  { feature: 'Attribution window', standard: '90 days', premium: 'Lifetime' },
  { feature: 'Support', standard: 'Email', premium: 'Dedicated 24/7' },
  { feature: 'Payouts', standard: 'Monthly', premium: 'On-demand' },
  { feature: 'Analytics', standard: 'Basic', premium: 'Advanced' },
  { feature: 'Branding', standard: 'No', premium: 'Co-branded' },
  { feature: 'Events', standard: 'No', premium: 'Exclusive access' },
];

export function PagePremium() {
  const navigate = usePartnerStore((s) => s.navigate);

  return (
    <div>
      {/* ===== HERO ===== */}
      <section className="border-b border-border/40">
        <div className="mx-auto max-w-6xl px-4 pb-20 pt-20 sm:px-6 sm:pb-28 sm:pt-28 lg:px-8">
          <motion.div
            initial="hidden"
            animate="visible"
            className="mx-auto max-w-2xl text-center"
          >
            <motion.p
              variants={fadeUp}
              custom={0}
              className="mb-4 font-mono text-xs uppercase tracking-widest text-muted-foreground"
            >
              Premium Partnership
            </motion.p>
            <motion.h1
              variants={fadeUp}
              custom={1}
              className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl md:text-5xl"
            >
              Elevate your partnership.
            </motion.h1>
            <motion.p
              variants={fadeUp}
              custom={2}
              className="mt-4 text-base leading-relaxed text-muted-foreground sm:text-lg"
            >
              Unlock higher commission rates, priority support, and exclusive
              tools designed for high-performing partners.
            </motion.p>
            <motion.div variants={fadeUp} custom={3} className="mt-8">
              <Button
                size="lg"
                onClick={() => navigate('apply')}
                className="gap-2 px-8"
              >
                APPLY FOR PREMIUM
                <ArrowRight className="size-4" />
              </Button>
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* ===== STATS BAR ===== */}
      <section className="border-b border-border/40 bg-muted/20">
        <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 lg:px-8">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-40px' }}
            transition={{ duration: 0.5, ease: [0.25, 0.1, 0.25, 1] }}
            className="grid grid-cols-3 divide-x divide-border/40"
          >
            <div className="px-4 text-center first:pl-0 last:pr-0 sm:px-8">
              <p className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
                Up to 40%
              </p>
              <p className="mt-1 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                Commission
              </p>
            </div>
            <div className="px-4 text-center first:pl-0 last:pr-0 sm:px-8">
              <p className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
                24/7
              </p>
              <p className="mt-1 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                Dedicated support
              </p>
            </div>
            <div className="px-4 text-center first:pl-0 last:pr-0 sm:px-8">
              <p className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
                $0
              </p>
              <p className="mt-1 font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
                Cost to upgrade
              </p>
            </div>
          </motion.div>
        </div>
      </section>

      {/* ===== BENEFITS GRID ===== */}
      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
        <motion.div
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: '-60px' }}
        >
          <motion.div variants={fadeUp} custom={0} className="mb-10 max-w-lg">
            <p className="mb-3 font-mono text-xs uppercase tracking-widest text-muted-foreground">
              Benefits
            </p>
            <h2 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
              Everything you need to scale
            </h2>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
              Premium partners get access to tools and support that make a
              measurable difference in their earnings.
            </p>
          </motion.div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {benefits.map((benefit, idx) => (
              <motion.div
                key={benefit.title}
                variants={fadeUp}
                custom={idx + 1}
                whileHover={{ y: -2, transition: { duration: 0.2 } }}
                className="group rounded-lg border border-border/60 bg-background p-6 transition-colors hover:border-border hover:bg-muted/20"
              >
                <div className="mb-4 flex size-10 items-center justify-center rounded-md border border-border/60 bg-muted/40 text-muted-foreground transition-colors group-hover:border-border group-hover:text-foreground">
                  {benefit.icon}
                </div>
                <h3 className="mb-2 text-sm font-semibold text-foreground">
                  {benefit.title}
                </h3>
                <p className="text-sm leading-relaxed text-muted-foreground">
                  {benefit.description}
                </p>
              </motion.div>
            ))}
          </div>
        </motion.div>
      </section>

      {/* ===== COMPARISON TABLE ===== */}
      <section className="border-t border-border/40 bg-muted/20">
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
                Standard vs Premium
              </h2>
              <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                See exactly what changes when you upgrade to premium
                partnership.
              </p>
            </motion.div>

            <motion.div
              variants={fadeUp}
              custom={1}
              className="overflow-hidden rounded-lg border border-border/60 bg-background"
            >
              {/* Table header */}
              <div className="grid grid-cols-3 gap-2 border-b border-border/60 bg-muted/30 px-4 py-3 font-mono text-[10px] uppercase tracking-wider text-muted-foreground sm:px-6">
                <span>Feature</span>
                <span className="text-center">Standard</span>
                <span className="text-center">Premium</span>
              </div>

              {/* Rows */}
              {comparisonRows.map((row, idx) => (
                <div
                  key={row.feature}
                  className={
                    'grid grid-cols-3 gap-2 border-b border-border/30 px-4 py-3.5 last:border-0 hover:bg-muted/20 transition-colors sm:px-6' +
                    (idx === 0 ? ' pt-4' : '')
                  }
                >
                  <span className="text-sm font-medium text-foreground">
                    {row.feature}
                  </span>
                  <span className="flex items-center justify-center gap-2 text-sm text-muted-foreground">
                    <Minus className="size-3.5 text-muted-foreground/30" />
                    {row.standard}
                  </span>
                  <span className="flex items-center justify-center gap-2 text-sm text-foreground">
                    <Check className="size-3.5 text-foreground/60" />
                    {row.premium}
                  </span>
                </div>
              ))}
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* ===== DARK CTA ===== */}
      <section className="border-t border-border/40 bg-neutral-950 text-neutral-50">
        <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6 sm:py-28 lg:px-8">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: '-60px' }}
            className="mx-auto max-w-2xl text-center"
          >
            <motion.h2
              variants={fadeUp}
              custom={0}
              className="mb-4 text-2xl font-semibold tracking-tight sm:text-3xl"
            >
              Ready to go premium?
            </motion.h2>
            <motion.p
              variants={fadeUp}
              custom={1}
              className="mb-10 text-base leading-relaxed text-neutral-400"
            >
              Apply for premium partnership and start earning more from day one.
            </motion.p>
            <motion.div
              variants={fadeUp}
              custom={2}
              className="flex flex-col items-center justify-center gap-3 sm:flex-row"
            >
              <Button
                size="lg"
                onClick={() => navigate('apply')}
                className="gap-2 bg-neutral-50 text-neutral-950 hover:bg-neutral-200 px-8"
              >
                APPLY NOW
                <ArrowRight className="size-4" />
              </Button>
              <Button
                size="lg"
                variant="outline"
                onClick={() => navigate('support')}
                className="gap-2 border-neutral-700 text-neutral-300 hover:bg-neutral-800 hover:text-neutral-50 px-8"
              >
                CONTACT SALES
              </Button>
            </motion.div>
          </motion.div>
        </div>
      </section>
    </div>
  );
}
