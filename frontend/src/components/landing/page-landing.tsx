'use client';

import { useState, useEffect, useRef } from 'react';
import { motion, useInView, type Variants } from 'framer-motion';
import { useTheme } from 'next-themes';
import {
  Sun,
  Moon,
  Menu,
  X,
  ArrowRight,
  AlertTriangle,
  FileSearch,
  DollarSign,
  Activity,
  Link2,
  ShieldCheck,
  Check,
  ChevronRight,
  Zap,
  Clock,
  LayoutDashboard,
  Wallet,
  Star,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from '@/components/ui/accordion';
import { Badge } from '@/components/ui/badge';
import { usePartnerStore } from '@/stores/partner-store';
import type { PartnerPage } from '@/types/partner';

/* ─── Animation helpers ─────────────────────────────── */

const fadeUp: Variants = {
  hidden: { opacity: 0, y: 24 },
  visible: (i: number = 0) => ({
    opacity: 1,
    y: 0,
    transition: { duration: 0.5, delay: i * 0.1, ease: [0.25, 0.1, 0.25, 1] },
  }),
};

const staggerContainer: Variants = {
  hidden: {},
  visible: {
    transition: { staggerChildren: 0.1 },
  },
};

function Section({
  children,
  className,
  id,
}: {
  children: React.ReactNode;
  className?: string;
  id?: string;
}) {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: '-60px' });
  return (
    <motion.section
      ref={ref}
      id={id}
      initial="hidden"
      animate={isInView ? 'visible' : 'hidden'}
      variants={fadeUp}
      className={className}
    >
      {children}
    </motion.section>
  );
}

/* ─── Vendor latency bars (animated) ────────────────── */

const vendors = [
  { name: 'Stripe', ms: 124, color: 'bg-emerald-500' },
  { name: 'Auth0', ms: 342, color: 'bg-amber-500' },
  { name: 'Vercel', ms: 48, color: 'bg-emerald-500' },
  { name: 'Twilio', ms: 187, color: 'bg-zinc-400' },
  { name: 'SendGrid', ms: 96, color: 'bg-emerald-500' },
];

function VendorBar({ name, ms, color }: { name: string; ms: number; color: string }) {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true });
  const maxMs = 400;
  const widthPct = Math.min((ms / maxMs) * 100, 100);
  return (
    <div ref={ref} className="flex items-center gap-3">
      <span className="w-20 shrink-0 text-right text-xs font-medium text-zinc-500">
        {name}
      </span>
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
        <motion.div
          initial={{ width: 0 }}
          animate={isInView ? { width: `${widthPct}%` } : { width: 0 }}
          transition={{ duration: 0.8, delay: 0.2, ease: 'easeOut' }}
          className={`h-full rounded-full ${color}`}
        />
      </div>
      <span
        className={`w-14 shrink-0 text-right font-mono text-xs ${
          ms > 250 ? 'text-amber-600' : ms > 150 ? 'text-zinc-500' : 'text-emerald-600'
        }`}
      >
        {ms}ms
      </span>
    </div>
  );
}

/* ─── Mini Dashboard (Hero) ──────────────────────────── */

function MiniDashboard() {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: '-40px' });
  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: 20 }}
      animate={isInView ? { opacity: 1, y: 0 } : { opacity: 0, y: 20 }}
      transition={{ duration: 0.7, delay: 0.3 }}
      className="mx-auto mt-12 max-w-xl rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-700 dark:bg-zinc-900"
    >
      <div className="mb-4 flex items-center gap-2">
        <div className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
        <span className="text-xs font-medium text-zinc-500">LIVE VENDOR LATENCY</span>
        <span className="ml-auto font-mono text-[10px] text-zinc-400">updated 4s ago</span>
      </div>
      <div className="space-y-2.5">
        {vendors.map((v) => (
          <VendorBar key={v.name} {...v} />
        ))}
      </div>
    </motion.div>
  );
}

/* ─── Navbar ─────────────────────────────────────────── */

function Navbar() {
  const navigate = usePartnerStore((s) => s.navigate);
  const { theme, setTheme } = useTheme();
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 16);
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const navItems: { label: string; page: PartnerPage }[] = [
    { label: 'Features', page: 'home' },
    { label: 'How It Works', page: 'how-it-works' },
    { label: 'Pricing', page: 'premium' },
    { label: 'Partners', page: 'home' },
    { label: 'Blog', page: 'home' },
    { label: 'Status', page: 'home' },
  ];

  const handleNav = (page: PartnerPage) => {
    navigate(page);
    setMobileOpen(false);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <nav
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        scrolled
          ? 'bg-white/80 border-b border-zinc-200 backdrop-blur-xl dark:bg-zinc-950/80 dark:border-zinc-800'
          : 'bg-transparent'
      }`}
    >
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4 sm:px-6">
        {/* Logo */}
        <button
          onClick={() => handleNav('landing')}
          className="font-mono text-sm font-bold tracking-widest text-zinc-900 dark:text-white hover:opacity-80 transition-opacity"
        >
          reliastra
        </button>

        {/* Desktop nav */}
        <div className="hidden items-center gap-1 md:flex">
          {navItems.map((item) => (
            <button
              key={item.label}
              onClick={() => handleNav(item.page)}
              className="rounded-md px-3 py-1.5 text-sm text-zinc-600 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
            >
              {item.label}
            </button>
          ))}
          {/* Theme toggle */}
          {theme && (
            <button
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              className="ml-1 rounded-md p-2 text-zinc-500 transition-colors hover:text-zinc-900 dark:hover:text-white"
              aria-label="Toggle theme"
            >
              {theme === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
            </button>
          )}
          <div className="ml-2 flex items-center gap-2">
            <button
              onClick={() => handleNav('login')}
              className="rounded-md px-3 py-1.5 text-sm text-zinc-600 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
            >
              Sign In
            </button>
            <Button
              size="sm"
              onClick={() => handleNav('login')}
              className="bg-zinc-900 text-white hover:bg-zinc-800 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
            >
              Start Free
            </Button>
          </div>
        </div>

        {/* Mobile hamburger */}
        <div className="flex items-center gap-2 md:hidden">
          {theme && (
            <button
              onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              className="rounded-md p-2 text-zinc-500 transition-colors hover:text-zinc-900 dark:hover:text-white"
              aria-label="Toggle theme"
            >
              {theme === 'dark' ? <Sun className="size-4" /> : <Moon className="size-4" />}
            </button>
          )}
          <button
            onClick={() => setMobileOpen(!mobileOpen)}
            className="rounded-md p-2 text-zinc-600 dark:text-zinc-400"
            aria-label="Toggle menu"
          >
            {mobileOpen ? <X className="size-5" /> : <Menu className="size-5" />}
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {mobileOpen && (
        <motion.div
          initial={{ opacity: 0, y: -4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -4 }}
          className="border-b border-zinc-200 bg-white/95 backdrop-blur-xl md:hidden dark:border-zinc-800 dark:bg-zinc-950/95"
        >
          <div className="space-y-1 px-4 py-3">
            {navItems.map((item) => (
              <button
                key={item.label}
                onClick={() => handleNav(item.page)}
                className="block w-full rounded-md px-3 py-2 text-left text-sm text-zinc-600 transition-colors hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"
              >
                {item.label}
              </button>
            ))}
            <div className="flex gap-2 pt-3">
              <Button
                variant="outline"
                className="flex-1"
                onClick={() => handleNav('login')}
              >
                Sign In
              </Button>
              <Button
                className="flex-1 bg-zinc-900 text-white hover:bg-zinc-800 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
                onClick={() => handleNav('login')}
              >
                Start Free
              </Button>
            </div>
          </div>
        </motion.div>
      )}
    </nav>
  );
}

/* ─── Problem Section ────────────────────────────────── */

const painPoints = [
  {
    icon: AlertTriangle,
    title: 'Blind to Vendor Failures',
    description:
      'Your monitoring tells you your app is down — but not why. External dependencies fail silently, and you waste hours in war rooms.',
  },
  {
    icon: FileSearch,
    title: 'No Causal Evidence',
    description:
      'When vendors cause outages, you have no timestamped proof. Negotiating SLA credits becomes a "he-said, she-said" battle.',
  },
  {
    icon: DollarSign,
    title: 'Credits Left on the Table',
    description:
      'Most teams never claim the SLA credits they deserve. Without evidence, vendors deny claims — and you pay the price.',
  },
];

/* ─── How It Works Steps ─────────────────────────────── */

const steps = [
  {
    icon: Activity,
    label: 'TRACK',
    title: 'Monitor Every Vendor',
    description:
      'Reliastra continuously monitors your external dependencies — APIs, SaaS services, CDNs — from multiple global vantage points.',
  },
  {
    icon: Link2,
    label: 'CORRELATE',
    title: 'Find the Real Cause',
    description:
      'When failures happen, Reliastra correlates vendor degradation with your incident timeline. No more guessing — you know exactly what failed.',
  },
  {
    icon: ShieldCheck,
    label: 'PROVE',
    title: 'Produce Evidence',
    description:
      'Get timestamped, tamper-proof evidence reports ready for vendor disputes, SLA credit claims, and internal post-mortems.',
  },
];

/* ─── Evidence Report Preview ────────────────────────── */

const evidenceLines = [
  { time: '02:14:31 UTC', level: 'WARN', message: 'Auth0 /oauth/token latency exceeded 300ms threshold (342ms)' },
  { time: '02:14:33 UTC', level: 'ERROR', message: 'Stripe /v1/charges returned 503 Service Unavailable' },
  { time: '02:14:35 UTC', level: 'WARN', message: 'Auth0 /userinfo response time degraded to 890ms' },
  { time: '02:14:38 UTC', level: 'ERROR', message: 'Downstream service /api/checkout timed out (correlated with Stripe 503)' },
  { time: '02:14:42 UTC', level: 'INFO', message: 'Evidence snapshot captured — incident #INC-4821 linked to Stripe degradation window' },
];

/* ─── Partner Benefits ───────────────────────────────── */

const partnerBenefits = [
  {
    icon: Zap,
    title: '30% recurring commission',
    description: 'Earn every month your referrals stay subscribed.',
  },
  {
    icon: Clock,
    title: '90-day attribution window',
    description: 'Get credited for signups up to 90 days after your referral.',
  },
  {
    icon: LayoutDashboard,
    title: 'Real-time dashboard',
    description: 'Track clicks, signups, and earnings in real time.',
  },
  {
    icon: Wallet,
    title: 'Monthly crypto payouts',
    description: 'Get paid in USDC/USDT to your wallet, monthly.',
  },
];

/* ─── Pricing Tiers ──────────────────────────────────── */

const tiers = [
  {
    name: 'Free',
    price: '$0',
    period: '/forever',
    description: 'For individuals exploring vendor intelligence.',
    popular: false,
    features: [
      'Up to 5 vendors monitored',
      'Basic latency tracking',
      'Community support',
      'Weekly email reports',
    ],
  },
  {
    name: 'Starter',
    price: '$19',
    period: '/month',
    description: 'For small teams getting started with evidence.',
    popular: false,
    features: [
      'Up to 25 vendors monitored',
      'Correlation engine',
      'Evidence reports (PDF)',
      'Email support',
      'Daily email reports',
    ],
  },
  {
    name: 'Standard',
    price: '$49',
    period: '/month',
    description: 'For teams that need proof for SLA disputes.',
    popular: true,
    features: [
      'Up to 100 vendors monitored',
      'Advanced correlation',
      'Tamper-proof evidence',
      'Priority support',
      'Real-time alerts (Slack, PagerDuty)',
      'API access',
    ],
  },
  {
    name: 'Professional',
    price: '$99',
    period: '/month',
    description: 'For organizations with critical infrastructure.',
    popular: false,
    features: [
      'Unlimited vendors',
      'Custom SLA tracking',
      'Automated credit claims',
      'Dedicated account manager',
      'Custom integrations',
      'SOC 2 evidence compliance',
      'On-premise deployment option',
    ],
  },
];

/* ─── FAQ Items ───────────────────────────────────────── */

const faqItems = [
  {
    q: 'What does Reliastra actually monitor?',
    a: 'Reliastra monitors the external dependencies your application relies on — APIs (Stripe, Auth0, Twilio, etc.), SaaS platforms, CDNs, DNS providers, and any HTTP endpoint you specify. We track latency, error rates, availability, and response anomalies from multiple global vantage points.',
  },
  {
    q: 'How does the correlation engine work?',
    a: "When an incident occurs in your infrastructure, Reliastra cross-references your vendor health data with your incident timeline. If we detect that a vendor's degradation or outage aligns with your incident window, we flag it as a correlated cause and include it in your evidence report.",
  },
  {
    q: 'What kind of evidence do you produce?',
    a: 'Reliastra generates timestamped, tamper-proof evidence reports that include: vendor health timelines, latency graphs, error rate analysis, correlated incident windows, and SLA violation summaries. These reports are designed to be shared directly with vendors for SLA credit claims.',
  },
  {
    q: 'How do SLA credits work?',
    a: "Most SaaS vendors offer service credits when they fail to meet their SLA commitments (typically 99.9% or 99.99% uptime). The problem is proving the failure. Reliastra provides the evidence you need to file and win these claims — potentially saving thousands of dollars per incident.",
  },
  {
    q: 'Is my data secure?',
    a: 'Reliastra is built with security-first architecture. All data is encrypted at rest and in transit. We never store your API keys or credentials — we only monitor public-facing endpoints. We support SOC 2 compliance reports and offer on-premise deployment for Enterprise customers.',
  },
  {
    q: 'How quickly can I get started?',
    a: 'You can start monitoring your first vendor in under 5 minutes. Simply sign up, add your vendor endpoints, and Reliastra begins tracking immediately. No agent installation required for most use cases — we monitor from the outside in.',
  },
];

/* ═══════════════════════════════════════════════════════
   MAIN LANDING PAGE COMPONENT
   ═══════════════════════════════════════════════════════ */

export function PageLanding() {
  const navigate = usePartnerStore((s) => s.navigate);

  return (
    <div className="min-h-screen bg-white text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <Navbar />

      {/* ─── Hero ─────────────────────────────────────── */}
      <header className="relative overflow-hidden pt-28 pb-16 sm:pt-36 sm:pb-24">
        {/* Subtle grid background */}
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.03] dark:opacity-[0.04]"
          style={{
            backgroundImage:
              'linear-gradient(to right, #71717a 1px, transparent 1px), linear-gradient(to bottom, #71717a 1px, transparent 1px)',
            backgroundSize: '64px 64px',
          }}
        />
        <div className="relative mx-auto max-w-4xl px-4 text-center sm:px-6">
          <motion.div
            initial="hidden"
            animate="visible"
            variants={staggerContainer}
            className="flex flex-col items-center"
          >
            <motion.div variants={fadeUp} custom={0}>
              <Badge
                variant="outline"
                className="mb-6 border-zinc-300 font-mono text-[11px] tracking-wider text-zinc-600 dark:border-zinc-700 dark:text-zinc-400"
              >
                EXTERNAL DEPENDENCY INTELLIGENCE
              </Badge>
            </motion.div>

            <motion.h1
              variants={fadeUp}
              custom={1}
              className="text-4xl font-bold leading-tight tracking-tight sm:text-5xl md:text-6xl lg:text-7xl"
            >
              Your site went down.{' '}
              <span className="text-zinc-400 dark:text-zinc-500">
                Was it you, or your vendors?
              </span>
            </motion.h1>

            <motion.p
              variants={fadeUp}
              custom={2}
              className="mx-auto mt-6 max-w-2xl text-base leading-relaxed text-zinc-600 sm:text-lg dark:text-zinc-400"
            >
              Reliastra monitors your external dependencies, correlates failures
              with your incidents, and produces timestamped evidence you can use
              to claim SLA credits — or prove it wasn't your fault.
            </motion.p>

            <motion.div
              variants={fadeUp}
              custom={3}
              className="mt-8 flex flex-col gap-3 sm:flex-row sm:justify-center"
            >
              <Button
                size="lg"
                onClick={() => {
                  navigate('login');
                  window.scrollTo({ top: 0, behavior: 'smooth' });
                }}
                className="h-11 bg-zinc-900 px-8 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
              >
                Start Free
                <ArrowRight className="size-4" />
              </Button>
              <Button
                variant="outline"
                size="lg"
                onClick={() => {
                  navigate('home');
                  window.scrollTo({ top: 0, behavior: 'smooth' });
                }}
                className="h-11 px-8 text-sm font-medium"
              >
                See Live Data
              </Button>
            </motion.div>
          </motion.div>

          <MiniDashboard />
        </div>
      </header>

      {/* ─── Problem Section ────────────────────────────── */}
      <Section className="border-y border-zinc-100 bg-zinc-50/50 py-20 sm:py-28 dark:border-zinc-800 dark:bg-zinc-900/30">
        <div className="mx-auto max-w-5xl px-4 sm:px-6">
          <div className="mb-12 text-center">
            <p className="mb-3 font-mono text-xs tracking-widest text-zinc-500">
              THE PROBLEM
            </p>
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
              The 2 AM War Room
            </h2>
            <p className="mx-auto mt-4 max-w-2xl text-zinc-600 dark:text-zinc-400">
              Every outage starts the same way. Your monitoring lights up, but you
              can't tell if it's your code or your vendors. Hours are lost. Credits
              go unclaimed.
            </p>
          </div>
          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
            {painPoints.map((point, i) => (
              <motion.div
                key={point.title}
                variants={fadeUp}
                custom={i}
                className="rounded-xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900"
              >
                <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg border border-zinc-200 bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-800">
                  <point.icon className="size-5 text-zinc-700 dark:text-zinc-300" />
                </div>
                <h3 className="mb-2 text-sm font-semibold">{point.title}</h3>
                <p className="text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
                  {point.description}
                </p>
              </motion.div>
            ))}
          </div>
        </div>
      </Section>

      {/* ─── How It Works ──────────────────────────────── */}
      <Section className="py-20 sm:py-28">
        <div className="mx-auto max-w-5xl px-4 sm:px-6">
          <div className="mb-14 text-center">
            <p className="mb-3 font-mono text-xs tracking-widest text-zinc-500">
              HOW IT WORKS
            </p>
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
              Three steps to clarity
            </h2>
          </div>
          <div className="grid gap-8 md:grid-cols-3">
            {steps.map((step, i) => (
              <motion.div
                key={step.label}
                variants={fadeUp}
                custom={i}
                className="relative flex flex-col items-start"
              >
                {/* Connector line (desktop) */}
                {i < steps.length - 1 && (
                  <div className="absolute top-7 left-[calc(50%+32px)] hidden h-px w-[calc(100%-64px)] bg-zinc-200 md:block dark:bg-zinc-800" />
                )}
                <div className="relative mb-4 flex h-14 w-14 items-center justify-center rounded-xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-700 dark:bg-zinc-900">
                  <step.icon className="size-6 text-emerald-600" />
                </div>
                <span className="mb-1 font-mono text-xs font-medium tracking-wider text-emerald-600">
                  {step.label}
                </span>
                <h3 className="mb-2 text-base font-semibold">{step.title}</h3>
                <p className="text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
                  {step.description}
                </p>
              </motion.div>
            ))}
          </div>
        </div>
      </Section>

      {/* ─── Live Evidence Preview ──────────────────────── */}
      <Section className="border-y border-zinc-100 bg-zinc-50/50 py-20 sm:py-28 dark:border-zinc-800 dark:bg-zinc-900/30">
        <div className="mx-auto max-w-3xl px-4 sm:px-6">
          <div className="mb-10 text-center">
            <p className="mb-3 font-mono text-xs tracking-widest text-zinc-500">
              LIVE EVIDENCE
            </p>
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
              Proof you can hand to your vendor
            </h2>
            <p className="mx-auto mt-4 max-w-xl text-zinc-600 dark:text-zinc-400">
              Every incident produces a timestamped, structured evidence report
              ready for SLA credit claims.
            </p>
          </div>

          <motion.div
            variants={fadeUp}
            className="overflow-hidden rounded-xl border border-zinc-200 bg-zinc-950 dark:border-zinc-700"
          >
            {/* Terminal header */}
            <div className="flex items-center gap-2 border-b border-zinc-800 px-4 py-3">
              <div className="h-2.5 w-2.5 rounded-full bg-zinc-700" />
              <div className="h-2.5 w-2.5 rounded-full bg-zinc-700" />
              <div className="h-2.5 w-2.5 rounded-full bg-zinc-700" />
              <span className="ml-3 font-mono text-[11px] text-zinc-500">
                reliastra — evidence-report #INC-4821
              </span>
            </div>
            {/* Evidence lines */}
            <div className="space-y-0 p-4 font-mono text-xs leading-6 sm:text-sm">
              {evidenceLines.map((line, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, x: -8 }}
                  variants={fadeUp}
                  custom={i}
                  className="flex gap-3"
                >
                  <span className="shrink-0 text-zinc-600">{line.time}</span>
                  <span
                    className={`w-12 shrink-0 text-center font-medium ${
                      line.level === 'ERROR'
                        ? 'text-red-400'
                        : line.level === 'WARN'
                          ? 'text-amber-400'
                          : 'text-emerald-400'
                    }`}
                  >
                    {line.level}
                  </span>
                  <span className="text-zinc-300">{line.message}</span>
                </motion.div>
              ))}
            </div>
          </motion.div>
        </div>
      </Section>

      {/* ─── Partner Network CTA ────────────────────────── */}
      <section className="relative overflow-hidden bg-zinc-900 py-20 sm:py-28">
        {/* Decorative grid */}
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.04]"
          style={{
            backgroundImage:
              'linear-gradient(to right, #ffffff 1px, transparent 1px), linear-gradient(to bottom, #ffffff 1px, transparent 1px)',
            backgroundSize: '48px 48px',
          }}
        />
        {/* Radial glow */}
        <div className="pointer-events-none absolute left-1/2 top-0 -translate-x-1/2 h-[500px] w-[800px] bg-emerald-500/5 blur-3xl" />

        <Section className="relative mx-auto max-w-5xl px-4 sm:px-6">
          <div className="text-center">
            <p className="mb-3 font-mono text-xs tracking-widest text-emerald-400">
              PARTNER NETWORK
            </p>
            <h2 className="text-3xl font-bold tracking-tight text-white sm:text-4xl md:text-5xl">
              Earn 30% recurring commission
            </h2>
            <p className="mx-auto mt-5 max-w-2xl text-base leading-relaxed text-zinc-400 sm:text-lg">
              Turn your network into recurring revenue. Share Reliastra with teams
              that depend on critical infrastructure.
            </p>
          </div>

          {/* Benefit cards */}
          <div className="mt-14 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {partnerBenefits.map((benefit, i) => (
              <motion.div
                key={benefit.title}
                variants={fadeUp}
                custom={i}
                whileHover={{ scale: 1.03 }}
                transition={{ type: 'spring', stiffness: 400, damping: 25 }}
                className="rounded-xl border border-zinc-700/60 bg-zinc-800/50 p-5 backdrop-blur-sm"
              >
                <benefit.icon className="mb-3 size-5 text-emerald-400" />
                <h3 className="mb-1 text-sm font-semibold text-white">
                  {benefit.title}
                </h3>
                <p className="text-xs leading-relaxed text-zinc-400">
                  {benefit.description}
                </p>
              </motion.div>
            ))}
          </div>

          {/* CTAs */}
          <div className="mt-12 flex flex-col items-center gap-3 sm:flex-row sm:justify-center">
            <Button
              size="lg"
              onClick={() => {
                navigate('apply');
                window.scrollTo({ top: 0, behavior: 'smooth' });
              }}
              className="h-11 bg-emerald-600 px-8 text-sm font-medium text-white hover:bg-emerald-700"
            >
              Become a Partner
              <ArrowRight className="size-4" />
            </Button>
            <Button
              variant="outline"
              size="lg"
              onClick={() => {
                navigate('home');
                window.scrollTo({ top: 0, behavior: 'smooth' });
              }}
              className="h-11 border-zinc-700 px-8 text-sm font-medium text-zinc-300 hover:bg-zinc-800 hover:text-white"
            >
              Learn More
            </Button>
          </div>
        </Section>
      </section>

      {/* ─── Pricing ────────────────────────────────────── */}
      <Section className="py-20 sm:py-28">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <div className="mb-14 text-center">
            <p className="mb-3 font-mono text-xs tracking-widest text-zinc-500">
              PRICING
            </p>
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
              Simple, transparent pricing
            </h2>
            <p className="mx-auto mt-4 max-w-xl text-zinc-600 dark:text-zinc-400">
              Start free. Upgrade when you need more vendors, more evidence, more
              proof.
            </p>
          </div>

          <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {tiers.map((tier, i) => (
              <motion.div
                key={tier.name}
                variants={fadeUp}
                custom={i}
                whileHover={{ y: -4 }}
                transition={{ type: 'spring', stiffness: 400, damping: 30 }}
                className={`relative flex flex-col rounded-xl border p-6 ${
                  tier.popular
                    ? 'border-zinc-900 shadow-lg dark:border-zinc-100'
                    : 'border-zinc-200 dark:border-zinc-800'
                } bg-white dark:bg-zinc-900`}
              >
                {tier.popular && (
                  <div className="absolute -top-3 left-1/2 -translate-x-1/2">
                    <Badge className="bg-zinc-900 text-white dark:bg-white dark:text-zinc-900">
                      Most Popular
                    </Badge>
                  </div>
                )}
                <div className="mb-4">
                  <h3 className="text-sm font-semibold">{tier.name}</h3>
                  <div className="mt-2 flex items-baseline gap-1">
                    <span className="text-3xl font-bold tracking-tight">
                      {tier.price}
                    </span>
                    <span className="text-sm text-zinc-500">{tier.period}</span>
                  </div>
                  <p className="mt-2 text-xs text-zinc-500">{tier.description}</p>
                </div>
                <ul className="mb-6 flex-1 space-y-2.5">
                  {tier.features.map((f) => (
                    <li key={f} className="flex items-start gap-2 text-sm">
                      <Check className="mt-0.5 size-3.5 shrink-0 text-emerald-600" />
                      <span className="text-zinc-600 dark:text-zinc-400">{f}</span>
                    </li>
                  ))}
                </ul>
                <Button
                  variant={tier.popular ? 'default' : 'outline'}
                  className={`w-full ${
                    tier.popular
                      ? 'bg-zinc-900 text-white hover:bg-zinc-800 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200'
                      : ''
                  }`}
                  onClick={() => {
                    navigate('login');
                    window.scrollTo({ top: 0, behavior: 'smooth' });
                  }}
                >
                  Get Started
                  <ChevronRight className="size-3.5" />
                </Button>
              </motion.div>
            ))}
          </div>
        </div>
      </Section>

      {/* ─── FAQ ────────────────────────────────────────── */}
      <Section className="border-y border-zinc-100 bg-zinc-50/50 py-20 sm:py-28 dark:border-zinc-800 dark:bg-zinc-900/30">
        <div className="mx-auto max-w-2xl px-4 sm:px-6">
          <div className="mb-12 text-center">
            <p className="mb-3 font-mono text-xs tracking-widest text-zinc-500">
              FAQ
            </p>
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">
              Frequently asked questions
            </h2>
          </div>
          <Accordion type="single" collapsible className="w-full">
            {faqItems.map((item, i) => (
              <AccordionItem
                key={i}
                value={`faq-${i}`}
                className="border-zinc-200 dark:border-zinc-800"
              >
                <AccordionTrigger className="text-sm font-medium hover:no-underline sm:text-base">
                  {item.q}
                </AccordionTrigger>
                <AccordionContent className="text-sm leading-relaxed text-zinc-600 dark:text-zinc-400">
                  {item.a}
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        </div>
      </Section>

      {/* ─── Founder Section ────────────────────────────── */}
      <Section className="py-20 sm:py-28">
        <div className="mx-auto max-w-2xl px-4 text-center sm:px-6">
          <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-zinc-100 dark:bg-zinc-800">
            <span className="text-xl font-bold text-zinc-600 dark:text-zinc-300">
              EO
            </span>
          </div>
          <h2 className="text-2xl font-bold tracking-tight sm:text-3xl">
            Emmanuel Osei
          </h2>
          <p className="mt-1 font-mono text-xs tracking-wider text-zinc-500">
            FOUNDER & CEO
          </p>
          <blockquote className="mt-6 text-base leading-relaxed text-zinc-600 sm:text-lg dark:text-zinc-400">
            &ldquo;I built Reliastra because I lived through too many war rooms
            where the question was never &ldquo;what broke,&rdquo; but &ldquo;who
            broke it.&rdquo; Without vendor-level evidence, engineering teams eat
            the cost of someone else&rsquo;s failure. That stops now.&rdquo;
          </blockquote>
        </div>
      </Section>

      {/* ─── Final CTA ──────────────────────────────────── */}
      <section className="border-t border-zinc-100 bg-zinc-50/50 py-20 sm:py-28 dark:border-zinc-800 dark:bg-zinc-900/30">
        <div className="mx-auto max-w-2xl px-4 text-center sm:px-6">
          <Section>
            <h2 className="text-3xl font-bold tracking-tight sm:text-4xl md:text-5xl">
              Stop guessing.{' '}
              <span className="text-emerald-600">Start proving.</span>
            </h2>
            <p className="mx-auto mt-5 max-w-lg text-zinc-600 dark:text-zinc-400">
              Join the teams that already know exactly what failed, when it
              failed, and how to prove it.
            </p>
            <div className="mt-8">
              <Button
                size="lg"
                onClick={() => {
                  navigate('login');
                  window.scrollTo({ top: 0, behavior: 'smooth' });
                }}
                className="h-11 bg-zinc-900 px-8 text-sm font-medium text-white hover:bg-zinc-800 dark:bg-white dark:text-zinc-900 dark:hover:bg-zinc-200"
              >
                Start Free
                <ArrowRight className="size-4" />
              </Button>
            </div>
          </Section>
        </div>
      </section>

      {/* ─── Footer ─────────────────────────────────────── */}
      <footer className="border-t border-zinc-200 bg-white py-14 dark:border-zinc-800 dark:bg-zinc-950">
        <div className="mx-auto max-w-6xl px-4 sm:px-6">
          <div className="grid gap-10 sm:grid-cols-2 lg:grid-cols-4">
            {/* Brand column */}
            <div className="sm:col-span-2 lg:col-span-1">
              <span className="font-mono text-sm font-bold tracking-widest text-zinc-900 dark:text-white">
                reliastra
              </span>
              <p className="mt-3 text-sm leading-relaxed text-zinc-500">
                External dependency intelligence. Monitor, correlate, and prove
                vendor failures.
              </p>
            </div>

            {/* Product */}
            <div>
              <h4 className="mb-3 font-mono text-xs font-medium tracking-wider text-zinc-500">
                PRODUCT
              </h4>
              <ul className="space-y-2">
                {['Features', 'Pricing', 'Vendor Intelligence', 'Partners', 'Status'].map(
                  (label) => (
                    <li key={label}>
                      <button
                        onClick={() => {
                          navigate('home');
                          window.scrollTo({ top: 0, behavior: 'smooth' });
                        }}
                        className="text-sm text-zinc-600 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
                      >
                        {label}
                      </button>
                    </li>
                  )
                )}
              </ul>
            </div>

            {/* Company */}
            <div>
              <h4 className="mb-3 font-mono text-xs font-medium tracking-wider text-zinc-500">
                COMPANY
              </h4>
              <ul className="space-y-2">
                {['About', 'Blog', 'Community', 'Investors', 'Contact'].map(
                  (label) => (
                    <li key={label}>
                      <button
                        onClick={() => {
                          navigate('home');
                          window.scrollTo({ top: 0, behavior: 'smooth' });
                        }}
                        className="text-sm text-zinc-600 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
                      >
                        {label}
                      </button>
                    </li>
                  )
                )}
              </ul>
            </div>

            {/* Legal */}
            <div>
              <h4 className="mb-3 font-mono text-xs font-medium tracking-wider text-zinc-500">
                LEGAL
              </h4>
              <ul className="space-y-2">
                {['Privacy Policy', 'Terms of Service', 'Guarantee'].map(
                  (label) => (
                    <li key={label}>
                      <button
                        onClick={() => {
                          navigate(
                            label === 'Privacy Policy'
                              ? 'privacy'
                              : label === 'Terms of Service'
                                ? 'terms'
                                : 'home'
                          );
                          window.scrollTo({ top: 0, behavior: 'smooth' });
                        }}
                        className="text-sm text-zinc-600 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-white"
                      >
                        {label}
                      </button>
                    </li>
                  )
                )}
              </ul>
            </div>
          </div>

          <div className="mt-12 flex flex-col items-center justify-between gap-3 border-t border-zinc-100 pt-6 sm:flex-row dark:border-zinc-800">
            <p className="text-xs text-zinc-500">
              &copy; 2026 Reliastra, Inc. All rights reserved.
            </p>
            <div className="flex items-center gap-1">
              <Star className="size-3 text-zinc-400" />
              <span className="font-mono text-[10px] text-zinc-400">v1.0</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}
