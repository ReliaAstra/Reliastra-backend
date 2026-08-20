'use client';

import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { usePartnerStore } from '@/stores/partner-store';
import { partnerApi } from '@/lib/partner-api';
import { formatCurrency, formatCurrencyFromMinor, formatDate } from '@/lib/format';
import { StatusBadge } from '@/components/partner/shared/status-badge';
import { MetricCard } from '@/components/partner/shared/metric-card';
import { DashboardEarningsSkeleton } from '@/components/partner/shared/dashboard-skeleton';
import type { CommissionItem, CommissionListResponse } from '@/types/partner';

// --- Empty state with projected earnings ---
function EarningsEmpty() {
  const projections = [
    { referrals: 1, monthly: 14.7, yearly: 176.4 },
    { referrals: 5, monthly: 73.5, yearly: 882 },
    { referrals: 10, monthly: 147, yearly: 1764 },
    { referrals: 25, monthly: 367.5, yearly: 4410 },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="max-w-4xl space-y-8"
    >
      <div>
        <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">
          Earnings
        </h1>
      </div>

      {/* Projected earnings */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
        className="border border-border/60 rounded-lg bg-background overflow-hidden"
      >
        <div className="px-5 py-3.5 border-b border-border/60">
          <p className="text-xs font-mono uppercase tracking-widest text-muted-foreground">
            Projected earnings at $49/mo Pro plan
          </p>
        </div>
        <div className="divide-y divide-border/30">
          {projections.map((p, i) => {
            const barWidth = Math.min((p.referrals / 25) * 100, 100);
            return (
              <motion.div
                key={p.referrals}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.2 + i * 0.06 }}
                className="px-5 py-4 flex items-center gap-4"
              >
                <div className="w-20 shrink-0">
                  <span className="font-mono text-xs text-muted-foreground">
                    {p.referrals} {p.referrals === 1 ? 'referral' : 'referrals'}
                  </span>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="h-2 bg-muted/60 rounded-full overflow-hidden">
                    <motion.div
                      initial={{ width: 0 }}
                      animate={{ width: `${barWidth}%` }}
                      transition={{ duration: 0.8, delay: 0.3 + i * 0.08, ease: [0.25, 0.1, 0.25, 1] }}
                      className="h-full bg-foreground/80 rounded-full"
                    />
                  </div>
                </div>
                <div className="w-28 text-right shrink-0">
                  <p className="font-mono text-sm tabular-nums">
                    {formatCurrency(p.monthly)}/mo
                  </p>
                  <p className="font-mono text-[10px] text-muted-foreground">
                    {formatCurrency(p.yearly)}/yr
                  </p>
                </div>
              </motion.div>
            );
          })}
        </div>
        <div className="px-5 py-3 border-t border-border/60 bg-muted/20">
          <p className="text-[11px] text-muted-foreground">
            Projections based on 30% commission of $49/mo subscription. Actual earnings depend on referral plan and retention.
          </p>
        </div>
      </motion.div>

      {/* CTA */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.5 }}
        className="py-8 text-center"
      >
        <h3 className="text-lg font-medium tracking-tight mb-2">
          No earnings yet
        </h3>
        <p className="text-sm text-muted-foreground max-w-sm mx-auto">
          When your referrals subscribe, your commissions will appear here.
          Share your referral link to get started.
        </p>
      </motion.div>
    </motion.div>
  );
}

// --- Commission row ---
function CommissionRow({ commission, index }: { commission: CommissionItem; index: number }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ delay: 0.02 * index }}
      className="border-b border-border/30 last:border-b-0 hover:bg-muted/30 transition-colors"
    >
      {/* Desktop row */}
      <div className="hidden md:flex items-center justify-between px-5 py-3.5">
        <div className="flex-1 min-w-0">
          <p className="text-sm truncate">
            {commission.period
              ? `Commission for ${commission.period}`
              : 'Referral commission'}
          </p>
          <p className="text-[11px] font-mono text-muted-foreground mt-0.5">
            {formatDate(commission.created_at)}
            {commission.payable_at && (
              <span className="ml-2">Payable {formatDate(commission.payable_at)}</span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-4 ml-4">
          <span className="text-xs text-muted-foreground">
            {commission.commission_rate}%
          </span>
          <StatusBadge status={commission.status} />
          <span className="font-mono text-sm tabular-nums min-w-[80px] text-right">
            {formatCurrencyFromMinor(commission.commission_amount_minor, commission.currency)}
          </span>
        </div>
      </div>
      {/* Mobile card */}
      <div className="md:flex md:hidden px-5 py-4">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-sm truncate">
            {commission.period
              ? `Commission for ${commission.period}`
              : 'Referral commission'}
          </span>
          <StatusBadge status={commission.status} />
        </div>
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-mono text-muted-foreground">
            {formatDate(commission.created_at)}
          </span>
          <span className="font-mono text-sm tabular-nums">
            {formatCurrencyFromMinor(commission.commission_amount_minor, commission.currency)}
          </span>
        </div>
      </div>
    </motion.div>
  );
}

// --- Main page ---
export function PageEarnings() {
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const { data: response, isLoading, isError } = useQuery<CommissionListResponse>({
    queryKey: ['partner-commissions', page],
    queryFn: () => partnerApi.getCommissions(page, pageSize),
    staleTime: 30_000,
  });

  const list = response?.items || [];
  const total = response?.total ?? 0;
  const totalPages = Math.ceil(total / pageSize);

  // Group commissions by period for the bar chart (use all pages' worth if possible — first page only)
  const monthlyData = useMemo(() => {
    const periodMap = new Map<string, number>();
    for (const c of list) {
      if (c.period) {
        periodMap.set(c.period, (periodMap.get(c.period) || 0) + c.commission_amount_minor / 100);
      }
    }
    const entries = Array.from(periodMap.entries());
    entries.sort((a, b) => a[0].localeCompare(b[0]));
    return entries.slice(-12) as [string, number][];
  }, [list]);

  const maxMonthly = Math.max(...monthlyData.map(([, v]) => v), 1);

  // Calculate summary from commissions
  const summary = useMemo(() => {
    const now = new Date();
    const thisMonth = now.getMonth();
    const thisYear = now.getFullYear();

    let thisMonthTotal = 0;
    let pendingTotal = 0;
    let payableTotal = 0;
    let paidTotal = 0;
    let totalEarned = 0;

    for (const c of list) {
      const amount = c.commission_amount_minor / 100;
      totalEarned += amount;

      if (c.status === 'pending') pendingTotal += amount;
      if (c.status === 'payable') payableTotal += amount;
      if (c.status === 'paid') paidTotal += amount;

      const d = new Date(c.created_at);
      if (d.getMonth() === thisMonth && d.getFullYear() === thisYear) {
        thisMonthTotal += amount;
      }
    }

    return { totalEarned, thisMonthTotal, pendingTotal, payableTotal, paidTotal };
  }, [list]);

  if (isLoading) {
    return <DashboardEarningsSkeleton />;
  }

  if (isError) {
    return (
      <div className="max-w-4xl">
        <p className="text-sm text-muted-foreground">
          Unable to load earnings. Please try refreshing.
        </p>
      </div>
    );
  }

  if (list.length === 0 && page === 1) {
    return <EarningsEmpty />;
  }

  return (
    <div className="max-w-4xl space-y-8">
      {/* Heading */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
      >
        <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">
          Earnings
        </h1>
      </motion.div>

      {/* Hero metric */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.05 }}
      >
        <div className="border border-border/60 rounded-lg bg-background p-6 md:p-8">
          <p className="text-xs font-mono uppercase tracking-widest text-muted-foreground mb-2">
            Total earned
          </p>
          <p className="text-4xl md:text-5xl font-semibold tracking-tight tabular-nums">
            {formatCurrency(summary.totalEarned)}
          </p>
        </div>
      </motion.div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard
          label="This Month"
          value={formatCurrency(summary.thisMonthTotal)}
          delay={0.1}
        />
        <MetricCard
          label="Pending"
          value={formatCurrency(summary.pendingTotal)}
          delay={0.15}
        />
        <MetricCard
          label="Payable"
          value={formatCurrency(summary.payableTotal)}
          delay={0.2}
        />
        <MetricCard
          label="Paid"
          value={formatCurrency(summary.paidTotal)}
          delay={0.25}
        />
      </div>

      {/* Monthly earnings trend */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.28 }}
        className="border border-border/60 rounded-lg bg-background p-5 md:p-6"
      >
        <p className="text-xs font-mono uppercase tracking-widest text-muted-foreground mb-5">
          Monthly earnings trend
        </p>
        {monthlyData.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No period data available to display the chart.
          </p>
        ) : (
          <div className="relative">
            {/* Y-axis labels + bars container */}
            <div className="flex items-end gap-0">
              {/* Amount labels above bars */}
              <div className="flex-1 flex items-end justify-around" style={{ height: 160 }}>
                {monthlyData.map(([period, amount], i) => {
                  const heightPercent = (amount / maxMonthly) * 100;
                  return (
                    <div key={period} className="flex flex-col items-center flex-1 max-w-[60px]">
                      <motion.span
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        transition={{ delay: 0.35 + i * 0.05, duration: 0.3 }}
                        className="font-mono text-[10px] tabular-nums text-muted-foreground mb-1.5 whitespace-nowrap"
                      >
                        {formatCurrency(amount)}
                      </motion.span>
                      <motion.div
                        initial={{ height: 0 }}
                        animate={{ height: `${heightPercent}%` }}
                        transition={{
                          duration: 0.6,
                          delay: 0.35 + i * 0.05,
                          ease: [0.25, 0.1, 0.25, 1],
                        }}
                        className="w-full max-w-[32px] bg-foreground/80 rounded-t-sm hover:bg-foreground transition-colors cursor-default"
                        style={{ minHeight: 2 }}
                      />
                    </div>
                  );
                })}
              </div>
            </div>
            {/* Month labels below bars */}
            <div className="flex justify-around mt-2 border-t border-border/40 pt-2">
              {monthlyData.map(([period], i) => {
                const shortLabel = period.slice(5);
                const monthNames = [
                  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
                ];
                const monthIndex = parseInt(shortLabel, 10) - 1;
                const label = monthNames[monthIndex] ?? shortLabel;
                return (
                  <motion.span
                    key={period}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.4 + i * 0.04, duration: 0.3 }}
                    className="font-mono text-[10px] text-muted-foreground flex-1 text-center"
                  >
                    {label}
                  </motion.span>
                );
              })}
            </div>
          </div>
        )}
      </motion.div>

      {/* Earnings history */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.5 }}
        className="border border-border/60 rounded-lg bg-background overflow-hidden"
      >
        <div className="px-5 py-3.5 border-b border-border/60">
          <p className="text-xs font-mono uppercase tracking-widest text-muted-foreground">
            Earnings history
          </p>
        </div>
        {list.map((c, i) => (
          <CommissionRow key={c.id} commission={c} index={i} />
        ))}
      </motion.div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <motion.button
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
            className="flex items-center gap-1.5 rounded-md border border-border/60 bg-background px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground disabled:opacity-40 transition-colors"
          >
            Previous
          </motion.button>
          <span className="text-xs font-mono text-muted-foreground px-3">
            {page} / {totalPages}
          </span>
          <motion.button
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
            className="flex items-center gap-1.5 rounded-md border border-border/60 bg-background px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground disabled:opacity-40 transition-colors"
          >
            Next
          </motion.button>
        </div>
      )}
    </div>
  );
}
