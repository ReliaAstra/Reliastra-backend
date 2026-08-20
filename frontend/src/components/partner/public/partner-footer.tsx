'use client';

import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';
import { ReliastraLogo } from '../shared/reliastra-logo';
import { usePartnerStore } from '@/stores/partner-store';
import type { PartnerPage } from '@/types/partner';

const footerSections = [
  {
    heading: 'Program',
    links: [
      { label: 'Overview', page: 'home' as PartnerPage },
      { label: 'How It Works', page: 'how-it-works' as PartnerPage },
      { label: 'Commission', page: 'commission' as PartnerPage },
      { label: 'Earn', page: 'earn' as PartnerPage },
      { label: 'Resources', page: 'resources' as PartnerPage },
      { label: 'Premium', page: 'premium' as PartnerPage },
      { label: 'FAQ', page: 'faq' as PartnerPage },
      { label: 'Tiers', page: 'tiers' as PartnerPage },
    ],
  },
  {
    heading: 'Account',
    links: [
      { label: 'Apply', page: 'apply' as PartnerPage },
      { label: 'Log in', page: 'login' as PartnerPage },
      { label: 'Sign up', page: 'signup' as PartnerPage },
    ],
  },
  {
    heading: 'Legal',
    links: [
      { label: 'Privacy', page: 'privacy' as PartnerPage },
      { label: 'Terms', page: 'terms' as PartnerPage },
    ],
  },
];

function FooterLink({ label, page }: { label: string; page: PartnerPage }) {
  const navigate = usePartnerStore((s) => s.navigate);

  return (
    <motion.button
      onClick={() => {
        navigate(page);
        window.scrollTo({ top: 0, behavior: 'smooth' });
      }}
      whileHover={{ x: 2 }}
      transition={{ duration: 0.2, ease: [0.25, 0.1, 0.25, 1] }}
      className="text-sm text-muted-foreground underline-offset-4 transition-colors hover:text-foreground hover:underline"
    >
      {label}
    </motion.button>
  );
}

export function PartnerFooter() {
  const navigate = usePartnerStore((s) => s.navigate);

  const handleLinkClick = (page: PartnerPage) => {
    navigate(page);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <footer className="mt-auto border-t border-border/60 bg-background">
      {/* Gradient top line */}
      <div className="h-px w-full bg-gradient-to-r from-transparent via-border to-transparent" />

      <div className="mx-auto max-w-6xl px-4 py-12 sm:px-6 lg:px-8">
        <div className="grid grid-cols-2 gap-10 sm:grid-cols-2 lg:grid-cols-4">
          {/* Brand column */}
          <div className="col-span-2 sm:col-span-2 lg:col-span-1">
            <button
              onClick={() => handleLinkClick('home')}
              className="mb-4 flex items-center transition-opacity hover:opacity-70"
            >
              <ReliastraLogo size="sm" />
            </button>
            <p className="max-w-xs text-sm leading-relaxed text-muted-foreground">
              A premium partnership program for consultants, agencies, and
              technology advisors. Turn your infrastructure expertise into
              recurring revenue with RELIASTRA.
            </p>
            <motion.button
              onClick={() => handleLinkClick('resources')}
              whileHover={{ x: 2 }}
              transition={{ duration: 0.2, ease: [0.25, 0.1, 0.25, 1] }}
              className="mt-4 inline-block text-xs font-medium text-muted-foreground underline-offset-4 transition-colors hover:text-foreground hover:underline"
            >
              Resources →
            </motion.button>
          </div>

          {/* Link columns */}
          {footerSections.map((section) => (
            <div key={section.heading}>
              <h4 className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {section.heading}
              </h4>
              <ul className="space-y-2.5">
                {section.links.map((link) => (
                  <li key={`${section.heading}-${link.label}`}>
                    <FooterLink label={link.label} page={link.page} />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        {/* Thin separator */}
        <div className="my-8 h-px w-full bg-border/40" />

        {/* Bottom bar */}
        <div className="flex flex-col items-center justify-between gap-4 sm:flex-row">
          <p className="text-xs text-muted-foreground">
            © {new Date().getFullYear()} RELIASTRA. All rights reserved.
          </p>
          <div className="flex items-center gap-5">
            {/* Social links */}
            <div className="flex items-center gap-3">
              <a
                href="https://twitter.com/reliastro"
                target="_blank"
                rel="noopener noreferrer"
                className="text-muted-foreground/50 transition-colors hover:text-foreground"
                aria-label="Twitter / X"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/></svg>
              </a>
              <a
                href="https://github.com/reliastro"
                target="_blank"
                rel="noopener noreferrer"
                className="text-muted-foreground/50 transition-colors hover:text-foreground"
                aria-label="GitHub"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/></svg>
              </a>
              <a
                href="https://linkedin.com/company/reliastro"
                target="_blank"
                rel="noopener noreferrer"
                className="text-muted-foreground/50 transition-colors hover:text-foreground"
                aria-label="LinkedIn"
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/></svg>
              </a>
            </div>
            <span className="font-mono text-[10px] uppercase tracking-widest text-muted-foreground/40">
              v1.1
            </span>
          </div>
        </div>
      </div>
    </footer>
  );
}
