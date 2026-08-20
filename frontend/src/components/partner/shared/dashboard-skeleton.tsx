'use client';

import { cn } from '@/lib/utils';
import { motion } from 'framer-motion';

// --- Shimmer keyframes injected via style tag ---
const shimmerStyle = `
@keyframes skeleton-shimmer {
  0% { background-position: -200% 0; }
  100% { background-position: 200% 0; }
}
.skeleton-shimmer {
  animation: skeleton-shimmer 1.8s ease-in-out infinite;
  background-size: 200% 100%;
}
`;

// --- SkeletonLine ---
// A single line of arbitrary width/height with shimmer effect
export function SkeletonLine({
  className,
  width,
  height = 'h-4',
}: {
  className?: string;
  width?: string;
  height?: string;
}) {
  return (
    <div
      className={cn(
        'rounded-md bg-muted/40 relative overflow-hidden skeleton-shimmer',
        'bg-[length:200%_100%] bg-[linear-gradient(90deg,theme(colors.muted/40)_25%,theme(colors.background/60)_50%,theme(colors.muted/40)_75%)]',
        height,
        width,
        className
      )}
    />
  );
}

// --- SkeletonPulse ---
// A pulsing div with animate-pulse
export function SkeletonPulse({
  className,
}: {
  className?: string;
}) {
  return (
    <div
      className={cn('animate-pulse bg-muted/40 rounded-md', className)}
    />
  );
}

// --- SkeletonShimmer ---
// A div with shimmer gradient animation
export function SkeletonShimmer({
  className,
}: {
  className?: string;
}) {
  return (
    <div
      className={cn(
        'rounded-md bg-muted/40 relative overflow-hidden skeleton-shimmer',
        'bg-[length:200%_100%] bg-[linear-gradient(90deg,theme(colors.muted/40)_25%,theme(colors.background/60)_50%,theme(colors.muted/40)_75%)]',
        className
      )}
    />
  );
}

// --- SkeletonCard ---
// A card-shaped skeleton block
function SkeletonCard({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        'border border-border/60 rounded-lg bg-background p-4 md:p-6',
        className
      )}
    />
  );
}

// --- SkeletonTableRow ---
// A single table row skeleton
function SkeletonTableRow({
  showDate = false,
  className,
}: {
  showDate?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        'px-5 py-3.5 border-b border-border/30 last:border-b-0',
        className
      )}
    >
      <div className="flex items-center justify-between">
        <SkeletonShimmer className="h-4 w-36 md:w-44" />
        <div className="flex items-center gap-3">
          <SkeletonShimmer className="h-5 w-14 rounded" />
          <SkeletonShimmer className="h-4 w-16" />
        </div>
      </div>
      {showDate && (
        <div className="flex items-center justify-between mt-2">
          <SkeletonShimmer className="h-3 w-20" />
          <SkeletonShimmer className="h-3 w-16" />
        </div>
      )}
    </div>
  );
}

// ============================================================
// Dashboard page skeletons
// ============================================================

// --- DashboardOverviewSkeleton ---
// Mimics overview page: tier progress card, 4 metric cards, referral link,
// how-it-works bar, activity feed, referrals table
export function DashboardOverviewSkeleton({ className }: { className?: string }) {
  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: shimmerStyle }} />
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4 }}
        className={cn('space-y-8 max-w-4xl', className)}
      >
        {/* Page heading */}
        <div className="space-y-2">
          <SkeletonShimmer className="h-8 w-64" />
          <SkeletonShimmer className="h-4 w-80" />
        </div>

        {/* Tier progress card (2 rows) */}
        <div className="border border-border/60 rounded-lg bg-background p-5 md:p-6">
          <div className="flex items-center justify-between mb-4">
            <SkeletonShimmer className="h-4 w-32" />
            <SkeletonShimmer className="h-5 w-20 rounded-full" />
          </div>
          <SkeletonShimmer className="h-2 w-full rounded-full" />
          <div className="flex items-center justify-between mt-3">
            <SkeletonShimmer className="h-3 w-24" />
            <SkeletonShimmer className="h-3 w-16" />
          </div>
        </div>

        {/* 4 metric cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div
              key={i}
              className="border border-border/60 rounded-lg bg-background p-4 md:p-5 space-y-3"
            >
              <SkeletonShimmer className="h-3 w-20" />
              <SkeletonShimmer className="h-6 w-24" />
              <SkeletonShimmer className="h-3 w-14" />
            </div>
          ))}
        </div>

        {/* Referral link card */}
        <div className="border border-border/60 rounded-lg bg-background p-4 md:p-5">
          <SkeletonShimmer className="h-3 w-28 mb-3" />
          <SkeletonShimmer className="h-10 w-full rounded-md" />
        </div>

        {/* How it works bar */}
        <div className="border border-border/40 rounded-lg bg-muted/20 py-4 px-5">
          <div className="flex items-center justify-around">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="flex flex-col items-center gap-1">
                <SkeletonShimmer className="h-3 w-16" />
                <SkeletonShimmer className="h-2.5 w-20" />
              </div>
            ))}
          </div>
        </div>

        {/* Activity feed */}
        <div className="border border-border/60 rounded-lg bg-background overflow-hidden">
          <div className="px-5 py-3.5 border-b border-border/60">
            <SkeletonShimmer className="h-3 w-32" />
          </div>
          {[...Array(4)].map((_, i) => (
            <div
              key={i}
              className="px-5 py-3.5 border-b border-border/30 last:border-b-0"
            >
              <div className="flex items-center gap-3">
                <SkeletonPulse className="size-7 rounded-full" />
                <div className="flex-1 space-y-1.5">
                  <SkeletonShimmer className="h-4 w-48" />
                  <SkeletonShimmer className="h-3 w-20" />
                </div>
                <SkeletonShimmer className="h-4 w-14" />
              </div>
            </div>
          ))}
        </div>

        {/* Recent referrals table */}
        <div className="border border-border/60 rounded-lg bg-background overflow-hidden">
          <div className="px-5 py-3.5 border-b border-border/60">
            <SkeletonShimmer className="h-3 w-32" />
          </div>
          {[...Array(3)].map((_, i) => (
            <SkeletonTableRow key={i} showDate={i === 0} />
          ))}
        </div>
      </motion.div>
    </>
  );
}

// --- DashboardReferralsSkeleton ---
// Conversion stats bar + table skeleton with 5 rows
export function DashboardReferralsSkeleton({ className }: { className?: string }) {
  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: shimmerStyle }} />
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4 }}
        className={cn('space-y-6 max-w-4xl', className)}
      >
        {/* Heading */}
        <div className="flex items-center gap-3">
          <SkeletonShimmer className="h-8 w-32" />
          <SkeletonShimmer className="h-5 w-10 rounded" />
        </div>

        {/* Conversion stats bar */}
        <div className="border border-border/60 rounded-lg bg-background px-5 py-4 flex items-center justify-around divide-x divide-border/40">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="flex flex-col items-center text-center flex-1">
              <SkeletonShimmer className="h-6 w-10 mb-1" />
              <SkeletonShimmer className="h-2.5 w-16" />
            </div>
          ))}
        </div>

        {/* Table */}
        <div className="border border-border/60 rounded-lg bg-background overflow-hidden">
          <div className="hidden md:block">
            {/* Table header skeleton */}
            <div className="border-b border-border/60 px-5 py-3">
              <div className="flex items-center justify-between">
                {[...Array(5)].map((_, i) => (
                  <SkeletonShimmer key={i} className="h-3 w-16" />
                ))}
              </div>
            </div>
            {/* Table rows */}
            {[...Array(5)].map((_, i) => (
              <SkeletonTableRow key={i} showDate />
            ))}
          </div>
          {/* Mobile cards skeleton */}
          <div className="md:hidden divide-y divide-border/40">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="px-5 py-4 space-y-2">
                <div className="flex items-center justify-between">
                  <SkeletonShimmer className="h-4 w-32" />
                  <SkeletonShimmer className="h-5 w-14 rounded" />
                </div>
                <div className="flex items-center justify-between">
                  <SkeletonShimmer className="h-3 w-16" />
                  <SkeletonShimmer className="h-4 w-16" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </motion.div>
    </>
  );
}

// --- DashboardEarningsSkeleton ---
// Hero metric card + 4 summary cards + chart skeleton area + history table
export function DashboardEarningsSkeleton({ className }: { className?: string }) {
  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: shimmerStyle }} />
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4 }}
        className={cn('space-y-8 max-w-4xl', className)}
      >
        {/* Heading */}
        <SkeletonShimmer className="h-8 w-32" />

        {/* Hero metric card */}
        <div className="border border-border/60 rounded-lg bg-background p-6 md:p-8">
          <SkeletonShimmer className="h-3 w-28 mb-2" />
          <SkeletonShimmer className="h-12 w-48" />
        </div>

        {/* 4 summary metric cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div
              key={i}
              className="border border-border/60 rounded-lg bg-background p-4 md:p-5 space-y-3"
            >
              <SkeletonShimmer className="h-3 w-20" />
              <SkeletonShimmer className="h-6 w-24" />
            </div>
          ))}
        </div>

        {/* Chart skeleton area */}
        <div className="border border-border/60 rounded-lg bg-background p-5 md:p-6">
          <SkeletonShimmer className="h-3 w-40 mb-5" />
          {/* Bar chart placeholder */}
          <div className="flex items-end justify-around gap-2" style={{ height: 160 }}>
            {[...Array(8)].map((_, i) => (
              <div key={i} className="flex flex-col items-center flex-1 gap-1.5">
                <SkeletonShimmer className="h-3 w-10" />
                <SkeletonShimmer
                  className="w-full max-w-[32px] rounded-t-sm"
                  style={{ height: `${30 + Math.random() * 70}%` } as React.CSSProperties}
                />
              </div>
            ))}
          </div>
          <div className="flex justify-around mt-2 border-t border-border/40 pt-2">
            {[...Array(8)].map((_, i) => (
              <SkeletonShimmer key={i} className="h-3 w-8" />
            ))}
          </div>
        </div>

        {/* Earnings history table */}
        <div className="border border-border/60 rounded-lg bg-background overflow-hidden">
          <div className="px-5 py-3.5 border-b border-border/60">
            <SkeletonShimmer className="h-3 w-36" />
          </div>
          {[...Array(5)].map((_, i) => (
            <div
              key={i}
              className="px-5 py-3.5 border-b border-border/30 last:border-b-0"
            >
              <div className="flex items-center justify-between">
                <div className="space-y-1.5">
                  <SkeletonShimmer className="h-4 w-44" />
                  <SkeletonShimmer className="h-3 w-24" />
                </div>
                <div className="text-right space-y-1.5">
                  <SkeletonShimmer className="h-4 w-20 ml-auto" />
                  <SkeletonShimmer className="h-5 w-16 rounded ml-auto" />
                </div>
              </div>
            </div>
          ))}
        </div>
      </motion.div>
    </>
  );
}

// --- DashboardPayoutsSkeleton ---
// 2 metric area cards + table skeleton with 4 rows
export function DashboardPayoutsSkeleton({ className }: { className?: string }) {
  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: shimmerStyle }} />
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4 }}
        className={cn('space-y-8 max-w-4xl', className)}
      >
        {/* Heading */}
        <SkeletonShimmer className="h-8 w-32" />

        {/* Available to withdraw card */}
        <div className="border border-border/60 rounded-lg bg-background p-6 md:p-8">
          <SkeletonShimmer className="h-3 w-44 mb-2" />
          <SkeletonShimmer className="h-12 w-48 mb-6" />
          <SkeletonShimmer className="h-10 w-[200px] rounded-md" />
        </div>

        {/* Crypto recommendation banner */}
        <div className="border border-border/60 rounded-lg bg-background p-5 md:p-6">
          <div className="flex items-start gap-3">
            <SkeletonPulse className="size-8 rounded-full shrink-0" />
            <div className="flex-1 space-y-2">
              <SkeletonShimmer className="h-4 w-48" />
              <SkeletonShimmer className="h-3 w-full max-w-sm" />
              <SkeletonShimmer className="h-3 w-64" />
            </div>
          </div>
        </div>

        {/* Payout history table with 4 rows */}
        <div className="border border-border/60 rounded-lg bg-background overflow-hidden">
          <div className="px-5 py-3.5 border-b border-border/60">
            <SkeletonShimmer className="h-3 w-36" />
          </div>
          {[...Array(4)].map((_, i) => (
            <SkeletonTableRow key={i} showDate />
          ))}
        </div>
      </motion.div>
    </>
  );
}

// --- DashboardSettingsSkeleton ---
// Tabs bar + form fields skeleton
export function DashboardSettingsSkeleton({ className }: { className?: string }) {
  return (
    <>
      <style dangerouslySetInnerHTML={{ __html: shimmerStyle }} />
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.4 }}
        className={cn('space-y-6 max-w-4xl', className)}
      >
        {/* Heading */}
        <SkeletonShimmer className="h-8 w-28" />

        {/* Tabs bar */}
        <div className="flex items-center gap-1 border-b border-border/60 pb-0">
          {[...Array(4)].map((_, i) => (
            <div
              key={i}
              className={cn(
                'px-4 py-2.5',
                i === 0 && 'border-b-2 border-foreground/80'
              )}
            >
              <SkeletonShimmer
                className={cn(
                  'h-3.5 rounded',
                  i === 0 ? 'w-16' : i === 1 ? 'w-20' : i === 2 ? 'w-20' : 'w-24'
                )}
              />
            </div>
          ))}
        </div>

        {/* Form fields area */}
        <div className="space-y-6 pt-2">
          {/* Avatar + name row */}
          <div className="flex items-center gap-4">
            <SkeletonPulse className="size-12 rounded-full" />
            <div className="space-y-2">
              <SkeletonShimmer className="h-4 w-32" />
              <SkeletonShimmer className="h-3 w-44" />
            </div>
          </div>

          {/* Divider */}
          <div className="h-px bg-border/60" />

          {/* Two-column form fields */}
          <div className="grid gap-4 sm:grid-cols-2">
            {[...Array(2)].map((_, i) => (
              <div key={i} className="space-y-2">
                <SkeletonShimmer className="h-3 w-14" />
                <SkeletonShimmer className="h-10 w-full rounded-md" />
              </div>
            ))}
          </div>

          {/* Single field */}
          <div className="space-y-2">
            <SkeletonShimmer className="h-3 w-20" />
            <SkeletonShimmer className="h-5 w-14 rounded" />
          </div>

          {/* Divider */}
          <div className="h-px bg-border/60" />

          {/* Support card */}
          <div className="border border-border/60 rounded-lg p-4 md:p-5">
            <div className="flex items-start justify-between gap-4">
              <div className="space-y-1.5">
                <SkeletonShimmer className="h-4 w-24" />
                <SkeletonShimmer className="h-3 w-64" />
              </div>
              <SkeletonShimmer className="h-10 w-36 rounded-md shrink-0" />
            </div>
          </div>

          {/* Additional form fields below divider */}
          <div className="h-px bg-border/60" />
          <div className="space-y-4">
            <SkeletonShimmer className="h-3 w-20" />
            <div className="space-y-3 max-w-lg">
              {[...Array(3)].map((_, i) => (
                <div
                  key={i}
                  className={cn(
                    'border rounded-lg p-4 md:p-5',
                    i === 0 ? 'border-foreground/80 bg-muted/30' : 'border-border/60'
                  )}
                >
                  <div className="flex items-center gap-3">
                    <SkeletonPulse className="size-10 rounded-full" />
                    <div className="flex-1 space-y-1.5">
                      <SkeletonShimmer className="h-4 w-36" />
                      <SkeletonShimmer className="h-3 w-44" />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </motion.div>
    </>
  );
}
