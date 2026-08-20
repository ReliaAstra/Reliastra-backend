'use client';

import { motion } from 'framer-motion';
import { ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { ReferralLinkCard } from './referral-link-card';

interface EmptyStateProps {
  referralLink: string;
  onGoToDashboard?: () => void;
}

function NetworkGraph() {
  return (
    <div className="mb-8 flex justify-center">
      <svg width="160" height="100" viewBox="0 0 160 100" fill="none" className="text-foreground/20">
        {/* Lines connecting nodes */}
        <line x1="80" y1="22" x2="30" y2="78" stroke="currentColor" strokeWidth="1" />
        <line x1="80" y1="22" x2="130" y2="78" stroke="currentColor" strokeWidth="1" />
        <line x1="30" y1="78" x2="130" y2="78" stroke="currentColor" strokeWidth="1" />

        {/* Node 1 — top center, pulsing */}
        <motion.circle
          cx="80"
          cy="22"
          r="6"
          fill="currentColor"
          initial={{ opacity: 0.2, scale: 1 }}
          animate={{ opacity: [0.2, 0.5, 0.2], scale: [1, 1.15, 1] }}
          transition={{ duration: 2.5, repeat: Infinity, ease: 'easeInOut' }}
        />
        <circle cx="80" cy="22" r="12" stroke="currentColor" strokeWidth="0.5" fill="none">
          <animate
            attributeName="r"
            values="12;16;12"
            dur="2.5s"
            repeatCount="indefinite"
          />
          <animate
            attributeName="opacity"
            values="0.3;0;0.3"
            dur="2.5s"
            repeatCount="indefinite"
          />
        </circle>

        {/* Node 2 — bottom left */}
        <circle cx="30" cy="78" r="5" fill="currentColor" opacity="0.25" />

        {/* Node 3 — bottom right */}
        <circle cx="130" cy="78" r="5" fill="currentColor" opacity="0.25" />
      </svg>
    </div>
  );
}

export function EmptyState({ referralLink, onGoToDashboard }: EmptyStateProps) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex flex-col items-center justify-center py-16 md:py-24 px-4"
    >
      <div className="max-w-lg w-full text-center">
        {/* Animated network graph */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }}
        >
          <NetworkGraph />
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
        >
          <h3 className="text-2xl font-semibold tracking-tight mb-3 md:text-3xl">
            Your first referral is waiting.
          </h3>
          <p className="text-muted-foreground mb-10">
            Start by sharing your link with someone who needs RELIASTRA.
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="mb-10"
        >
          <ReferralLinkCard link={referralLink} size="hero" showLabel={false} />
          <p className="mt-3 text-xs text-muted-foreground">
            We&apos;ll notify you when someone signs up.
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          className="space-y-5 text-left max-w-sm mx-auto"
        >
          <div className="flex gap-3.5 items-start">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-border/80 bg-muted/50 text-[11px] font-mono font-medium text-muted-foreground">
              1
            </span>
            <p className="text-sm text-foreground/80 pt-0.5">Copy your link</p>
          </div>
          <div className="flex gap-3.5 items-start">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-border/80 bg-muted/50 text-[11px] font-mono font-medium text-muted-foreground">
              2
            </span>
            <p className="text-sm text-foreground/80 pt-0.5">Share it with someone who needs RELIASTRA</p>
          </div>
          <div className="flex gap-3.5 items-start">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-border/80 bg-muted/50 text-[11px] font-mono font-medium text-muted-foreground">
              3
            </span>
            <p className="text-sm text-foreground/80 pt-0.5">We&apos;ll track the subscription</p>
          </div>
          <div className="flex gap-3.5 items-start">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-border/80 bg-muted/50 text-[11px] font-mono font-medium text-muted-foreground">
              4
            </span>
            <p className="text-sm text-foreground/80 pt-0.5">You&apos;ll earn 30% every month</p>
          </div>
        </motion.div>

        {onGoToDashboard && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.4 }}
            className="mt-10"
          >
            <Button variant="ghost" onClick={onGoToDashboard} className="gap-2">
              GO TO DASHBOARD
              <ArrowRight className="size-4" />
            </Button>
          </motion.div>
        )}
      </div>
    </motion.div>
  );
}
