'use client';

import { motion } from 'framer-motion';
import { usePartnerStore } from '@/stores/partner-store';

const sectionFade = {
  hidden: { opacity: 0, y: 20 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.06, duration: 0.5, ease: [0.25, 0.1, 0.25, 1] },
  }),
};

interface TermSection {
  heading: string;
  body: string[];
}

const terms: TermSection[] = [
  {
    heading: '1. Acceptance of Terms',
    body: [
      'By accessing or using the RELIASTRA Partner Network (the "Program"), you agree to be bound by these Terms of Service ("Terms"), which constitute a legally binding agreement between you ("Partner" or "you") and RELIASTRA Inc. ("RELIASTRA," "we," or "us").',
      'If you do not agree to these Terms, you may not participate in the Program or use any associated services, tools, or materials provided by RELIASTRA.',
      'These Terms apply to your participation in the Program, including but not limited to the use of referral links, the partner dashboard, marketing materials, and any commission or payout processes. RELIASTRA reserves the right to update these Terms at any time as described in Section 11.',
      'Your continued participation in the Program following any modification constitutes acceptance of the revised Terms.',
    ],
  },
  {
    heading: '2. The Partner Program',
    body: [
      'The RELIASTRA Partner Network is a referral-based commission program designed for qualified professionals, agencies, and organizations that wish to promote RELIASTRA’s platform and earn recurring revenue from successful referrals.',
      'Approved partners earn a flat commission of 30% of the monthly subscription fee paid by each referred customer. This commission is recurring in nature—you continue to earn as long as the referred customer maintains an active subscription with RELIASTRA.',
      'The commission applies to all subscription tiers offered by RELIASTRA. There is no cap on total earnings; your revenue scales directly with the number and size of your active referrals.',
      'RELIASTRA provides partners with a referral link, a partner dashboard for tracking referrals and commissions, and select marketing resources to support promotional efforts.',
    ],
  },
  {
    heading: '3. Partner Eligibility & Application',
    body: [
      'The Program is open to individuals and entities who meet the following criteria: you must be at least 18 years of age (or the legal age of majority in your jurisdiction), have the legal capacity to enter into binding agreements, and not be prohibited from participating under applicable law.',
      'To join the Program, you must submit a partner application through the RELIASTRA Partner Network website. All applications are subject to review by RELIASTRA. We reserve the right to approve or reject any application at our sole discretion, with or without cause.',
      'RELIASTRA may consider factors including but not limited to: the nature of your business or professional activities, your audience and reach, alignment with RELIASTRA’s brand values, and compliance history with prior programs or agreements.',
      'You agree to provide accurate and complete information during the application process. Misrepresentation of any material fact may result in immediate rejection or termination.',
    ],
  },
  {
    heading: '4. Referral Process & Tracking',
    body: [
      'Upon approval, each partner is issued a unique referral link. This link is the sole authorized method for tracking and attributing referrals. Manual attribution requests, including name-based or email-based referrals, are not supported.',
      'When a prospective customer clicks your referral link, a tracking cookie is placed on their device. This cookie remains active for 90 days. If the user creates a RELIASTRA account and subscribes to a paid plan within the 90-day window, the referral is attributed to your partner account.',
      'Self-referrals are strictly prohibited. You may not use your own referral link to create a RELIASTRA account or subscription for yourself, your immediate family members, or any entity you directly or indirectly control.',
      'RELIASTRA uses industry-standard tracking methods. In the event of a tracking dispute, RELIASTRA’s records shall be considered final and binding. Cookie clearing, use of ad-blocking software, or browser privacy settings by the referred user may affect tracking and is not the responsibility of RELIASTRA.',
    ],
  },
  {
    heading: '5. Commissions',
    body: [
      'Approved partners earn a commission equal to 30% of the monthly subscription fee paid by each referred customer. The commission is calculated based on the actual amount collected by RELIASTRA from the customer, after any applicable discounts or promotions.',
      'A commission is earned when a referred customer completes a paid subscription to a RELIASTRA plan. Commissions on recurring subscriptions continue for each billing cycle in which the customer remains active.',
      'Each commission progresses through three states: Pending (the referral has subscribed but the initial payment has not yet been fully processed), Payable (the commission has been verified and is queued for the next payout cycle), and Paid (the commission has been disbursed to your designated payout method).',
      'There is no maximum cap on commissions. You may earn unlimited commissions from an unlimited number of referrals, subject to these Terms and the continued active status of referred subscriptions.',
      'If a referred customer cancels their subscription, commissions for that customer cease accruing from the cancellation date forward. Previously paid commissions are not subject to clawback or recovery by RELIASTRA.',
    ],
  },
  {
    heading: '6. Payouts',
    body: [
      'Commissions are accumulated on a monthly basis and are eligible for payout once the total payable balance reaches a minimum threshold of $50 USD. Balances below this threshold are carried forward to the following month until the threshold is met.',
      'Payouts are processed within the first 30 days following the end of each calendar month. The exact processing date may vary based on your selected payout method and any applicable banking or network processing times.',
      'Available payout methods include: bank transfer (ACH for US-based partners, international wire for non-US partners), USDC (Ethereum, Polygon, or Solana networks), and USDT (Ethereum, Tron, or BSC networks).',
      'You are responsible for providing accurate and current payout information. RELIASTRA is not liable for payouts sent to incorrect or outdated payment details. You may update your payout method at any time through the partner dashboard, though changes made close to a payout cycle may not take effect until the following cycle.',
      'Partners are solely responsible for any tax obligations arising from commissions received under this Program. RELIASTRA does not withhold taxes on commission payments. Depending on your jurisdiction, you may be required to provide tax identification information.',
    ],
  },
  {
    heading: '7. Partner Obligations',
    body: [
      'As a partner, you agree to represent RELIASTRA and its products accurately and in a professional manner. All promotional content must be truthful, non-misleading, and consistent with RELIASTRA’s current product descriptions and pricing.',
      'You may not bid on or purchase advertisements targeting RELIASTRA’s trademarked terms, trade names, or brand variations (including misspellings) on any search engine, social media platform, or advertising network. This includes pay-per-click, paid social, and any other form of keyword-targeted advertising.',
      'Spam, unsolicited communications, and deceptive marketing practices are strictly prohibited. You may not send commercial emails to individuals who have not provided prior consent, nor may you use automated tools or bots to distribute referral links in bulk.',
      'You must comply with all applicable local, state, national, and international laws, regulations, and industry standards in connection with your participation in the Program, including but not limited to advertising standards, privacy laws, and anti-spam legislation.',
      'RELIASTRA reserves the right to request review of your promotional materials and may require modifications if such materials are found to be inconsistent with these Terms or RELIASTRA’s brand guidelines.',
    ],
  },
  {
    heading: '8. Intellectual Property',
    body: [
      'RELIASTRA grants you a limited, non-exclusive, non-transferable, revocable license to use the RELIASTRA name, logos, trademarks, and other brand materials (collectively, "Marks") solely for the purpose of promoting RELIASTRA and the Partner Program in accordance with these Terms.',
      'This license is conditioned upon your continued compliance with the Program’s brand guidelines and these Terms. You may not modify, alter, or create derivative works of the Marks without prior written consent from RELIASTRA.',
      'Your referral link is provided for your exclusive use and may not be sold, transferred, or sublicensed to any third party. The referral link must be used in its original, unmodified form as provided by RELIASTRA.',
      'All intellectual property rights in the RELIASTRA platform, its products, and its brand materials remain the sole and exclusive property of RELIASTRA. No ownership or intellectual property rights are transferred to you under these Terms.',
    ],
  },
  {
    heading: '9. Termination',
    body: [
      'Either party may terminate this agreement at any time, with or without cause. You may terminate your participation by contacting RELIASTRA or by deactivating your partner account through the dashboard.',
      'RELIASTRA reserves the right to terminate your participation immediately and without prior notice if you materially breach these Terms, engage in fraudulent or abusive activity, or otherwise act in a manner that is detrimental to RELIASTRA’s reputation or business interests.',
      'Upon termination, your referral link will be deactivated and you will no longer be eligible to earn new commissions. Pending commissions that have not yet reached the Payable state at the time of termination will be forfeited.',
      'Commissions that have already reached the Payable or Paid state at the time of termination will be processed and disbursed according to the normal payout schedule, subject to RELIASTRA’s right to withhold or recover any commissions arising from fraudulent or prohibited activity.',
      'Provisions of these Terms that by their nature should survive termination—including but not limited to intellectual property licenses, limitation of liability, and governing law—shall remain in effect following any termination.',
    ],
  },
  {
    heading: '10. Limitation of Liability',
    body: [
      'To the maximum extent permitted by applicable law, RELIASTRA and its officers, directors, employees, agents, and affiliates shall not be liable for any indirect, incidental, special, consequential, or punitive damages arising out of or in connection with your participation in the Program, regardless of the legal theory under which such damages are sought.',
      'RELIASTRA’s total aggregate liability under these Terms shall not exceed the total commissions actually paid to you during the twelve (12) months immediately preceding the event giving rise to the claim.',
      'RELIASTRA does not warrant that the Program will be uninterrupted, error-free, or free of viruses or other harmful components. The partner dashboard, referral tracking, and all associated tools are provided “as is” without warranties of any kind, either express or implied.',
      'RELIASTRA shall not be liable for any loss of commissions, referrals, or data resulting from technical failures, tracking errors, browser settings, third-party interference, or any other cause beyond RELIASTRA’s reasonable control.',
    ],
  },
  {
    heading: '11. Modifications to Terms',
    body: [
      'RELIASTRA reserves the right to modify, amend, or update these Terms at any time at its sole discretion. When material changes are made, RELIASTRA will notify partners by posting the updated Terms on the RELIASTRA Partner Network website and, where appropriate, by email.',
      'The “Last updated” date at the top of this page indicates when the Terms were last revised. Continued use of the Program after the effective date of any modification constitutes your acceptance of the revised Terms.',
      'If you do not agree with any modification to these Terms, your sole remedy is to terminate your participation in the Program as described in Section 9.',
    ],
  },
  {
    heading: '12. Governing Law',
    body: [
      'These Terms shall be governed by and construed in accordance with the laws of the State of Delaware, United States of America, without regard to its conflict of law principles.',
      'Any disputes arising out of or in connection with these Terms shall be resolved in the state or federal courts located in Delaware. You consent to the personal jurisdiction and venue of such courts and waive any objection to the inconvenience of such forum.',
      'Before initiating any legal proceedings, you agree to attempt to resolve any dispute informally by contacting RELIASTRA at support@reliastra.com. RELIASTRA will attempt to respond to your inquiry within thirty (30) days.',
    ],
  },
  {
    heading: '13. Contact',
    body: [
      'For questions, concerns, or notices related to these Terms of Service or the RELIASTRA Partner Network, please contact us at: RELIASTRA Inc. — Email: support@reliastra.com',
      'We recommend reviewing these Terms periodically to stay informed of any updates. Your participation in the Program is valued, and we are committed to maintaining a transparent and mutually beneficial partnership.',
    ],
  },
];

export function PageTerms() {
  const navigate = usePartnerStore((s) => s.navigate);

  return (
    <div>
      {/* Header */}
      <section className="border-b border-border/40">
        <div className="mx-auto max-w-3xl px-4 pb-12 pt-20 sm:px-6 sm:pb-16 sm:pt-28">
          <motion.div
            initial="hidden"
            animate="visible"
          >
            <motion.button
              variants={sectionFade}
              custom={0}
              onClick={() => navigate('home')}
              className="mb-8 font-mono text-xs uppercase tracking-widest text-muted-foreground transition-colors hover:text-foreground"
            >
              ← Back to Partner Network
            </motion.button>
            <motion.p
              variants={sectionFade}
              custom={1}
              className="mb-3 font-mono text-xs uppercase tracking-widest text-muted-foreground"
            >
              LEGAL
            </motion.p>
            <motion.h1
              variants={sectionFade}
              custom={2}
              className="text-3xl font-semibold tracking-tight text-foreground md:text-4xl"
            >
              Terms of Service
            </motion.h1>
            <motion.p
              variants={sectionFade}
              custom={3}
              className="mt-3 text-sm text-muted-foreground"
            >
              Last updated: August 2026
            </motion.p>
          </motion.div>
        </div>
      </section>

      {/* Terms content */}
      <section className="mx-auto max-w-3xl px-4 py-12 sm:px-6 sm:py-16">
        <div className="space-y-0">
          {terms.map((section, si) => (
            <motion.div
              key={section.heading}
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true, margin: '-60px' }}
              className="border-b border-border/40 pb-10 pt-10 first:pt-0"
            >
              <motion.h2
                variants={sectionFade}
                custom={0}
                className="mb-4 text-sm font-semibold uppercase tracking-wider text-foreground"
              >
                {section.heading}
              </motion.h2>
              <div className="space-y-4">
                {section.body.map((paragraph, pi) => (
                  <motion.p
                    key={pi}
                    variants={sectionFade}
                    custom={pi + 1}
                    className="text-sm leading-relaxed text-muted-foreground"
                  >
                    {paragraph}
                  </motion.p>
                ))}
              </div>
            </motion.div>
          ))}
        </div>
      </section>
    </div>
  );
}
