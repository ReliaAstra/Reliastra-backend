'use client';

import { useRef, useEffect, useState } from 'react';
import { motion, useMotionValue, useSpring, useInView } from 'framer-motion';
import { cn } from '@/lib/utils';

interface MetricCardProps {
  label: string;
  value: string;
  sublabel?: string;
  className?: string;
  delay?: number;
  /** When true, animate the numeric value counting up from 0 */
  animated?: boolean;
}

/**
 * Parse a formatted currency/value string and return the numeric value.
 * Handles formats like "$441.00", "$1,234.56", "12".
 */
function parseNumericValue(formatted: string): number {
  const cleaned = formatted.replace(/[^0-9.]/g, '');
  const parsed = parseFloat(cleaned);
  return isNaN(parsed) ? 0 : parsed;
}

/**
 * Detect the prefix (everything before the first digit) and suffix
 * (everything after the last digit/decimal).
 */
function parseParts(formatted: string): { prefix: string; suffix: string } {
  const match = formatted.match(/^([^0-9]*)([0-9,.-]+)([^0-9]*)$/);
  if (match) {
    return { prefix: match[1], suffix: match[3] };
  }
  return { prefix: '', suffix: '' };
}

/**
 * Animated counter component that counts up from 0 to the target value.
 * Uses framer-motion's useMotionValue + useSpring for smooth animation.
 */
function AnimatedCounter({
  formattedValue,
}: {
  formattedValue: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const isInView = useInView(ref, { once: true, margin: '-20px' });
  const [displayValue, setDisplayValue] = useState('0');

  const numericValue = parseNumericValue(formattedValue);
  const { prefix, suffix } = parseParts(formattedValue);

  // Determine number of decimal places from the formatted value
  const decimalMatch = formattedValue.match(/\.([0-9]+)/);
  const decimals = decimalMatch ? decimalMatch[1].length : 0;

  const motionVal = useMotionValue(0);
  const springVal = useSpring(motionVal, {
    duration: 1500,
    bounce: 0,
  });

  useEffect(() => {
    if (isInView) {
      motionVal.set(numericValue);
    }
  }, [isInView, motionVal, numericValue]);

  useEffect(() => {
    const unsubscribe = springVal.on('change', (latest) => {
      setDisplayValue(
        latest.toLocaleString('en-US', {
          minimumFractionDigits: decimals,
          maximumFractionDigits: decimals,
        })
      );
    });
    return unsubscribe;
  }, [springVal, decimals]);

  return (
    <span ref={ref}>
      {prefix}
      {displayValue}
      {suffix}
    </span>
  );
}

export function MetricCard({
  label,
  value,
  sublabel,
  className,
  delay = 0,
  animated = false,
}: MetricCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ scale: 1.01 }}
      transition={{ duration: 0.4, delay, ease: [0.25, 0.1, 0.25, 1] }}
      className={cn(
        'border border-border/60 rounded-lg p-5 md:p-6 bg-background transition-colors duration-200 hover:border-border hover:bg-muted/20',
        className
      )}
    >
      <p className="text-xs font-mono uppercase tracking-widest text-muted-foreground mb-2">
        {label}
      </p>
      <p className="text-2xl md:text-3xl font-semibold tracking-tight tabular-nums">
        {animated ? <AnimatedCounter formattedValue={value} /> : value}
      </p>
      {sublabel && (
        <p className="text-sm text-muted-foreground mt-1">{sublabel}</p>
      )}
    </motion.div>
  );
}
