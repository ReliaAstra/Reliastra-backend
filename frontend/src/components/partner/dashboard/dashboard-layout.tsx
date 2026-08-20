'use client';

import { useEffect, useState, useCallback } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AnimatePresence, motion } from 'framer-motion';
import {
  LayoutDashboard,
  Users,
  DollarSign,
  Wallet,
  Settings,
  LogOut,
  Menu,
  ChevronRight,
  ExternalLink,
  MessageSquare,
} from 'lucide-react';
import { usePartnerStore } from '@/stores/partner-store';
import { partnerApi } from '@/lib/partner-api';
import { maskEmail } from '@/lib/format';
import { toast } from 'sonner';
import type { PartnerPage } from '@/types/partner';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { PageOverview } from './page-overview';
import { PageReferrals } from './page-referrals';
import { PageEarnings } from './page-earnings';
import { PagePayouts } from './page-payouts';
import { PageSettings } from './page-settings';
import { ThemeToggle } from '../shared/theme-toggle';
import { CommandPalette } from '../shared/command-palette';
import { TierBadge } from '../shared/tier-badge';
import { getPartnerTier, type TierInfo } from '@/types/partner';

// --- Query client (created once) ---
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

// --- Navigation config ---
interface NavItem {
  page: PartnerPage;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}

const sidebarNav: NavItem[] = [
  { page: 'dashboard', label: 'Overview', icon: LayoutDashboard },
  { page: 'referrals', label: 'Referrals', icon: Users },
  { page: 'earnings', label: 'Earnings', icon: DollarSign },
  { page: 'payouts', label: 'Payouts', icon: Wallet },
  { page: 'settings', label: 'Settings', icon: Settings },
];

const mobileNav: NavItem[] = [
  { page: 'dashboard', label: 'Overview', icon: LayoutDashboard },
  { page: 'referrals', label: 'Referrals', icon: Users },
  { page: 'earnings', label: 'Earnings', icon: DollarSign },
  { page: 'payouts', label: 'Payouts', icon: Wallet },
];

// --- RELIASTRA Logo ---
function ReliastraLogo({ className }: { className?: string }) {
  return (
    <div className={cn('flex items-center gap-2', className)}>
      <svg
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill="none"
        className="shrink-0"
      >
        <rect x="2" y="2" width="20" height="20" rx="4" stroke="currentColor" strokeWidth="1.5" />
        <path
          d="M8 12L11 15L16 9"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span className="font-mono text-sm tracking-[0.2em] font-medium">RELIASTRA</span>
    </div>
  );
}

// --- Sidebar (desktop) ---
function DesktopSidebar() {
  const currentPage = usePartnerStore((s) => s.currentPage);
  const navigate = usePartnerStore((s) => s.navigate);
  const user = usePartnerStore((s) => s.user);
  const setUser = usePartnerStore((s) => s.setUser);
  const setAuthStatus = usePartnerStore((s) => s.setAuthStatus);
  const reset = usePartnerStore((s) => s.reset);

  const handleSignOut = useCallback(async () => {
    try {
      await partnerApi.logout();
    } catch {
      // continue regardless
    }
    reset();
    toast.success('Signed out');
    navigate('home');
  }, [reset, navigate]);

  return (
    <aside className="hidden md:flex md:flex-col md:w-[240px] md:shrink-0 border-r border-border/60 bg-background">
      {/* Logo */}
      <div className="px-6 pt-6 pb-2">
        <ReliastraLogo />
        <p className="text-[10px] font-mono uppercase tracking-[0.25em] text-muted-foreground mt-1.5">
          Partner
        </p>
      </div>

      <Separator className="my-3" />

      {/* Navigation */}
      <nav className="flex-1 px-3 space-y-0.5" aria-label="Dashboard navigation">
        {sidebarNav.map((item) => {
          const isActive = currentPage === item.page;
          const Icon = item.icon;
          return (
            <button
              key={item.page}
              onClick={() => navigate(item.page)}
              className={cn(
                'w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-sm text-left transition-colors duration-150',
                'hover:bg-muted/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1',
                isActive
                  ? 'border-l-2 border-foreground -ml-px bg-muted/80 text-foreground font-medium'
                  : 'border-l-2 border-transparent -ml-px text-muted-foreground'
              )}
              aria-current={isActive ? 'page' : undefined}
            >
              <Icon className="size-4 shrink-0" />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      {/* Support button */}
      <div className="px-3">
        <button
          onClick={() => navigate('support')}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-sm text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <MessageSquare className="size-4 shrink-0" />
          <span>Support</span>
        </button>
      </div>

      {/* Bottom section */}
      <div className="px-3 pb-4">
        <Separator className="mb-3" />
        <button
          onClick={handleSignOut}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-sm text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <LogOut className="size-4 shrink-0" />
          <span>Sign out</span>
        </button>
      </div>
    </aside>
  );
}

// --- Mobile bottom nav ---
function MobileBottomNav({ onMoreOpen }: { onMoreOpen: () => void }) {
  const currentPage = usePartnerStore((s) => s.currentPage);
  const navigate = usePartnerStore((s) => s.navigate);

  return (
    <nav
      className="md:hidden fixed bottom-0 left-0 right-0 z-50 border-t border-border/60 bg-background/95 backdrop-blur-sm"
      aria-label="Mobile navigation"
    >
      <div className="flex items-center justify-around h-14 px-2">
        {mobileNav.map((item) => {
          const isActive = currentPage === item.page;
          const Icon = item.icon;
          return (
            <button
              key={item.page}
              onClick={() => navigate(item.page)}
              className={cn(
                'flex flex-col items-center justify-center gap-0.5 px-3 py-1 rounded-md min-w-[56px] transition-colors',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                isActive ? 'text-foreground' : 'text-muted-foreground'
              )}
              aria-current={isActive ? 'page' : undefined}
            >
              <Icon className={cn('size-5', isActive && 'fill-current')} />
              <span className={cn('text-[10px] font-mono tracking-wide', isActive && 'font-medium')}>
                {item.label}
              </span>
            </button>
          );
        })}
        <button
          onClick={onMoreOpen}
          className={cn(
            'flex flex-col items-center justify-center gap-0.5 px-3 py-1 rounded-md min-w-[56px] transition-colors',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            currentPage === 'settings' ? 'text-foreground' : 'text-muted-foreground'
          )}
          aria-label="More options"
        >
          <svg
            width="20"
            height="20"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            className={currentPage === 'settings' ? 'fill-current' : ''}
          >
            <circle cx="12" cy="5" r="1.5" />
            <circle cx="12" cy="12" r="1.5" />
            <circle cx="12" cy="19" r="1.5" />
          </svg>
          <span
            className={cn(
              'text-[10px] font-mono tracking-wide',
              currentPage === 'settings' && 'font-medium'
            )}
          >
            More
          </span>
        </button>
      </div>
      {/* Safe area spacer for iOS */}
      <div className="h-[env(safe-area-inset-bottom)]" />
    </nav>
  );
}

// --- Mobile "More" sheet ---
function MoreSheet({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const navigate = usePartnerStore((s) => s.navigate);
  const reset = usePartnerStore((s) => s.reset);

  const handleSignOut = useCallback(async () => {
    try {
      await partnerApi.logout();
    } catch {
      // continue
    }
    onOpenChange(false);
    reset();
    toast.success('Signed out');
    navigate('home');
  }, [reset, navigate, onOpenChange]);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="bottom" className="rounded-t-xl">
        <SheetHeader>
          <SheetTitle className="text-left font-mono text-xs tracking-widest uppercase text-muted-foreground">
            More
          </SheetTitle>
        </SheetHeader>
        <div className="mt-4 space-y-1">
          <button
            onClick={() => {
              onOpenChange(false);
              navigate('settings');
            }}
            className="w-full flex items-center gap-3 px-3 py-3 rounded-md text-sm text-foreground hover:bg-muted/60 transition-colors text-left"
          >
            <Settings className="size-4 text-muted-foreground" />
            <span>Settings</span>
            <ChevronRight className="size-4 text-muted-foreground ml-auto" />
          </button>
          <button
            onClick={() => { onOpenChange(false); navigate('support'); }}
            className="w-full flex items-center gap-3 px-3 py-3 rounded-md text-sm text-foreground hover:bg-muted/60 transition-colors text-left"
          >
            <MessageSquare className="size-4 text-muted-foreground" />
            <span>Contact Support</span>
            <ChevronRight className="size-4 text-muted-foreground ml-auto" />
          </button>
          <Separator />
          <button
            onClick={handleSignOut}
            className="w-full flex items-center gap-3 px-3 py-3 rounded-md text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors text-left"
          >
            <LogOut className="size-4" />
            <span>Sign out</span>
          </button>
        </div>
      </SheetContent>
    </Sheet>
  );
}

// --- Top bar ---
function TopBar({ onMoreOpen }: { onMoreOpen: () => void }) {
  const user = usePartnerStore((s) => s.user);
  const navigate = usePartnerStore((s) => s.navigate);
  const reset = usePartnerStore((s) => s.reset);
  const dashboardData = usePartnerStore((s) => s.dashboardData);

  const currentTier: TierInfo = getPartnerTier(dashboardData?.referrals?.length ?? 0);

  const handleSignOut = useCallback(async () => {
    try {
      await partnerApi.logout();
    } catch {
      // continue
    }
    reset();
    toast.success('Signed out');
    navigate('home');
  }, [reset, navigate]);

  const initials = user?.name
    ? user.name
        .split(' ')
        .map((n) => n[0])
        .join('')
        .slice(0, 2)
        .toUpperCase()
    : user?.email?.[0]?.toUpperCase() || 'P';

  return (
    <header className="sticky top-0 z-40 flex items-center justify-between h-14 px-4 md:px-6 border-b border-border/60 bg-background/95 backdrop-blur-sm">
      {/* Mobile logo */}
      <div className="flex items-center gap-3 md:hidden">
        <ReliastraLogo />
      </div>

      {/* Spacer for desktop */}
      <div className="hidden md:block" />

      {/* Right side */}
      <div className="flex items-center gap-2">
        <ThemeToggle />
        <div className="hidden sm:inline-flex items-center gap-1.5">
          <TierBadge tier={currentTier} size="sm" />
        </div>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              className="flex items-center gap-2 rounded-md p-1.5 hover:bg-muted/60 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label="Account menu"
            >
              <Avatar className="size-7">
                <AvatarFallback className="bg-muted text-[11px] font-mono font-medium">
                  {initials}
                </AvatarFallback>
              </Avatar>
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-56">
            <DropdownMenuLabel className="font-normal">
              <div className="flex flex-col gap-1">
                <p className="text-sm font-medium">
                  {user?.name || 'Partner'}
                </p>
                <p className="text-xs font-mono text-muted-foreground">
                  {user?.email ? maskEmail(user.email) : ''}
                </p>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={() => navigate('dashboard')}
                  className="text-xs font-mono uppercase tracking-wide"
            >
              <LayoutDashboard className="size-4 mr-2" />
              Dashboard
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => navigate('settings')}
              className="text-xs font-mono uppercase tracking-wide"
            >
              <Settings className="size-4 mr-2" />
              Settings
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={() => navigate('home')}
              className="text-xs font-mono uppercase tracking-wide"
            >
              <ExternalLink className="size-4 mr-2" />
              Main site
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              onClick={handleSignOut}
              className="text-xs font-mono uppercase tracking-wide text-red-600 dark:text-red-400 focus:text-red-600 dark:focus:text-red-400"
            >
              <LogOut className="size-4 mr-2" />
              Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}

// --- Page router ---
function DashboardPages() {
  const currentPage = usePartnerStore((s) => s.currentPage);

  const pageVariants = {
    initial: { opacity: 0, y: 8 },
    animate: { opacity: 1, y: 0 },
    exit: { opacity: 0, y: -8 },
  };

  const pageTransition = { duration: 0.25, ease: [0.25, 0.1, 0.25, 1] as const };

  return (
    <AnimatePresence mode="wait">
      {currentPage === 'dashboard' && (
        <motion.div
          key="dashboard"
          variants={pageVariants}
          initial="initial"
          animate="animate"
          exit="exit"
          transition={pageTransition}
        >
          <PageOverview />
        </motion.div>
      )}
      {currentPage === 'referrals' && (
        <motion.div
          key="referrals"
          variants={pageVariants}
          initial="initial"
          animate="animate"
          exit="exit"
          transition={pageTransition}
        >
          <PageReferrals />
        </motion.div>
      )}
      {currentPage === 'earnings' && (
        <motion.div
          key="earnings"
          variants={pageVariants}
          initial="initial"
          animate="animate"
          exit="exit"
          transition={pageTransition}
        >
          <PageEarnings />
        </motion.div>
      )}
      {currentPage === 'payouts' && (
        <motion.div
          key="payouts"
          variants={pageVariants}
          initial="initial"
          animate="animate"
          exit="exit"
          transition={pageTransition}
        >
          <PagePayouts />
        </motion.div>
      )}
      {currentPage === 'settings' && (
        <motion.div
          key="settings"
          variants={pageVariants}
          initial="initial"
          animate="animate"
          exit="exit"
          transition={pageTransition}
        >
          <PageSettings />
        </motion.div>
      )}
    </AnimatePresence>
  );
}

// --- Main export ---
export function DashboardLayout() {
  const navigate = usePartnerStore((s) => s.navigate);
  const setDashboardData = usePartnerStore((s) => s.setDashboardData);
  const [moreSheetOpen, setMoreSheetOpen] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);

  // Fetch dashboard data on mount
  useEffect(() => {
    let cancelled = false;

    const fetchDashboard = async () => {
      try {
        const data = await partnerApi.getDashboard();
        if (!cancelled) {
          setDashboardData(data);
        }
      } catch (err) {
        if (!cancelled) {
          const msg = err instanceof Error ? err.message : '';
          if (msg === 'UNAUTHORIZED') {
            navigate('login');
            return;
          }
        }
      } finally {
        if (!cancelled) {
          setInitialLoading(false);
        }
      }
    };

    fetchDashboard();
    return () => {
      cancelled = true;
    };
  }, [setDashboardData, navigate]);

  return (
    <QueryClientProvider client={queryClient}>
      <div className="flex min-h-screen flex-col bg-background">
        <div className="flex flex-1">
          {/* Desktop sidebar */}
          <DesktopSidebar />

          {/* Main content area */}
          <div className="flex flex-1 flex-col min-w-0">
            <TopBar onMoreOpen={() => setMoreSheetOpen(true)} />

            <main className="flex-1 px-4 md:px-8 py-6 md:py-8 pb-24 md:pb-8">
              {initialLoading ? (
                <div className="space-y-6 max-w-4xl">
                  <div className="space-y-2">
                    <Skeleton className="h-8 w-64" />
                    <Skeleton className="h-4 w-80" />
                  </div>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    {[...Array(4)].map((_, i) => (
                      <Skeleton key={i} className="h-24 rounded-lg" />
                    ))}
                  </div>
                  <Skeleton className="h-32 rounded-lg" />
                  <Skeleton className="h-48 rounded-lg" />
                </div>
              ) : (
                <DashboardPages />
              )}
            </main>
          </div>
        </div>

        {/* Mobile bottom nav */}
        <MobileBottomNav onMoreOpen={() => setMoreSheetOpen(true)} />

        {/* Mobile more sheet */}
        <MoreSheet open={moreSheetOpen} onOpenChange={setMoreSheetOpen} />
        <CommandPalette />
      </div>
    </QueryClientProvider>
  );
}
