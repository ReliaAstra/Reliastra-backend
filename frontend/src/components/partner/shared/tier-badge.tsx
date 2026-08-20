'use client';

import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';
import type { TierInfo } from '@/types/partner';

interface TierBadgeProps {
  tier: TierInfo;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

const sizeConfig = {
  sm: {
    container: 'gap-1.5 px-2 py-0.5',
    icon: 'size-3',
    text: 'text-[9px]',
  },
  md: {
    container: 'gap-2 px-3 py-1',
    icon: 'size-3.5',
    text: 'text-[10px]',
  },
  lg: {
    container: 'gap-2.5 px-4 py-1.5',
    icon: 'size-4',
    text: 'text-xs',
  },
};

const tierStyles: Record<string, { border: string; icon: string; text: string; glow?: string }> = {
  bronze: {
    border: 'border-amber-600/40 dark:border-amber-400/30',
    icon: 'text-amber-700 dark:text-amber-400',
    text: 'text-amber-800 dark:text-amber-300',
  },
  silver: {
    border: 'border-slate-500/40 dark:border-slate-300/30',
    icon: 'text-slate-600 dark:text-slate-300',
    text: 'text-slate-700 dark:text-slate-200',
  },
  gold: {
    border: 'border-yellow-500/40 dark:border-yellow-400/30',
    icon: 'text-yellow-600 dark:text-yellow-400',
    text: 'text-yellow-700 dark:text-yellow-300',
    glow: 'shadow-[0_0_8px_rgba(202,138,4,0.1)] dark:shadow-[0_0_8px_rgba(250,204,21,0.1)]',
  },
  platinum: {
    border: 'border-zinc-500/40 dark:border-zinc-300/30',
    icon: 'text-zinc-800 dark:text-zinc-100',
    text: 'text-zinc-800 dark:text-zinc-100',
    glow: 'shadow-[0_0_8px_rgba(63,63,70,0.08)] dark:shadow-[0_0_8px_rgba(161,161,170,0.08)]',
  },
};

function TierIcon({ tier, className }: { tier: TierInfo; className?: string }) {
  const style = tierStyles[tier.tier];

  if (tier.tier === 'bronze') {
    return (
      <svg
        viewBox="0 0 16 16"
        fill="none"
        className={cn('shrink-0', className, style.icon)}
      >
        <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.2" />
        <circle cx="8" cy="8" r="2" fill="currentColor" opacity="0.5" />
      </svg>
    );
  }

  if (tier.tier === 'silver') {
    return (
      <svg
        viewBox="0 0 16 16"
        fill="none"
        className={cn('shrink-0', className, style.icon)}
      >
        <path
          d="M8 1.5L14.5 5.5L12.5 13H3.5L1.5 5.5L8 1.5Z"
          stroke="currentColor"
          strokeWidth="1.2"
          strokeLinejoin="round"
        />
        <path
          d="M8 1.5L14.5 5.5L12.5 13H3.5L1.5 5.5L8 1.5Z"
          fill="currentColor"
          opacity="0.15"
        />
      </svg>
    );
  }

  if (tier.tier === 'gold') {
    return (
      <svg
        viewBox="0 0 16 16"
        fill="none"
        className={cn('shrink-0', className, style.icon)}
      >
        <path
          d="M2 10.5L4 5L6 8L8 3L10 8L12 5L14 10.5H2Z"
          stroke="currentColor"
          strokeWidth="1.2"
          strokeLinejoin="round"
        />
        <path
          d="M2 10.5L4 5L6 8L8 3L10 8L12 5L14 10.5H2Z"
          fill="currentColor"
          opacity="0.2"
        />
      </svg>
    );
  }

  // platinum - diamond
  return (
    <svg
      viewBox="0 0 16 16"
      fill="none"
      className={cn('shrink-0', className, style.icon)}
    >
      <path
        d="M8 1L14 6.5L8 15L2 6.5L8 1Z"
        stroke="currentColor"
        strokeWidth="1.2"
        strokeLinejoin="round"
      />
      <path
        d="M8 1L14 6.5L8 15L2 6.5L8 1Z"
        fill="currentColor"
        opacity="0.1"
      />
      <path d="M2 6.5H14" stroke="currentColor" strokeWidth="0.8" opacity="0.3" />
    </svg>
  );
}

export function TierBadge({ tier, size = 'md', className }: TierBadgeProps) {
  const config = sizeConfig[size];
  const style = tierStyles[tier.tier];
  const isAnimated = tier.tier === 'gold' || tier.tier === 'platinum';

  return (
    <motion.span
      className={cn(
        'inline-flex items-center rounded-md border font-mono uppercase tracking-widest font-medium',
        config.container,
        style.border,
        style.text,
        style.glow,
        className
      )}
      {...(isAnimated
        ? {
            animate: {
              borderColor: [
                `${tier.tier === 'gold' ? 'rgba(202,138,4,0.3)' : 'rgba(63,63,70,0.3)'}`,
                `${tier.tier === 'gold' ? 'rgba(202,138,4,0.55)' : 'rgba(63,63,70,0.5)'}`,
                `${tier.tier === 'gold' ? 'rgba(202,138,4,0.3)' : 'rgba(63,63,70,0.3)'}`,
              ],
            },
            transition: {
              duration: 3,
              repeat: Infinity,
              ease: 'easeInOut',
            },
          }
        : {})}
    >
      <TierIcon tier={tier} className={config.icon} />
      <span className={cn('leading-none', config.text)}>{tier.name}</span>
    </motion.span>
  );
}
