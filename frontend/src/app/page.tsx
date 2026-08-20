'use client';

import { useEffect, useState } from 'react';
import { usePartnerStore } from '@/stores/partner-store';
import { PageLanding } from '@/components/landing/page-landing';
import { PublicLayout } from '@/components/partner/public/public-layout';
import { DashboardLayout } from '@/components/partner/dashboard/dashboard-layout';
import type { PartnerPage } from '@/types/partner';

const dashboardPages: PartnerPage[] = [
  'dashboard',
  'referrals',
  'earnings',
  'payouts',
  'settings',
];

export default function Home() {
  const currentPage = usePartnerStore((s) => s.currentPage);
  const authStatus = usePartnerStore((s) => s.authStatus);
  const user = usePartnerStore((s) => s.user);
  const navigate = usePartnerStore((s) => s.navigate);
  const setAuthStatus = usePartnerStore((s) => s.setAuthStatus);
  const setUser = usePartnerStore((s) => s.setUser);
  const setPartner = usePartnerStore((s) => s.setPartner);
  const [mounted, setMounted] = useState(false);

  // Hydrate auth state from server on mount
  useEffect(() => {
    const checkAuth = async () => {
      try {
        const token = localStorage.getItem('partner_access_token');
        if (!token) {
          setAuthStatus('unauthenticated');
          setMounted(true);
          return;
        }

        // Fetch /api/auth/me — returns UserResponse directly (snake_case, not wrapped)
        const meRes = await fetch('/api/auth/me', {
          headers: { Authorization: `Bearer ${token}` },
        });

        if (meRes.ok) {
          const data = await meRes.json();
          setUser({
            id: data.id,
            email: data.email,
            fullName: data.full_name,
          });
          setAuthStatus('authenticated');

          // Also try to fetch partner profile in parallel
          const partnerRes = await fetch('/api/partners/me', {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (partnerRes.ok) {
            const p = await partnerRes.json();
            setPartner({
              partnerId: p.partner_id,
              referralCode: p.referral_code,
              referralLink: p.referral_link,
              commissionRate: p.commission_rate,
              status: p.status,
              createdAt: p.created_at,
            });
          }
        } else {
          // Token is invalid
          localStorage.removeItem('partner_access_token');
          localStorage.removeItem('partner_refresh_token');
          setAuthStatus('unauthenticated');
        }
      } catch {
        setAuthStatus('unauthenticated');
      }
      setMounted(true);
    };
    checkAuth();
  }, [setUser, setAuthStatus, setPartner]);

  // Redirect unauthenticated users away from dashboard pages
  // Redirect to home if authenticated user tries a non-existent dashboard page
  useEffect(() => {
    if (!mounted) return;
    const isDashboardPage = dashboardPages.includes(currentPage);
    if (isDashboardPage && authStatus === 'unauthenticated') {
      navigate('login');
      return;
    }
    // Fallback: redirect non-authenticated users from dashboard pages to home
    if (isDashboardPage && authStatus !== 'unauthenticated' && authStatus !== 'authenticated') {
      navigate('home');
    }
  }, [currentPage, authStatus, mounted, navigate]);

  if (!mounted) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="flex items-center gap-3">
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            className="animate-pulse text-foreground"
          >
            <rect x="2" y="2" width="20" height="20" rx="4" stroke="currentColor" strokeWidth="1.5" />
            <path d="M8 12L11 15L16 9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span className="font-mono text-xs tracking-widest uppercase text-muted-foreground">
            RELIASTRA
          </span>
        </div>
      </div>
    );
  }

  const isPublicPage = !dashboardPages.includes(currentPage);

  if (currentPage === 'landing') {
    return <PageLanding />;
  }

  if (isPublicPage) {
    return <PublicLayout />;
  }

  // Dashboard pages: authenticated users
  if (authStatus === 'authenticated' && user) {
    return <DashboardLayout />;
  }

  // For dashboard pages that aren't yet authenticated, show nothing (useEffect handles redirect)
  if (dashboardPages.includes(currentPage)) {
    return null;
  }

  // Public pages fallback
  return <PublicLayout />;
}
