'use client';

import { useMemo } from 'react';
import { motion } from 'framer-motion';
import { Check, ArrowUpRight, Minus } from 'lucide-react';
import { cn } from '@/lib/utils';
import { getPartnerTier, getNextTier } from '@/types/partner';
import { TierBadge } from './tier-badge';
import type { TierInfo } from '@/types/partner';

interface TierProgressCardProps {
  activeReferrals: number;
  className?: string;
  delay?: number;
}

function ProgressBar({
  current,
  next,
  referrals,
}: {
  current: TierInfo;
  next: TierInfo | null;
  referrals: number;
}) {
  if (!next) return null;

  const range = next.minReferrals - current.minReferrals;
  const progress = Math.min((referrals - current.minReferrals) / range, 1);
  const remaining = next.minReferrals - referrals;

  return (
    <div className="mt-4">
      <div className="flex items-baseline justify-between mb-1.5">
        <span className="text-xs text-muted-foreground">
          <span className="font-mono tabular-nums font-medium text-foreground">
            {referrals}
          </span>
          {' / '}
          <span className="font-mono tabular-nums">{next.minReferrals}</span>
          {' referrals'}
        </span>
        <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
          {remaining > 0 ? `${remaining} to go` : 'Almost there'}
        </span>
      </div>

      <div className="h-1.5 rounded-full bg-muted/60 overflow-hidden">
        <motion.div
          className="h-full rounded-full bg-foreground/80"
          initial={{ width: 0 }}
          animate={{ width: `${Math.max(progress * 100, 2)}%` }}
          transition={{ duration: 0.8, delay: 0.3, ease: [0.25, 0.1, 0.25, 1] }}
        />
      </div>

      <div className="flex justify-between mt-1.5">
        <span className="text-[10px] font-mono text-muted-foreground/60">
          {current.name}
        </span>
        <span className="text-[10px] font-mono text-muted-foreground/60">
          {next.name}
        </span>
      </div>
    </div>
  );
}

function MaxTierReached() {
  return (
    <div className="mt-4 flex items-center gap-2 rounded-md border border-border/40 bg-muted/20 px-3 py-2">
      <Minus className="size-3 text-muted-foreground" />
      <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground">
        Max tier reached
      </span>
    </div>
  );
}

function BenefitsList({
  benefits,
  variant = 'current',
}: {
  benefits: string[];
  variant?: 'current' | 'next';
}) {
  return (
    <ul className={cn('space-y-1.5', variant === 'next' && 'pt-1')}>
      {benefits.map((benefit) => (
        <li key={benefit} className="flex items-start gap-2">
          {variant === 'current' ? (
            <Check className="size-3 mt-0.5 shrink-0 text-foreground/60" />
          ) : (
            <ArrowUpRight className="size-3 mt-0.5 shrink-0 text-muted-foreground" />
          )}
          <span
            className={cn(
              'text-xs leading-relaxed',
              variant === 'current'
                ? 'text-foreground/80'
                : 'text-muted-foreground'
            )}
          >
            {benefit}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function TierProgressCard({
  activeReferrals,
  className,
  delay = 0,
}: TierProgressCardProps) {
  const currentTier = useMemo(
    () => getPartnerTier(activeReferrals),
    [activeReferrals]
  );
  const nextTier = useMemo(
    () => getNextTier(activeReferrals),
    [activeReferrals]
  );

  // Benefits the next tier unlocks that the current tier doesn't have
  const newBenefits = useMemo(() => {
    if (!nextTier) return [];
    return nextTier.benefits.filter(
      (b) => !currentTier.benefits.includes(b)
    );
  }, [currentTier, nextTier]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay, ease: [0.25, 0.1, 0.25, 1] }}
      className={cn(
        'border border-border/60 rounded-lg p-5 md:p-6 bg-background',
        className
      )}
    >
      {/* Header: tier badge + commission rate */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <TierBadge tier={currentTier} size="lg" />
          <div>
            <p className="font-mono text-2xl font-bold tabular-nums tracking-tight">
              {currentTier.commissionRate}%
            </p>
            <p className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
              Commission
            </p>
          </div>
        </div>
        <div className="text-right">
          <p className="font-mono text-sm tabular-nums text-foreground">
            {activeReferrals}
          </p>
          <p className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
            Active referrals
          </p>
        </div>
      </div>

      {/* Progress bar or max tier */}
      {nextTier ? (
        <ProgressBar
          current={currentTier}
          next={nextTier}
          referrals={activeReferrals}
        />
      ) : (
        <MaxTierReached />
      )}

      {/* Benefits section */}
      <div className="mt-5 pt-4 border-t border-border/40">
        <p className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mb-2.5">
          Current benefits
        </p>
        <BenefitsList benefits={currentTier.benefits} variant="current" />
      </div>

      {/* Next tier unlocks */}
      {nextTier && newBenefits.length > 0 && (
        <div className="mt-4 pt-4 border-t border-border/40">
          <div className="flex items-center gap-2 mb-2.5">
            <p className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">
              Unlocks at {nextTier.name}
            </p>
            <TierBadge tier={nextTier} size="sm" />
          </div>
          <BenefitsList benefits={newBenefits} variant="next" />
        </div>
      )}
    </motion.div>
  );
}
