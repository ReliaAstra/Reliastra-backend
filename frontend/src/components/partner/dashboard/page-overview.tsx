'use client';

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { ArrowRight, Users, DollarSign } from 'lucide-react';
import { usePartnerStore } from '@/stores/partner-store';
import { partnerApi } from '@/lib/partner-api';
import { formatCurrencyFromMinor, formatDate } from '@/lib/format';
import { MetricCard } from '@/components/partner/shared/metric-card';
import { ReferralLinkCard } from '@/components/partner/shared/referral-link-card';
import { StatusBadge } from '@/components/partner/shared/status-badge';
import { EmptyState } from '@/components/partner/shared/empty-state';
import { TierProgressCard } from '@/components/partner/shared/tier-progress-card';
import { DashboardOverviewSkeleton } from '@/components/partner/shared/dashboard-skeleton';
import type { ReferralItem, CommissionItem } from '@/types/partner';

// --- How it works strip ---
function HowItWorks() {
  const steps = [
    { label: 'SHARE', detail: 'Your link' },
    { label: 'THEY SUBSCRIBE', detail: 'To RELIASTRA' },
    { label: 'YOU EARN 30%', detail: 'Every month' },
  ];

  return (
    <div className="flex items-center justify-center gap-0 py-5">
      {steps.map((step, i) => (
        <div key={step.label} className="flex items-center">
          <div className="flex flex-col items-center text-center">
            <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-foreground font-medium">
              {step.label}
            </span>
            <span className="text-[11px] text-muted-foreground mt-0.5">
              {step.detail}
            </span>
          </div>
          {i < steps.length - 1 && (
            <ArrowRight className="size-3.5 text-border mx-4 md:mx-6 shrink-0" />
          )}
        </div>
      ))}
    </div>
  );
}

// --- Activity feed ---
type ActivityItem =
  | { type: 'referral'; item: ReferralItem }
  | { type: 'commission'; item: CommissionItem };

function ActivityFeed({ items }: { items: ActivityItem[] }) {
  if (items.length === 0) return null;

  return (
    <div className="border border-border/60 rounded-lg bg-background overflow-hidden">
      <div className="px-5 py-3.5 border-b border-border/60">
        <p className="text-xs font-mono uppercase tracking-widest text-muted-foreground">
          Recent activity
        </p>
      </div>
      <div className="px-5 py-4">
        {items.map((entry, i) => {
          const isLast = i === items.length - 1;
          const dateStr = entry.item.created_at;
          return (
            <div
              key={
                entry.type === 'referral'
                  ? `ref-${entry.item.referral_id}`
                  : `com-${entry.item.id}`
              }
              className={`${!isLast ? 'border-l border-border/40' : 'border-l border-transparent'} ml-3.5 pl-4 pb-5 last:pb-0`}
            >
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.3, delay: 0.05 * i }}
                className="flex items-start gap-3 -ml-[30px]"
              >
                {/* Icon circle */}
                <div className="size-7 rounded-full bg-muted/80 flex items-center justify-center shrink-0">
                  {entry.type === 'referral' ? (
                    <Users className="size-3.5 text-muted-foreground" />
                  ) : (
                    <DollarSign className="size-3.5 text-muted-foreground" />
                  )}
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0 pt-0.5">
                  {entry.type === 'referral' ? (
                    <>
                      <p className="text-sm">
                        New referral{' '}
                        <span className="font-mono text-xs text-muted-foreground">
                          {entry.item.masked_email
                            ? entry.item.masked_email
                            : ''}
                        </span>
                        {entry.item.plan && (
                          <span className="text-muted-foreground">
                            {' '}&middot; {entry.item.plan}
                          </span>
                        )}
                      </p>
                    </>
                  ) : (
                    <p className="text-sm">
                      Commission earned
                      {entry.item.period && (
                        <span className="text-muted-foreground">
                          {' '}&middot; {entry.item.period}
                        </span>
                      )}
                    </p>
                  )}
                  <p className="text-[11px] font-mono text-muted-foreground mt-0.5">
                    {formatDate(dateStr)}
                  </p>
                </div>

                {/* Right side amount for commissions */}
                {entry.type === 'commission' && (
                  <span className="font-mono text-sm tabular-nums shrink-0 pt-0.5">
                    {formatCurrencyFromMinor(entry.item.commission_amount_minor, entry.item.currency)}
                  </span>
                )}
              </motion.div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// --- Recent referrals table ---
function RecentReferrals({ referrals }: { referrals: ReferralItem[] }) {
  const recent = referrals.slice(0, 5);

  if (recent.length === 0) return null;

  return (
    <div className="border border-border/60 rounded-lg bg-background overflow-hidden">
      <div className="px-5 py-3.5 border-b border-border/60">
        <p className="text-xs font-mono uppercase tracking-widest text-muted-foreground">
          Recent referrals
        </p>
      </div>
      {/* Desktop table */}
      <div className="hidden md:block">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border/40">
              <th className="text-left px-5 py-2.5 text-[10px] font-mono uppercase tracking-widest text-muted-foreground font-normal">
                Customer
              </th>
              <th className="text-left px-5 py-2.5 text-[10px] font-mono uppercase tracking-widest text-muted-foreground font-normal">
                Plan
              </th>
              <th className="text-left px-5 py-2.5 text-[10px] font-mono uppercase tracking-widest text-muted-foreground font-normal">
                Status
              </th>
              <th className="text-right px-5 py-2.5 text-[10px] font-mono uppercase tracking-widest text-muted-foreground font-normal">
                Monthly earned
              </th>
            </tr>
          </thead>
          <tbody>
            {recent.map((ref) => (
              <tr
                key={ref.referral_id}
                className="border-b border-border/30 last:border-b-0 hover:bg-muted/30 transition-colors"
              >
                <td className="px-5 py-3">
                  <span className="font-mono text-xs">
                    {ref.masked_email || '---'}
                  </span>
                </td>
                <td className="px-5 py-3 text-muted-foreground">{ref.plan || '---'}</td>
                <td className="px-5 py-3">
                  <StatusBadge status={ref.status} />
                </td>
                <td className="px-5 py-3 text-right font-mono tabular-nums">
                  {formatCurrencyFromMinor(ref.monthly_commission_minor)}/mo
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {/* Mobile cards */}
      <div className="md:hidden divide-y divide-border/40">
        {recent.map((ref) => (
          <div key={ref.referral_id} className="px-5 py-3.5">
            <div className="flex items-center justify-between mb-1.5">
              <span className="font-mono text-xs">
                {ref.masked_email || '---'}
              </span>
              <StatusBadge status={ref.status} />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">{ref.plan || '---'}</span>
              <span className="font-mono text-xs tabular-nums">
                {formatCurrencyFromMinor(ref.monthly_commission_minor)}/mo
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// --- Main page ---
export function PageOverview() {
  const storeDashboardData = usePartnerStore((s) => s.dashboardData);

  const { data: dashboard, isLoading, isError } = useQuery({
    queryKey: ['partner-dashboard'],
    queryFn: async () => {
      const data = await partnerApi.getDashboard();
      usePartnerStore.getState().setDashboardData(data);
      return data;
    },
    staleTime: 30_000,
  });

  const { data: referralsData } = useQuery({
    queryKey: ['partner-referrals-overview'],
    queryFn: () => partnerApi.getReferrals(1, 5),
    staleTime: 30_000,
  });

  const { data: commissionsData } = useQuery({
    queryKey: ['partner-commissions-overview'],
    queryFn: () => partnerApi.getCommissions(1, 5),
    staleTime: 30_000,
  });

  const d = dashboard || storeDashboardData;

  // Build merged activity timeline
  const activityItems = useMemo<ActivityItem[]>(() => {
    const items: ActivityItem[] = [];

    if (referralsData?.items) {
      for (const ref of referralsData.items) {
        items.push({ type: 'referral', item: ref });
      }
    }

    if (commissionsData?.items) {
      for (const com of commissionsData.items) {
        items.push({ type: 'commission', item: com });
      }
    }

    items.sort((a, b) => new Date(b.item.created_at).getTime() - new Date(a.item.created_at).getTime());
    return items.slice(0, 8);
  }, [referralsData, commissionsData]);

  // Check if truly empty (no signups and zero earnings)
  const isEmpty =
    d &&
    d.signups === 0 &&
    d.total_earned_minor === 0;

  if (isLoading) {
    return <DashboardOverviewSkeleton />;
  }

  if (isError || !d) {
    return (
      <div className="max-w-4xl">
        <p className="text-sm text-muted-foreground">
          Unable to load dashboard data. Please try refreshing.
        </p>
      </div>
    );
  }

  if (isEmpty) {
    return <EmptyState referralLink={d.referral_link} />;
  }

  const currency = d.currency || 'USD';

  return (
    <div className="max-w-4xl space-y-8">
      {/* Heading */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
      >
        <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">
          Your Partner Network
        </h1>
        <p className="text-muted-foreground mt-1.5 text-sm">
          Turn your referrals into recurring revenue.
        </p>
      </motion.div>

      {/* Tier progress card */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.05 }}
      >
        <TierProgressCard activeReferrals={d.active_paid_customers} />
      </motion.div>

      {/* Metric cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard
          label="Total Earned"
          value={formatCurrencyFromMinor(d.total_earned_minor, currency)}
          delay={0.05}
          animated
        />
        <MetricCard
          label="This Month"
          value={formatCurrencyFromMinor(d.monthly_commission_minor, currency)}
          delay={0.1}
          animated
        />
        <MetricCard
          label="Active Customers"
          value={String(d.active_paid_customers)}
          delay={0.15}
          animated
        />
        <MetricCard
          label="Payable"
          value={formatCurrencyFromMinor(d.pending_commission_minor, currency)}
          sublabel="Available to withdraw"
          delay={0.2}
          animated
        />
      </div>

      {/* Referral link card */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.25 }}
      >
        <ReferralLinkCard link={d.referral_link} size="large" />
      </motion.div>

      {/* How it works */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.5, delay: 0.3 }}
      >
        <div className="border border-border/40 rounded-lg bg-muted/20 py-1">
          <HowItWorks />
        </div>
      </motion.div>

      {/* Recent activity feed */}
      {(commissionsData !== undefined || referralsData !== undefined) && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.35 }}
        >
          <ActivityFeed items={activityItems} />
        </motion.div>
      )}

      {/* Recent referrals */}
      {referralsData?.items && referralsData.items.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, delay: 0.4 }}
        >
          <RecentReferrals referrals={referralsData.items} />
        </motion.div>
      )}
    </div>
  );
}
