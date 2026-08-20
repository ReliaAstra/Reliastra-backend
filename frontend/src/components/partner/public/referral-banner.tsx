'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Link2 } from 'lucide-react';

const REFERRAL_COOKIE = 'ra_ref';
const REFERRAL_COOKIE_DAYS = 90;

function getReferralFromUrl(): string | null {
  if (typeof window === 'undefined') return null;
  const params = new URLSearchParams(window.location.search);
  return params.get('ref');
}

function setReferralCookie(code: string) {
  const expires = new Date();
  expires.setDate(expires.getDate() + REFERRAL_COOKIE_DAYS);
  document.cookie = `${REFERRAL_COOKIE}=${encodeURIComponent(code)};expires=${expires.toUTCString()};path=/;SameSite=Lax`;
}

function getReferralCookie(): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${REFERRAL_COOKIE}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

// Detect referral on initial render (lazy initializer)
function detectInitialReferral(): { code: string | null; showBanner: boolean } {
  if (typeof window === 'undefined') return { code: null, showBanner: false };

  const urlRef = getReferralFromUrl();
  if (urlRef) {
    setReferralCookie(urlRef);
    return { code: urlRef, showBanner: true };
  }

  const cookie = getReferralCookie();
  return { code: cookie, showBanner: false };
}

export function ReferralBanner() {
  const [dismissed, setDismissed] = useState(false);
  const [refCode, setRefCode] = useState<string | null>(null);
  const [showBanner, setShowBanner] = useState(false);

  // Use lazy initializer to detect referral without an effect
  const [initial] = useState(detectInitialReferral);

  // Sync initial detection to state on first render
  if (initial.code && !refCode) {
    setRefCode(initial.code);
    setShowBanner(initial.showBanner);
  }

  if (dismissed || !showBanner || !refCode) return null;

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -4 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -4 }}
        transition={{ duration: 0.3, ease: [0.25, 0.1, 0.25, 1] }}
        className="border-b border-border/60 bg-muted/40"
      >
        <div className="mx-auto max-w-6xl px-4 py-2.5 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-background border border-border/60">
                <Link2 className="size-3 text-muted-foreground" />
              </div>
              <p className="text-sm text-muted-foreground truncate">
                You were referred by a partner.{' '}
                <span className="font-mono text-xs text-foreground">{refCode}</span>
              </p>
            </div>
            <button
              onClick={() => setDismissed(true)}
              className="shrink-0 rounded p-1 text-muted-foreground transition-colors hover:text-foreground"
              aria-label="Dismiss"
            >
              <X className="size-3.5" />
            </button>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}

// Export utility for reading referral code in signup/apply flows
export function getStoredReferralCode(): string | null {
  return getReferralCookie();
}
