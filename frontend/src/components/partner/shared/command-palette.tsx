'use client';

import { useEffect, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  LayoutDashboard,
  Users,
  DollarSign,
  Wallet,
  Settings,
  MessageSquare,
  Home,
  HelpCircle,
  BookOpen,
  FileText,
  Crown,
  LogOut,
  Sun,
  Moon,
} from 'lucide-react';
import { usePartnerStore } from '@/stores/partner-store';
import { useTheme } from 'next-themes';
import { toast } from 'sonner';
import type { PartnerPage } from '@/types/partner';

interface CommandItem {
  label: string;
  page?: PartnerPage;
  action?: () => void;
  icon: React.ComponentType<{ className?: string }>;
  category: string;
}

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const navigate = usePartnerStore((s) => s.navigate);
  const authStatus = usePartnerStore((s) => s.authStatus);
  const { resolvedTheme, setTheme } = useTheme();

  const isDark = resolvedTheme === 'dark';
  const isDashboard = authStatus === 'authenticated';

  const items: CommandItem[] = isDashboard
    ? [
        { label: 'Overview', page: 'dashboard', icon: LayoutDashboard, category: 'Navigation' },
        { label: 'Referrals', page: 'referrals', icon: Users, category: 'Navigation' },
        { label: 'Earnings', page: 'earnings', icon: DollarSign, category: 'Navigation' },
        { label: 'Payouts', page: 'payouts', icon: Wallet, category: 'Navigation' },
        { label: 'Settings', page: 'settings', icon: Settings, category: 'Navigation' },
        { label: 'Contact Support', page: 'support', icon: MessageSquare, category: 'Actions' },
        { label: 'Toggle theme', action: () => setTheme(isDark ? 'light' : 'dark'), icon: isDark ? Sun : Moon, category: 'Actions' },
        { label: 'Sign out', action: () => { setOpen(false); usePartnerStore.getState().reset(); navigate('home'); toast.success('Signed out'); }, icon: LogOut, category: 'Actions' },
      ]
    : [
        { label: 'Home', page: 'home', icon: Home, category: 'Navigation' },
        { label: 'How It Works', page: 'how-it-works', icon: BookOpen, category: 'Navigation' },
        { label: 'Commission', page: 'commission', icon: DollarSign, category: 'Navigation' },
        { label: 'Earn', page: 'earn', icon: DollarSign, category: 'Navigation' },
        { label: 'Resources', page: 'resources', icon: FileText, category: 'Navigation' },
        { label: 'FAQ', page: 'faq', icon: HelpCircle, category: 'Navigation' },
        { label: 'Tiers', page: 'tiers', icon: Crown, category: 'Navigation' },
        { label: 'Premium', page: 'premium', icon: Crown, category: 'Navigation' },
        { label: 'Support', page: 'support', icon: MessageSquare, category: 'Navigation' },
        { label: 'Log in', page: 'login', icon: Users, category: 'Account' },
        { label: 'Sign up', page: 'signup', icon: Users, category: 'Account' },
        { label: 'Apply', page: 'apply', icon: FileText, category: 'Account' },
        { label: 'Privacy Policy', page: 'privacy', icon: FileText, category: 'Legal' },
        { label: 'Terms of Service', page: 'terms', icon: FileText, category: 'Legal' },
        { label: 'Toggle theme', action: () => setTheme(isDark ? 'light' : 'dark'), icon: isDark ? Sun : Moon, category: 'Actions' },
      ];

  const filtered = query
    ? items.filter((item) => item.label.toLowerCase().includes(query.toLowerCase()))
    : items;

  const grouped = filtered.reduce<Record<string, CommandItem[]>>((acc, item) => {
    if (!acc[item.category]) acc[item.category] = [];
    acc[item.category].push(item);
    return acc;
  }, {});

  const flatFiltered = Object.values(grouped).flat();

  const executeItem = useCallback(
    (item: CommandItem) => {
      setOpen(false);
      setQuery('');
      if (item.action) {
        item.action();
      } else if (item.page) {
        navigate(item.page);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }
    },
    [navigate]
  );

  // Keyboard shortcut
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
      if (e.key === 'Escape') {
        setOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Reset selection when query changes

  // Keyboard navigation inside palette
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((prev) => Math.min(prev + 1, flatFiltered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((prev) => Math.max(prev - 1, 0));
    } else if (e.key === 'Enter' && flatFiltered[selectedIndex]) {
      e.preventDefault();
      executeItem(flatFiltered[selectedIndex]);
    }
  };

  return (
    <>
      {/* Backdrop */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="fixed inset-0 z-[100] bg-black/40 backdrop-blur-sm"
            onClick={() => { setOpen(false); setQuery(''); }}
          />
        )}
      </AnimatePresence>

      {/* Palette */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, scale: 0.96, y: -8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: -8 }}
            transition={{ duration: 0.2, ease: [0.25, 0.1, 0.25, 1] }}
            className="fixed left-1/2 top-[15%] z-[101] w-full max-w-lg -translate-x-1/2 rounded-xl border border-border/60 bg-background shadow-2xl overflow-hidden"
          >
            {/* Search input */}
            <div className="flex items-center gap-3 border-b border-border/40 px-4">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 text-muted-foreground">
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
              <input
                type="text"
                value={query}
                onChange={(e) => { setQuery(e.target.value); setSelectedIndex(0); }}
                onKeyDown={handleKeyDown}
                placeholder="Search pages..."
                className="flex-1 bg-transparent py-3.5 text-sm outline-none placeholder:text-muted-foreground/60"
                autoFocus
              />
              <kbd className="hidden sm:inline-flex items-center gap-0.5 rounded border border-border/60 bg-muted/60 px-1.5 py-0.5 text-[10px] font-mono text-muted-foreground">
                ESC
              </kbd>
            </div>

            {/* Results */}
            <div className="max-h-72 overflow-y-auto py-2">
              {flatFiltered.length === 0 ? (
                <div className="px-4 py-8 text-center">
                  <p className="text-sm text-muted-foreground">No results found.</p>
                </div>
              ) : (
                Object.entries(grouped).map(([category, categoryItems]) => (
                  <div key={category}>
                    <p className="px-4 pt-2 pb-1 text-[10px] font-mono uppercase tracking-widest text-muted-foreground/60">
                      {category}
                    </p>
                    {categoryItems.map((item) => {
                      const globalIndex = flatFiltered.indexOf(item);
                      const Icon = item.icon;
                      const isSelected = globalIndex === selectedIndex;
                      return (
                        <button
                          key={item.label}
                          onClick={() => executeItem(item)}
                          onMouseEnter={() => setSelectedIndex(globalIndex)}
                          className={`w-full flex items-center gap-3 px-4 py-2 text-sm text-left transition-colors ${
                            isSelected
                              ? 'bg-muted/60 text-foreground'
                              : 'text-muted-foreground hover:text-foreground'
                          }`}
                        >
                          <Icon className="size-4 shrink-0" />
                          <span>{item.label}</span>
                        </button>
                      );
                    })}
                  </div>
                ))
              )}
            </div>

            {/* Footer hint */}
            <div className="flex items-center gap-3 border-t border-border/40 px-4 py-2.5">
              <div className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground/50">
                <kbd className="rounded border border-border/40 bg-muted/40 px-1 py-0.5 text-[9px]">↑↓</kbd>
                <span>navigate</span>
              </div>
              <div className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground/50">
                <kbd className="rounded border border-border/40 bg-muted/40 px-1 py-0.5 text-[9px]">↵</kbd>
                <span>select</span>
              </div>
              <div className="ml-auto flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground/50">
                <kbd className="rounded border border-border/40 bg-muted/40 px-1 py-0.5 text-[9px]">⌘K</kbd>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
