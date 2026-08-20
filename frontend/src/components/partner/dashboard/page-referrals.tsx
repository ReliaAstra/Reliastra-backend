'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { Copy, ArrowLeft, ArrowRight } from 'lucide-react';
import { usePartnerStore } from '@/stores/partner-store';
import { partnerApi } from '@/lib/partner-api';
import { formatCurrencyFromMinor, formatDate } from '@/lib/format';
import { StatusBadge } from '@/components/partner/shared/status-badge';
import { ReferralLinkCard } from '@/components/partner/shared/referral-link-card';
import { DashboardReferralsSkeleton } from '@/components/partner/shared/dashboard-skeleton';
import { Button } from '@/components/ui/button';
import type { ReferralItem, ReferralListResponse } from '@/types/partner';

// --- Empty state ---
function ReferralsEmpty({ referralLink }: { referralLink: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className="max-w-4xl space-y-8"
    >
      <div>
        <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">
          Referrals
        </h1>
        <p className="text-muted-foreground mt-1.5 text-sm font-mono">
          0 referrals
        </p>
      </div>
      <div className="py-16 md:py-24 text-center">
        <h3 className="text-lg font-medium tracking-tight mb-2">
          No referrals yet
        </h3>
        <p className="text-sm text-muted-foreground mb-8 max-w-sm mx-auto">
          Share your referral link to start earning. When someone subscribes
          through your link, they&apos;ll appear here.
        </p>
        <div className="max-w-md mx-auto">
          <ReferralLinkCard link={referralLink} size="large" showLabel={false} />
        </div>
      </div>
    </motion.div>
  );
}

// --- Main page ---
export function PageReferrals() {
  const dashboardData = usePartnerStore((s) => s.dashboardData);
  const [page, setPage] = useState(1);
  const pageSize = 20;

  const { data: response, isLoading, isError } = useQuery<ReferralListResponse>({
    queryKey: ['partner-referrals', page],
    queryFn: () => partnerApi.getReferrals(page, pageSize),
    staleTime: 30_000,
  });

  const list = response?.items || [];
  const total = response?.total ?? 0;
  const totalPages = Math.ceil(total / pageSize);

  if (isLoading) {
    return <DashboardReferralsSkeleton />;
  }

  if (isError) {
    return (
      <div className="max-w-4xl">
        <p className="text-sm text-muted-foreground">
          Unable to load referrals. Please try refreshing.
        </p>
      </div>
    );
  }

  if (list.length === 0 && page === 1) {
    return <ReferralsEmpty referralLink={dashboardData?.referral_link || ''} />;
  }

  return (
    <div className="max-w-4xl space-y-6">
      {/* Heading */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
        className="flex items-center gap-3"
      >
        <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">
          Referrals
        </h1>
        <span className="text-xs font-mono text-muted-foreground bg-muted px-2 py-0.5 rounded">
          {total}
        </span>
      </motion.div>

      {/* Conversion funnel stats bar */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.05 }}
        className="border border-border/60 rounded-lg bg-background px-5 py-4 flex items-center justify-around divide-x divide-border/40"
      >
        {(() => {
          const activeCount = list.filter((r) => r.status === 'active').length;
          const conversionRate = list.length > 0 ? (activeCount / list.length * 100).toFixed(0) : '0';
          return (
            <>
              <div className="flex flex-col items-center text-center flex-1">
                <span className="text-lg md:text-xl font-semibold tabular-nums">{total}</span>
                <span className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">TOTAL</span>
              </div>
              <div className="flex flex-col items-center text-center flex-1">
                <span className="text-lg md:text-xl font-semibold tabular-nums">{activeCount}</span>
                <span className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">ACTIVE</span>
              </div>
              <div className="flex flex-col items-center text-center flex-1">
                <span className="text-lg md:text-xl font-semibold tabular-nums text-emerald-600 dark:text-emerald-400">{conversionRate}%</span>
                <span className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground">CONVERSION</span>
              </div>
            </>
          );
        })()}
      </motion.div>

      {/* Table container */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.05 }}
        className="border border-border/60 rounded-lg bg-background overflow-hidden"
      >
        {/* Desktop table */}
        <div className="hidden md:block">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border/60">
                <th className="text-left px-5 py-3 text-[10px] font-mono uppercase tracking-widest text-muted-foreground font-normal">
                  Customer
                </th>
                <th className="text-left px-5 py-3 text-[10px] font-mono uppercase tracking-widest text-muted-foreground font-normal">
                  Organization
                </th>
                <th className="text-left px-5 py-3 text-[10px] font-mono uppercase tracking-widest text-muted-foreground font-normal">
                  Plan
                </th>
                <th className="text-left px-5 py-3 text-[10px] font-mono uppercase tracking-widest text-muted-foreground font-normal">
                  Status
                </th>
                <th className="text-right px-5 py-3 text-[10px] font-mono uppercase tracking-widest text-muted-foreground font-normal">
                  Monthly Earned
                </th>
                <th className="text-right px-5 py-3 text-[10px] font-mono uppercase tracking-widest text-muted-foreground font-normal">
                  Date
                </th>
              </tr>
            </thead>
            <tbody>
              {list.map((ref, i) => (
                <motion.tr
                  key={ref.referral_id}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.03 * i }}
                  className="border-b border-border/30 last:border-b-0 hover:bg-muted/30 transition-colors"
                >
                  <td className="px-5 py-3.5">
                    <span className="font-mono text-xs">
                      {ref.masked_email || '---'}
                    </span>
                  </td>
                  <td className="px-5 py-3.5 text-muted-foreground text-xs">
                    {ref.organization_name || '---'}
                  </td>
                  <td className="px-5 py-3.5 text-muted-foreground text-xs">
                    {ref.plan || '---'}
                  </td>
                  <td className="px-5 py-3.5">
                    <StatusBadge status={ref.status} />
                  </td>
                  <td className="px-5 py-3.5 text-right font-mono tabular-nums text-xs">
                    {formatCurrencyFromMinor(ref.monthly_commission_minor)}/mo
                  </td>
                  <td className="px-5 py-3.5 text-right font-mono text-xs text-muted-foreground">
                    {formatDate(ref.created_at)}
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Mobile cards */}
        <div className="md:hidden divide-y divide-border/40">
          {list.map((ref, i) => (
            <motion.div
              key={ref.referral_id}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.03 * i }}
              className="px-5 py-4"
            >
              <div className="flex items-center justify-between mb-2">
                <span className="font-mono text-xs">
                  {ref.masked_email || '---'}
                </span>
                <StatusBadge status={ref.status} />
              </div>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <span className="text-xs text-muted-foreground">{ref.plan || '---'}</span>
                  <span className="text-[10px] font-mono text-muted-foreground">
                    {formatDate(ref.created_at)}
                  </span>
                </div>
                <span className="font-mono text-xs tabular-nums">
                  {formatCurrencyFromMinor(ref.monthly_commission_minor)}/mo
                </span>
              </div>
            </motion.div>
          ))}
        </div>
      </motion.div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
            className="gap-1.5"
          >
            <ArrowLeft className="size-3.5" />
            Previous
          </Button>
          <span className="text-xs font-mono text-muted-foreground px-3">
            {page} / {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => p + 1)}
            className="gap-1.5"
          >
            Next
            <ArrowRight className="size-3.5" />
          </Button>
        </div>
      )}
    </div>
  );
}
