'use client';

import { useRef, useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { ArrowRight } from 'lucide-react';
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

const roles = [
  { name: 'Consultants', desc: 'You advise companies on infrastructure. You already have the trust.' },
  { name: 'Agencies', desc: 'You build and manage systems for clients. Distribution is natural.' },
  { name: 'MSPs', desc: 'You manage operations. Your clients depend on your recommendations.' },
  { name: 'Developers', desc: 'You build the software. Your network trusts your technical judgment.' },
  { name: 'Engineers', desc: 'You run production systems. You know what matters in infrastructure.' },
  { name: 'Founders', desc: 'You lead companies. Your network looks to you for tooling advice.' },
  { name: 'Creators', desc: 'You produce content about technology. Your audience listens.' },
  { name: 'Communities', desc: 'You run technical communities. Members trust shared recommendations.' },
];

export function PageHome() {
  const navigate = usePartnerStore((s) => s.navigate);

  return (
    <div>
      {/* ===== HERO ===== */}
      <section className="relative overflow-hidden border-b border-border/40">
        {/* Subtle grid */}
        <div className="absolute inset-0 opacity-[0.025]">
          <svg width="100%" height="100%" className="h-full w-full">
            <defs>
              <pattern id="hero-grid" width="48" height="48" patternUnits="userSpaceOnUse">
                <path d="M 48 0 L 0 0 0 48" fill="none" stroke="currentColor" strokeWidth="0.5" />
              </pattern>
            </defs>
            <rect width="100%" height="100%" fill="url(#hero-grid)" />
          </svg>
        </div>

        <div className="relative mx-auto max-w-6xl px-4 pb-20 pt-20 sm:px-6 sm:pb-28 sm:pt-28 lg:px-8 lg:pb-36 lg:pt-36">
          <div className="grid items-center gap-12 lg:grid-cols-2 lg:gap-16">
            {/* Left: Copy */}
            <motion.div initial="hidden" animate="visible" className="max-w-xl">
              <motion.div
                variants={fadeUp}
                custom={0}
                className="mb-6 inline-flex items-center gap-2 rounded-full border border-border/80 bg-background px-4 py-1.5"
              >
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                <span className="font-mono text-xs tracking-wide text-muted-foreground">
                  Partner Network
                </span>
              </motion.div>

              <motion.h1
                variants={fadeUp}
                custom={1}
                className="text-4xl font-bold leading-[1.1] tracking-tight text-foreground sm:text-5xl lg:text-[3.5rem]"
              >
                Turn your network into{' '}
                <span className="text-foreground">recurring revenue.</span>
              </motion.h1>

              <motion.p
                variants={fadeUp}
                custom={2}
                className="mt-6 text-base leading-relaxed text-muted-foreground sm:text-lg"
              >
                Share RELIASTRA with people who depend on critical infrastructure. When they subscribe, you earn 30% every month they remain a paying customer.
              </motion.p>

              <motion.div
                variants={fadeUp}
                custom={3}
                className="mt-10 flex flex-col gap-3 sm:flex-row"
              >
                <Button
                  size="lg"
                  onClick={() => navigate('signup')}
                  className="gap-2 px-8"
                >
                  BECOME A PARTNER
                  <ArrowRight className="size-4" />
                </Button>
                <Button
                  variant="outline"
                  size="lg"
                  onClick={() => navigate('how-it-works')}
                  className="px-8"
                >
                  HOW IT WORKS
                </Button>
              </motion.div>
            </motion.div>

            {/* Right: Network visualization */}
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ delay: 0.3, duration: 0.8, ease: [0.25, 0.1, 0.25, 1] }}
              className="hidden lg:block"
            >
              <NetworkVisualization />
            </motion.div>
          </div>
        </div>
      </section>

      {/* ===== 30% COMMISSION CALL-OUT ===== */}
      <section className="border-b border-border/40 bg-muted/20">
        <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: '-60px' }}
            className="mx-auto max-w-2xl text-center"
          >
            <motion.p
              variants={fadeUp}
              custom={0}
              className="font-mono text-xs uppercase tracking-widest text-muted-foreground mb-6"
            >
              Recurring commission
            </motion.p>
            {/* 30% number with pulsing ring and scale animation */}
            <motion.div
              variants={fadeUp}
              custom={1}
              className="relative inline-flex items-center justify-center"
            >
              {/* Pulsing ring (inner) */}
              <motion.span
                className="pointer-events-none absolute rounded-full border border-foreground/10"
                initial={{ scale: 0.9, opacity: 0 }}
                whileInView={{ scale: [1, 1.15, 1], opacity: [0, 0.4, 0] }}
                viewport={{ once: true }}
                transition={{
                  duration: 2.5,
                  repeat: Infinity,
                  repeatDelay: 1.5,
                  ease: 'easeInOut',
                }}
                style={{
                  width: '220px',
                  height: '220px',
                }}
              />
              {/* Pulsing ring (outer) */}
              <motion.span
                className="pointer-events-none absolute rounded-full border border-foreground/5"
                initial={{ scale: 0.9, opacity: 0 }}
                whileInView={{ scale: [1, 1.3, 1], opacity: [0, 0.2, 0] }}
                viewport={{ once: true }}
                transition={{
                  duration: 2.5,
                  repeat: Infinity,
                  repeatDelay: 1.5,
                  ease: 'easeInOut',
                  delay: 0.4,
                }}
                style={{
                  width: '220px',
                  height: '220px',
                }}
              />
              <motion.span
                className="text-7xl sm:text-8xl lg:text-9xl font-bold tracking-tight text-foreground"
                initial={{ scale: 0.85, opacity: 0 }}
                whileInView={{ scale: 1, opacity: 1 }}
                viewport={{ once: true }}
                transition={{
                  duration: 0.8,
                  ease: [0.25, 0.1, 0.25, 1],
                }}
              >
                30
              </motion.span>
              <motion.span
                className="text-4xl sm:text-5xl font-bold text-muted-foreground"
                initial={{ scale: 0.85, opacity: 0 }}
                whileInView={{ scale: 1, opacity: 1 }}
                viewport={{ once: true }}
                transition={{
                  duration: 0.8,
                  ease: [0.25, 0.1, 0.25, 1],
                }}
              >
                %
              </motion.span>
            </motion.div>
            <motion.p
              variants={fadeUp}
              custom={2}
              className="mt-4 text-base text-muted-foreground"
            >
              Every month a referred customer remains subscribed.
            </motion.p>

            {/* Visual arithmetic flow with connecting line */}
            <motion.div variants={fadeUp} custom={3} className="mt-10 inline-block">
              <div className="rounded-lg border border-border/60 bg-background p-6 sm:p-8">
                {/* Row 1: Customer pays → You earn */}
                <div className="flex flex-col items-center gap-3 sm:flex-row sm:items-center sm:gap-0 sm:justify-center">
                  <div className="text-center sm:text-right">
                    <p className="font-mono text-[11px] uppercase tracking-widest text-muted-foreground/60 mb-1.5">
                      Customer pays
                    </p>
                    <p className="font-mono text-lg font-semibold text-muted-foreground">
                      $49/mo
                    </p>
                  </div>

                  {/* Connecting arrow */}
                  <div className="flex items-center justify-center px-5 py-1">
                    <svg width="56" height="20" viewBox="0 0 56 20" fill="none" className="text-muted-foreground/30">
                      <path d="M0 10h48M40 3l7 7-7 7" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </div>

                  <div className="text-center sm:text-left">
                    <p className="font-mono text-[11px] uppercase tracking-widest text-muted-foreground/60 mb-1.5">
                      You earn (30%)
                    </p>
                    <p className="font-mono text-lg font-bold text-foreground">
                      $14.70/mo
                    </p>
                  </div>
                </div>

                {/* Vertical connector */}
                <div className="flex justify-center py-3">
                  <div className="h-4 w-px bg-border" />
                </div>

                {/* Row 2: Recurring note */}
                <p className="text-center text-sm text-muted-foreground">
                  They stay subscribed.{' '}
                  <span className="font-semibold text-foreground">You keep earning.</span>
                </p>
              </div>
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* ===== WHO IS THIS FOR ===== */}
      <section>
        <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6 sm:py-28 lg:px-8">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: '-60px' }}
          >
            <motion.div variants={fadeUp} custom={0} className="mb-4 max-w-lg">
              <p className="mb-3 font-mono text-xs uppercase tracking-widest text-muted-foreground">
                Who is this for
              </p>
              <h2 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
                You already have access to the people who need RELIASTRA.
              </h2>
            </motion.div>

            <motion.div
              variants={fadeUp}
              custom={1}
              className="mt-12 grid gap-px overflow-hidden rounded-lg border border-border/60 bg-border/60 sm:grid-cols-2 lg:grid-cols-4"
            >
              {roles.map((role) => (
                <motion.div
                  key={role.name}
                  whileHover={{ boxShadow: 'inset 0 0 0 1px rgba(0,0,0,0.15)' }}
                  transition={{ duration: 0.2, ease: [0.25, 0.1, 0.25, 1] }}
                  className="bg-background p-6 transition-all duration-200 hover:bg-muted/30 hover:-translate-y-px"
                >
                  <h3 className="mb-2 text-sm font-semibold text-foreground">
                    {role.name}
                  </h3>
                  <p className="text-sm leading-relaxed text-muted-foreground">
                    {role.desc}
                  </p>
                </motion.div>
              ))}
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* ===== ANIMATED NUMBER COUNTERS ===== */}
      <CounterSection />

      {/* ===== YOU DON'T NEED A HUGE AUDIENCE ===== */}
      <section className="border-t border-border/40 bg-muted/20">
        <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6 sm:py-28 lg:px-8">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: '-60px' }}
            className="grid items-center gap-12 lg:grid-cols-2"
          >
            <motion.div variants={fadeUp} custom={0}>
              <p className="mb-3 font-mono text-xs uppercase tracking-widest text-muted-foreground">
                Distribution philosophy
              </p>
              <h2 className="mb-4 text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
                You don&apos;t need a huge audience.
              </h2>
              <p className="text-base leading-relaxed text-muted-foreground">
                You need access to the right people.
              </p>
            </motion.div>

            <motion.div variants={fadeUp} custom={1} className="space-y-6">
              <div className="rounded-lg border border-border/60 bg-background p-6">
                <div className="flex items-center gap-4">
                  <span className="font-mono text-lg font-semibold text-muted-foreground/50">
                    100,000 followers
                  </span>
                  <span className="text-2xl text-muted-foreground/30">/=</span>
                  <span className="font-mono text-lg font-semibold text-muted-foreground/50">
                    100,000 customers
                  </span>
                </div>
              </div>
              <div className="rounded-lg border-2 border-foreground/80 bg-background p-6">
                <div className="flex items-center gap-4">
                  <span className="font-mono text-lg font-semibold text-foreground">
                    10 relevant client relationships
                  </span>
                  <span className="text-2xl text-foreground">=</span>
                  <span className="font-mono text-lg font-semibold text-foreground">
                    real distribution
                  </span>
                </div>
              </div>
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* ===== PRODUCT CONNECTION ===== */}
      <section className="border-t border-border/40">
        <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6 sm:py-28 lg:px-8">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: '-60px' }}
          >
            <motion.div variants={fadeUp} custom={0} className="mb-12 max-w-lg">
              <p className="mb-3 font-mono text-xs uppercase tracking-widest text-muted-foreground">
                What you&apos;re referring
              </p>
              <h2 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
                You&apos;re not referring another uptime monitor.
              </h2>
            </motion.div>

            <motion.div
              variants={fadeUp}
              custom={1}
              className="grid gap-px overflow-hidden rounded-lg border border-border/60 bg-border/60 sm:grid-cols-3"
            >
              {[
                {
                  step: '01',
                  title: 'TRACK',
                  desc: 'Know what happened. Full incident timeline with evidence collection.',
                },
                {
                  step: '02',
                  title: 'CORRELATE',
                  desc: 'Find the dependency. Cross-system correlation reveals root causes.',
                },
                {
                  step: '03',
                  title: 'PROVE',
                  desc: 'Produce the evidence. Actionable reports for stakeholders and audits.',
                },
              ].map((item) => (
                <div key={item.step} className="bg-background p-8 transition-all duration-200 hover:bg-muted/20">
                  <span className="mb-4 block font-mono text-xs tracking-widest text-muted-foreground/60">
                    {item.step}
                  </span>
                  <h3 className="mb-2 text-lg font-semibold tracking-tight text-foreground">
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

      {/* ===== TESTIMONIALS / SOCIAL PROOF ===== */}
      <section className="border-t border-border/40">
        <div className="mx-auto max-w-6xl px-4 py-20 sm:px-6 sm:py-28 lg:px-8">
          <motion.div
            initial="hidden"
            whileInView="visible"
            viewport={{ once: true, margin: '-60px' }}
          >
            <motion.div variants={fadeUp} custom={0} className="mb-12 max-w-lg">
              <p className="mb-3 font-mono text-xs uppercase tracking-widest text-muted-foreground">
                What partners say
              </p>
              <h2 className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl">
                Trusted by infrastructure professionals.
              </h2>
            </motion.div>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <motion.div
                variants={fadeUp}
                custom={1}
              >
                <TestimonialCard
                  quote="I recommended RELIASTRA to three infrastructure clients during a consulting engagement. Two subscribed within a week. I now earn recurring revenue from work I was already doing."
                  name="Marcus Webb"
                  role="Infrastructure Consultant"
                  badge="$440+/mo earned"
                />
              </motion.div>
              <motion.div
                variants={fadeUp}
                custom={2}
              >
                <TestimonialCard
                  quote="Our agency runs on RELIASTRA internally. When clients ask what we use for incident correlation, the answer naturally leads to a referral. It feels organic, not salesy."
                  name="Sarah Lin"
                  role="CTO, Operations Agency"
                  badge="$870+/mo earned"
                />
              </motion.div>
              <motion.div
                variants={fadeUp}
                custom={3}
                className="sm:col-span-2 lg:col-span-1"
              >
                <TestimonialCard
                  quote="I posted a single breakdown of how we use RELIASTRA for post-incident reviews. That one piece of content generated eight trial signups and four paying customers."
                  name="David Okafor"
                  role="DevOps Content Creator"
                  badge="$580+/mo earned"
                />
              </motion.div>
            </div>
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
              Your next customer could already be in your network.
            </motion.h2>
            <motion.p
              variants={fadeUp}
              custom={1}
              className="mb-10 text-base leading-relaxed text-neutral-400"
            >
              Get someone to subscribe. Earn 30% every month. It&apos;s that simple.
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

// --- Animated Counter Section ---
function CounterSection() {
  const sectionRef = useRef<HTMLElement>(null);
  const [started, setStarted] = useState(false);

  useEffect(() => {
    const el = sectionRef.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          const t = setTimeout(() => setStarted(true), 300);
          observer.disconnect();
        }
      },
      { threshold: 0.1 }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <section ref={sectionRef} className="border-y border-border/40 bg-muted/20">
      <div className="mx-auto max-w-6xl px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.5, ease: [0.25, 0.1, 0.25, 1] }}
          className="grid grid-cols-2 divide-x divide-border/40 lg:grid-cols-4"
        >
          <CounterItem target={30} prefix="" suffix="%" label="Recurring commission" active={started} />
          <CounterItem target={49} prefix="$" suffix="/mo" label="Starting plan price" active={started} delay={0.1} />
          <CounterItem target={90} prefix="" suffix=" days" label="Attribution window" active={started} delay={0.2} />
          <CounterItem target={0} prefix="$" suffix="" label="Cost to join" active={started} isZero delay={0.3} />
        </motion.div>
      </div>
    </section>
  );
}

// --- Animated Counter Item ---
function CounterItem({
  target,
  prefix,
  suffix,
  label,
  isZero = false,
  active = false,
  delay = 0,
}: {
  target: number;
  prefix: string;
  suffix: string;
  label: string;
  isZero?: boolean;
  active?: boolean;
  delay?: number;
}) {
  const [displayValue, setDisplayValue] = useState(0);

  useEffect(() => {
    if (!active) return;

    const startTimeout = setTimeout(() => {
      if (isZero) {
        setDisplayValue(0);
        return;
      }

      const duration = 1400;
      const startTime = performance.now();

      const tick = (now: number) => {
        const elapsed = now - startTime;
        const progress = Math.min(elapsed / duration, 1);
        // Ease out cubic
        const eased = 1 - Math.pow(1 - progress, 3);
        setDisplayValue(Math.round(eased * target));
        if (progress < 1) {
          requestAnimationFrame(tick);
        }
      };

      requestAnimationFrame(tick);
    }, delay * 1000);

    return () => clearTimeout(startTimeout);
  }, [active, target, isZero, delay]);

  return (
    <div className="py-8 sm:py-10 text-center px-4 first:pl-0">
      {isZero ? (
        <motion.span
          className="font-mono tabular-nums text-3xl font-bold text-foreground sm:text-4xl"
          initial={{ scale: 0.9, opacity: 0 }}
          animate={active ? { scale: [1, 1.05, 1], opacity: 1 } : {}}
          transition={{ duration: 0.8, ease: [0.25, 0.1, 0.25, 1], delay }}
        >
          {prefix}0{suffix}
        </motion.span>
      ) : (
        <span className="font-mono tabular-nums text-3xl font-bold text-foreground sm:text-4xl">
          {prefix}{displayValue}{suffix}
        </span>
      )}
      <p className="mt-2 font-mono text-xs uppercase tracking-widest text-muted-foreground">
        {label}
      </p>
    </div>
  );
}

// --- Testimonial Card ---
function TestimonialCard({
  quote,
  name,
  role,
  badge,
}: {
  quote: string;
  name: string;
  role: string;
  badge: string;
}) {
  return (
    <div className="h-full border border-border/60 rounded-lg bg-background p-6 transition-all duration-200 hover:-translate-y-px hover:border-foreground/15 hover:shadow-sm">
      <p className="mb-1 font-mono text-xs text-muted-foreground">
        PARTNER TESTIMONIAL
      </p>
      <p className="mt-4 text-sm leading-relaxed text-foreground/90">
        <span className="text-3xl leading-none text-foreground/15 select-none">
          &ldquo;
        </span>
        {quote}
      </p>
      <div className="mt-6">
        <p className="text-sm font-semibold text-foreground">{name}</p>
        <p className="text-xs text-muted-foreground">{role}</p>
        <span className="mt-3 inline-flex items-center rounded-full border border-emerald-500/20 bg-emerald-500/10 px-3 py-1 font-mono text-xs font-semibold text-emerald-600">
          {badge}
        </span>
      </div>
    </div>
  );
}

// --- Network Visualization SVG ---
function NetworkVisualization() {
  return (
    <div className="relative w-full aspect-square max-w-md mx-auto">
      <svg viewBox="0 0 400 400" className="w-full h-full" fill="none">
        {/* Connection lines */}
        <line x1="100" y1="80" x2="200" y2="200" stroke="currentColor" strokeWidth="1" className="text-border" />
        <line x1="200" y1="200" x2="300" y2="320" stroke="currentColor" strokeWidth="1" className="text-border" />
        <line x1="300" y1="320" x2="100" y2="320" stroke="currentColor" strokeWidth="1" className="text-border" />

        {/* Animated data packets */}
        <motion.circle
          r="3"
          fill="currentColor"
          className="text-foreground/40"
          animate={{
            cx: [100, 200],
            cy: [80, 200],
            opacity: [0, 1, 1, 0],
          }}
          transition={{
            duration: 3,
            repeat: Infinity,
            repeatDelay: 1,
            ease: 'linear',
          }}
        />
        <motion.circle
          r="3"
          fill="currentColor"
          className="text-foreground/40"
          animate={{
            cx: [200, 300],
            cy: [200, 320],
            opacity: [0, 1, 1, 0],
          }}
          transition={{
            duration: 3,
            repeat: Infinity,
            repeatDelay: 1,
            ease: 'linear',
            delay: 1.5,
          }}
        />
        <motion.circle
          r="3"
          fill="currentColor"
          className="text-emerald-500"
          animate={{
            cx: [300, 100],
            cy: [320, 320],
            opacity: [0, 1, 1, 0],
          }}
          transition={{
            duration: 3,
            repeat: Infinity,
            repeatDelay: 1,
            ease: 'linear',
            delay: 3,
          }}
        />

        {/* Node: YOU */}
        <g>
          <rect x="68" y="48" width="64" height="64" rx="8" stroke="currentColor" strokeWidth="1.5" className="text-border" />
          <text x="100" y="74" textAnchor="middle" className="fill-foreground text-[10px] font-mono" fontFamily="monospace" fontSize="10" fontWeight="600">YOU</text>
          <text x="100" y="92" textAnchor="middle" className="fill-muted-foreground text-[8px] font-mono" fontFamily="monospace" fontSize="8">referral</text>
        </g>

        {/* Node: RELIASTRA */}
        <g>
          <rect x="152" y="168" width="96" height="64" rx="8" stroke="currentColor" strokeWidth="1.5" className="text-foreground" />
          <text x="200" y="196" textAnchor="middle" className="fill-foreground text-[10px] font-mono" fontFamily="monospace" fontSize="10" fontWeight="600">RELIASTRA</text>
          <text x="200" y="214" textAnchor="middle" className="fill-muted-foreground text-[8px] font-mono" fontFamily="monospace" fontSize="8">platform</text>
        </g>

        {/* Node: SUBSCRIBER */}
        <g>
          <rect x="268" y="288" width="64" height="64" rx="8" stroke="currentColor" strokeWidth="1.5" className="text-border" />
          <text x="300" y="314" textAnchor="middle" className="fill-foreground text-[10px] font-mono" fontFamily="monospace" fontSize="10" fontWeight="600">CUSTOMER</text>
          <text x="300" y="332" textAnchor="middle" className="fill-muted-foreground text-[8px] font-mono" fontFamily="monospace" fontSize="8">subscribed</text>
        </g>

        {/* Node: YOU EARN */}
        <g>
          <rect x="60" y="288" width="80" height="64" rx="8" stroke="currentColor" strokeWidth="1.5" className="text-emerald-600" />
          <text x="100" y="314" textAnchor="middle" className="fill-emerald-600 text-[10px] font-mono" fontFamily="monospace" fontSize="10" fontWeight="600">YOU EARN</text>
          <text x="100" y="332" textAnchor="middle" className="fill-emerald-600/60 text-[8px] font-mono" fontFamily="monospace" fontSize="8">30%/month</text>
        </g>

        {/* Edge labels */}
        <text x="138" y="130" textAnchor="middle" className="fill-muted-foreground/50 text-[8px] font-mono" fontFamily="monospace" fontSize="8" transform="rotate(-40 138 130)">share link</text>
        <text x="260" y="260" textAnchor="middle" className="fill-muted-foreground/50 text-[8px] font-mono" fontFamily="monospace" fontSize="8" transform="rotate(40 260 260)">subscribes</text>
        <text x="200" y="340" textAnchor="middle" className="fill-emerald-600/50 text-[8px] font-mono" fontFamily="monospace" fontSize="8">recurring value</text>
      </svg>
    </div>
  );
}
