'use client';

import { cn } from '@/lib/utils';

interface ReliastraLogoProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

const sizeMap = {
  sm: { icon: 16, text: 'text-[10px]' },
  md: { icon: 20, text: 'text-xs' },
  lg: { icon: 24, text: 'text-sm' },
} as const;

export function ReliastraLogo({ size = 'md', className }: ReliastraLogoProps) {
  const s = sizeMap[size];

  return (
    <span className={cn('inline-flex items-center gap-2', className)}>
      <svg
        width={s.icon}
        height={s.icon}
        viewBox="0 0 24 24"
        fill="none"
        className="shrink-0"
      >
        <rect
          x="2"
          y="2"
          width="20"
          height="20"
          rx="4"
          stroke="currentColor"
          strokeWidth="1.5"
        />
        <path
          d="M8 12L11 15L16 9"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span
        className={cn(
          'font-mono font-semibold tracking-widest uppercase text-foreground',
          s.text
        )}
      >
        RELIASTRA
      </span>
    </span>
  );
}
