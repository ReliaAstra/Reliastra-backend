'use client';

import { motion } from 'framer-motion';
import { ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { usePartnerStore } from '@/stores/partner-store';
import { cn } from '@/lib/utils';

const fadeUp = {
  hidden: { opacity: 0, y: 20 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.07, duration: 0.6, ease: [0.25, 0.1, 0.25, 1] },
  }),
};

const staggerContainer = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.14,
      delayChildren: 0.15,
    },
  },
};

const staggerChild = {
  hidden: { opacity: 0, y: 28 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.6, ease: [0.25, 0.1, 0.25, 1] },
  },
};

const steps = [
  {
    number: '01',
    title: 'SIGN UP',
    description:
      'Create your partner account. No fees, no contracts. Just a short registration to get started.',
  },
  {
    number: '02',
    title: 'GET YOUR LINK',
    description:
      'Receive a unique referral link instantly. Share it with people who depend on reliable infrastructure.',
  },
  {
    number: '03',
    title: 'SHARE IT',
    description:
      'Send it via email, embed it in your content, or share it directly. No restrictions on how you distribute.',
  },
  {
    number: '04',
    title: 'EARN 30% EVERY MONTH',
    description:
      'When someone subscribes through your link, you earn 30% of their monthly subscription — for as long as they stay.',
    accent: true,
  },
];

const roles = [
  {
    name: 'Consultants',
    desc: 'You already advise on infrastructure.',
  },
  {
    name: 'Agencies',
    desc: 'Distribution is natural for your client engagements.',
  },
  {
    name: 'MSPs',
    desc: 'Your clients depend on your recommendations.',
  },
  {
    name: 'Engineers',
    desc: 'You run production. Your peers trust your judgment.',
  },
  {
    name: 'Founders',
    desc: 'You decide what tools your company uses.',
  },
  {
    name: 'Creators',
    desc: 'Your audience trusts your technical recommendations.',
  },
];

function PulseLine() {
  return (
    <div className="relative flex w-10 shrink-0 items-center justify-center lg:w-14">
      <div className="h-px w-full bg-border" />
      <motion.div
        className="absolute left-0 h-px w-4 bg-foreground/40"
        animate={{ left: ['0%', 'calc(100% - 16px)'] }}
        transition={{
          duration: 2,
          repeat: Infinity,
          repeatDelay: 1,
          ease: 'easeInOut',
        }}
      />
      <svg
        width="12"
        height="12"
        viewBox="0 0 12 12"
        fill="none"
        className="absolute right-0 -translate-y-px text-muted-foreground/40"
      >
        <path
          d="M2 6h6M6 2l4 4-4 4"
          stroke="currentColor"
          strokeWidth="1.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}

export function PageHowItWorks() {
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
              PROCESS
            </motion.p>
            <motion.h1
              variants={fadeUp}
              custom={1}
              className="text-3xl font-bold tracking-tight text-foreground sm:text-4xl"
            >
              How it works.
            </motion.h1>
            <motion.p
              variants={fadeUp}
              custom={2}
              className="mt-4 text-base leading-relaxed text-muted-foreground"
            >
              From referral to recurring revenue. The entire process is designed
              to be straightforward and transparent.
            </motion.p>
            <motion.div variants={fadeUp} custom={3} className="mt-8 flex flex-wrap gap-6">
              {[
                { value: '30%', label: 'Recurring commission' },
                { value: '90d', label: 'Attribution window' },
                { value: '$49/mo', label: 'Starting plan' },
                { value: '$0', label: 'To join' },
              ].map((m) => (
                <div key={m.label} className="flex items-baseline gap-1.5">
                  <span className="font-mono text-xl font-semibold tracking-tight">{m.value}</span>
                  <span className="text-[11px] text-muted-foreground">{m.label}</span>
                </div>
              ))}
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* ===== 4-STEP VISUAL FLOW (HERO) ===== */}
      <section className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8 lg:py-28">
        <motion.div
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: '-60px' }}
          variants={staggerContainer}
        >
          {/* Desktop: horizontal row with animated connectors */}
          <div className="hidden lg:grid lg:grid-cols-4 lg:gap-0">
            {steps.map((step, i) => (
              <div key={step.number} className="flex items-stretch">
                {/* Connector line with pulse */}
                {i > 0 && <PulseLine />}
                <motion.div
                  variants={staggerChild}
                  whileHover={{ y: -2 }}
                  transition={{ duration: 0.2, ease: [0.25, 0.1, 0.25, 1] }}
                  className={cn(
                    'flex-1 rounded-lg border bg-background p-8 xl:p-10 transition-colors duration-200',
                    step.accent
                      ? 'border-emerald-500/40 bg-emerald-50/20 hover:border-emerald-500/60'
                      : 'border-border/60 hover:border-border'
                  )}
                >
                  <motion.span
                    className="mb-5 block font-mono text-4xl font-extralight leading-none text-muted-foreground/30"
                    animate={{ scale: [1, 1.05, 1] }}
                    transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
                  >
                    {step.number}
                  </motion.span>
                  <h3 className="mb-2.5 text-xs font-semibold uppercase tracking-widest text-foreground">
                    {step.title}
                  </h3>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    {step.description}
                  </p>
                </motion.div>
              </div>
            ))}
          </div>

          {/* Mobile / Tablet: vertical stack with down arrows */}
          <div className="flex flex-col gap-3 lg:hidden">
            {steps.map((step, i) => (
              <div key={step.number}>
                <motion.div
                  variants={staggerChild}
                  whileHover={{ y: -2 }}
                  transition={{ duration: 0.2, ease: [0.25, 0.1, 0.25, 1] }}
                  className={cn(
                    'rounded-lg border bg-background p-6 sm:p-8 transition-colors duration-200',
                    step.accent
                      ? 'border-emerald-500/40 bg-emerald-50/20'
                      : 'border-border/60'
                  )}
                >
                  <div className="flex items-start gap-4 sm:items-start">
                    <motion.span
                      className="shrink-0 font-mono text-4xl font-extralight leading-none text-muted-foreground/30"
                      animate={{ scale: [1, 1.05, 1] }}
                      transition={{ duration: 3, repeat: Infinity, ease: 'easeInOut' }}
                    >
                      {step.number}
                    </motion.span>
                    <div>
                      <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-widest text-foreground">
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
                    <svg
                      width="16"
                      height="16"
                      viewBox="0 0 16 16"
                      fill="none"
                      className="text-muted-foreground/30"
                    >
                      <path
                        d="M8 2v12M4 10l4 4 4-4"
                        stroke="currentColor"
                        strokeWidth="1.5"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </div>
                )}
              </div>
            ))}
          </div>
        </motion.div>
      </section>

      {/* ===== TRACKING DETAILS ===== */}
      <section className="border-t border-border/40">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8 lg:py-28">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: '-60px' }}
          >
            <motion.div variants={fadeUp} custom={0} className="mb-12 max-w-lg">
              <p className="mb-3 font-mono text-xs uppercase tracking-widest text-muted-foreground">
                Tracking
              </p>
              <h2 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
                How attribution works
              </h2>
              <p className="mt-3 text-sm text-muted-foreground leading-relaxed">
                We use industry-standard cookie-based tracking with a generous
                attribution window to ensure you get credit for your referrals.
              </p>
            </motion.div>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {[
                { label: 'Cookie duration', value: '90 days', desc: 'From first click to signup' },
                { label: 'Attribution', value: 'Last-click', desc: 'Most recent partner gets credit' },
                { label: 'Commission lock', value: 'Instant', desc: 'Credited when subscription starts' },
                { label: 'Fraud protection', value: 'Active', desc: 'Self-referrals are filtered out' },
              ].map((item, i) => (
                <motion.div
                  key={item.label}
                  variants={fadeUp}
                  custom={i + 1}
                  className="rounded-lg border border-border/60 bg-background p-6 transition-all duration-200 hover:-translate-y-px hover:border-foreground/15"
                >
                  <p className="font-mono text-lg font-semibold tracking-tight">{item.value}</p>
                  <p className="text-xs font-medium text-foreground mt-1">{item.label}</p>
                  <p className="text-[11px] text-muted-foreground mt-1.5 leading-relaxed">{item.desc}</p>
                </motion.div>
              ))}
            </div>
          </motion.div>
        </div>
      </section>

      {/* ===== ELIGIBILITY SECTION ===== */}
      <section className="border-t border-border/40 bg-muted/30">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8 lg:py-28">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: '-60px' }}
          >
            <motion.div variants={fadeUp} custom={0} className="mb-12 max-w-lg">
              <p className="mb-3 font-mono text-xs uppercase tracking-widest text-muted-foreground">
                Eligibility
              </p>
              <h2 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
                Who should apply?
              </h2>
            </motion.div>

            <motion.div
              variants={fadeUp}
              custom={1}
              className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
            >
              {roles.map((role) => (
                <div
                  key={role.name}
                  className="rounded-lg border border-border/60 bg-background p-6 transition-all duration-200 hover:border-border hover:-translate-y-px"
                >
                  <h3 className="mb-1.5 text-sm font-semibold tracking-tight text-foreground">
                    {role.name}
                  </h3>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    {role.desc}
                  </p>
                </div>
              ))}
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* ===== DARK CTA SECTION ===== */}
      <section className="border-t border-border/40 bg-neutral-950 text-neutral-50">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8 lg:py-28">
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
              Your network already has people who need RELIASTRA.
            </motion.h2>
            <motion.p
              variants={fadeUp}
              custom={1}
              className="mb-10 text-base leading-relaxed text-neutral-400"
            >
              The process takes minutes. The earnings last as long as your
              referrals stay subscribed.
            </motion.p>
            <motion.div variants={fadeUp} custom={2}>
              <Button
                size="lg"
                onClick={() => navigate('signup')}
                className="gap-2 bg-neutral-50 text-neutral-950 hover:bg-neutral-200 px-8"
              >
                BECOME A PARTNER
                <ArrowRight className="size-4" />
              </Button>
            </motion.div>
          </motion.div>
        </div>
      </section>
    </div>
  );
}
