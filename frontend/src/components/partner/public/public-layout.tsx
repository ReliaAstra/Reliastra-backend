'use client';

import { useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { usePartnerStore } from '@/stores/partner-store';
import type { PartnerPage } from '@/types/partner';
import { PartnerNav } from './partner-nav';
import { PartnerFooter } from './partner-footer';
import { PageHome } from './page-home';
import { PageEarn } from './page-earn';
import { PageHowItWorks } from './page-how-it-works';
import { PageCommission } from './page-commission';
import { PageFaq } from './page-faq';
import { PageTiers } from './page-tiers';
import { PageResources } from './page-resources';
import { PageApply } from './page-apply';
import { PageLogin } from './page-login';
import { PageSignup } from './page-signup';
import { PageActivation } from './page-activation';
import { PageSupport } from './page-support';
import { PageForgotPassword } from './page-forgot-password';
import { PagePrivacy } from './page-privacy';
import { PageTerms } from './page-terms';
import { PagePremium } from './page-premium';
import { ReferralBanner } from './referral-banner';
import { ScrollToTop } from '../shared/scroll-to-top';
import { CommandPalette } from '../shared/command-palette';

const publicPages: PartnerPage[] = [
  'home',
  'earn',
  'how-it-works',
  'commission',
  'faq',
  'tiers',
  'premium',
  'resources',
  'apply',
  'login',
  'signup',
  'activation',
  'support',
  'forgot-password',
  'privacy',
  'terms',
];

const pageVariants = {
  initial: { opacity: 0, y: 8 },
  animate: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.35, ease: [0.25, 0.1, 0.25, 1] },
  },
  exit: {
    opacity: 0,
    y: -8,
    transition: { duration: 0.2, ease: [0.25, 0.1, 0.25, 1] },
  },
};

function PageContent({ page }: { page: PartnerPage }) {
  switch (page) {
    case 'home':
      return <PageHome />;
    case 'earn':
      return <PageEarn />;
    case 'how-it-works':
      return <PageHowItWorks />;
    case 'commission':
      return <PageCommission />;
    case 'faq':
      return <PageFaq />;
    case 'tiers':
      return <PageTiers />;
    case 'resources':
      return <PageResources />;
    case 'apply':
      return <PageApply />;
    case 'login':
      return <PageLogin />;
    case 'signup':
      return <PageSignup />;
    case 'activation':
      return <PageActivation />;
    case 'support':
      return <PageSupport />;
    case 'forgot-password':
      return <PageForgotPassword />;
    case 'privacy':
      return <PagePrivacy />;
    case 'terms':
      return <PageTerms />;
    case 'premium':
      return <PagePremium />;
    default:
      return <PageHome />;
  }
}

export function PublicLayout() {
  const currentPage = usePartnerStore((s) => s.currentPage);
  const isPublicPage = publicPages.includes(currentPage);

  // Scroll to top on page change
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [currentPage]);

  if (!isPublicPage) {
    return null;
  }

  const isCenteredPage = currentPage === 'login' || currentPage === 'signup' || currentPage === 'activation' || currentPage === 'forgot-password';
  const isFooterHidden = currentPage === 'support' || isCenteredPage;

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <ReferralBanner />
      <PartnerNav />

      <main className="flex-1">
        <AnimatePresence mode="wait">
          <motion.div
            key={currentPage}
            variants={pageVariants}
            initial="initial"
            animate="animate"
            exit="exit"
            className={isCenteredPage || currentPage === 'support' ? 'flex flex-col py-12 sm:py-16' : ''}
          >
            <PageContent page={currentPage} />
          </motion.div>
        </AnimatePresence>
      </main>

      {!isFooterHidden && <PartnerFooter />}

      <ScrollToTop />
      <CommandPalette />
    </div>
  );
}
