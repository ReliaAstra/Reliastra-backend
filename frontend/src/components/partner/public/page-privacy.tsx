'use client';

import { motion } from 'framer-motion';
import { usePartnerStore } from '@/stores/partner-store';

const fadeUp = {
  hidden: { opacity: 0, y: 16 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.08, duration: 0.5, ease: [0.25, 0.1, 0.25, 1] },
  }),
};

const sectionReveal = {
  hidden: { opacity: 0, y: 12 },
  visible: (i: number) => ({
    opacity: 1,
    y: 0,
    transition: { delay: i * 0.06, duration: 0.45, ease: [0.25, 0.1, 0.25, 1] },
  }),
};

interface PolicySection {
  heading: string;
  paragraphs: string[];
}

const sections: PolicySection[] = [
  {
    heading: '1. Information We Collect',
    paragraphs: [
      'We collect information that you provide directly when you interact with the RELIASTRA Partner Network. This includes your name, email address, company or organization name, billing details, and any other information you choose to provide during the application process or while using the partner dashboard.',
      'We automatically collect certain usage data when you access our platform. This includes IP address, browser type and version, operating system, referring URLs, pages viewed, links clicked, and the date and time of your interactions. This data helps us understand how partners use our platform and improve the experience accordingly.',
      'We use cookies and similar tracking technologies to maintain your session, remember your preferences, and support referral attribution. When a visitor arrives through your unique referral link, a cookie is placed on their device to track the referral for the attribution window (currently 90 days). See Section 6 for full details on our cookie practices.',
      'For the purpose of commission tracking, we collect referral data including the referral code used, the date and time of the referral click, the referred customer\'s sign-up and subscription status, and any subsequent commission events tied to your partner account.',
    ],
  },
  {
    heading: '2. How We Use Your Information',
    paragraphs: [
      'We use the information we collect to operate and improve the RELIASTRA Partner Network. Specifically, we process your data to evaluate and manage partner applications, provide access to the partner dashboard and referral tools, track and attribute referrals, calculate and process commission payments, and communicate with you about your account, earnings, and program updates.',
      'Your personal information is used to verify your identity, comply with know-your-customer requirements for payout processing, prevent fraud and abuse of the referral program, and ensure the integrity of our commission tracking system.',
      'We may use aggregate, anonymized usage data to analyze platform performance, identify trends, and make improvements to the partner experience. This data cannot be used to identify you personally.',
      'With your consent where required, we may send you communications about new features, program changes, partner events, or promotional materials that we believe may be relevant to your partnership with RELIASTRA.',
    ],
  },
  {
    heading: '3. Information Sharing',
    paragraphs: [
      'RELIASTRA does not sell, rent, or trade your personal information to third parties for their marketing purposes. We do not participate in data brokerages or advertising networks that monetize user data.',
      'We share your information with carefully selected service providers who assist us in operating the partner program. These include payment processors for commission payouts, cloud infrastructure providers for hosting our platform, email service providers for transactional communications, and analytics providers for understanding platform usage. All service providers are contractually obligated to protect your data and use it only for the purposes we specify.',
      'We may disclose your information when required by law, regulation, or legal process. This includes responding to valid subpoenas, court orders, or government requests. We may also disclose information to protect the rights, property, or safety of RELIASTRA, our partners, or the public, including to detect, prevent, or address fraud, security issues, or violations of our terms of service.',
      'In the event of a merger, acquisition, reorganization, or sale of assets, your information may be transferred as part of that transaction. We will notify you via email of any change in ownership or uses of your personal information.',
    ],
  },
  {
    heading: '4. Data Security',
    paragraphs: [
      'We implement industry-standard security measures to protect your personal information. All data transmissions between your browser and our servers are encrypted using TLS 1.2 or higher. Sensitive data at rest, including payment and authentication credentials, is encrypted using AES-256 encryption.',
      'Our infrastructure is hosted on secure, SOC 2 Type II certified cloud providers with robust physical security, network firewalls, intrusion detection systems, and continuous monitoring. Access to production systems is restricted to authorized personnel through multi-factor authentication and least-privilege access controls.',
      'We conduct regular security assessments, including automated vulnerability scanning and periodic penetration testing, to identify and address potential security risks. All code changes go through peer review and automated testing before deployment.',
      'Despite our best efforts, no method of electronic transmission or storage is completely secure. We cannot guarantee absolute security. If you become aware of any security vulnerability or unauthorized access to your account, please contact us immediately at support@reliastra.com.',
    ],
  },
  {
    heading: '5. Your Rights',
    paragraphs: [
      'You have the right to access the personal information we hold about you. You can review most of your data directly through the partner dashboard. For a complete copy of your personal data, submit a request to support@reliastra.com and we will provide it within 30 days.',
      'You have the right to request correction of any inaccurate or incomplete personal information. You can update most details directly in your partner dashboard settings. For changes that require our assistance, contact our support team.',
      'You have the right to request deletion of your personal information, subject to certain exceptions. We may retain information as required by law, for legitimate business purposes (such as fraud prevention), or to complete pending commission calculations and payouts. Upon account closure, your active referrals and commission records are preserved for a minimum of 7 years for tax and compliance purposes.',
      'Where technically feasible, you have the right to request portability of your data in a structured, machine-readable format. Contact support@reliastra.com to make such a request.',
      'You have the right to withdraw consent for any data processing based on your consent at any time. Note that withdrawing consent may affect your ability to participate in the partner program. You also have the right to lodge a complaint with a supervisory data protection authority in your jurisdiction.',
    ],
  },
  {
    heading: '6. Cookies & Tracking',
    paragraphs: [
      'Essential cookies are used to maintain your authenticated session, store your preferences, and ensure the security of your account. These cookies are strictly necessary for the platform to function and cannot be disabled without affecting core functionality.',
      'Analytics cookies help us understand how partners and visitors interact with our platform. We use this data to improve navigation, identify usability issues, and optimize the overall experience. All analytics data is aggregated and anonymized; we do not use analytics cookies to build individual user profiles.',
      'Referral attribution cookies are set when a visitor arrives via a partner\'s unique referral link. These cookies store the partner\'s referral code and the timestamp of the visit. The cookie duration is 90 days, meaning if the visitor signs up within 90 days of their first click, the referral is attributed to the corresponding partner. If a visitor clicks multiple partner links, only the most recent partner is credited.',
      'You can manage your cookie preferences through your browser settings. However, disabling essential cookies will prevent you from using the partner dashboard. Disabling referral cookies may result in lost attribution for your referrals.',
    ],
  },
  {
    heading: '7. Data Retention',
    paragraphs: [
      'We retain your personal information for as long as your partner account is active or as needed to provide you with the partner program services. This includes the duration of your active referrals and any pending commission payments.',
      'When you close your account or your partnership is terminated, we retain your data for a minimum of 7 years for tax reporting, audit, and regulatory compliance purposes. This includes commission records, payout history, and referral attribution data.',
      'Usage logs and analytics data are retained for up to 24 months, after which they are aggregated into anonymized reports and the raw data is deleted. Cookie data expires according to the cookie duration set at the time of placement.',
      'You may request early deletion of non-essential data by contacting support@reliastra.com. We will assess the request and delete the data where legally and operationally permissible.',
    ],
  },
  {
    heading: '8. Children\'s Privacy',
    paragraphs: [
      'The RELIASTRA Partner Network is not directed at individuals under the age of 16. We do not knowingly collect personal information from children. If you are under 16, please do not use the platform or submit any personal information.',
      'If we become aware that we have inadvertently collected personal information from a child under 16, we will take immediate steps to delete that information from our systems. If you believe a child has provided us with personal information, please contact us at support@reliastra.com.',
    ],
  },
  {
    heading: '9. Changes to This Policy',
    paragraphs: [
      'We may update this Privacy Policy from time to time to reflect changes in our practices, technology, legal requirements, or other factors. When we make material changes, we will notify you by posting the updated policy on this page and, where appropriate, by sending you an email notification.',
      'The "Last updated" date at the top of this page indicates when the most recent revision was made. We encourage you to review this policy periodically to stay informed about how we protect your information.',
      'Your continued use of the RELIASTRA Partner Network after any changes to this Privacy Policy constitutes your acceptance of the revised terms.',
    ],
  },
  {
    heading: '10. Contact Us',
    paragraphs: [
      'If you have any questions, concerns, or requests regarding this Privacy Policy or our data practices, please contact us at:',
      'Email: support@reliastra.com',
      'We aim to respond to all privacy-related inquiries within 10 business days. For urgent security concerns, please include "URGENT: Privacy" in your email subject line.',
    ],
  },
];

export function PagePrivacy() {
  const navigate = usePartnerStore((s) => s.navigate);

  return (
    <div>
      {/* Top bar */}
      <div className="border-b border-border/40">
        <div className="mx-auto max-w-3xl px-4 pt-6 sm:px-6">
          <motion.button
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.3 }}
            onClick={() => navigate('home')}
            className="mb-8 text-xs font-mono uppercase tracking-widest text-muted-foreground transition-colors hover:text-foreground"
          >
            &larr; Back to Partner Network
          </motion.button>
        </div>
      </div>

      {/* Header */}
      <section className="border-b border-border/40">
        <div className="mx-auto max-w-3xl px-4 pb-12 pt-2 sm:px-6 sm:pb-16">
          <motion.div
            initial="hidden"
            animate="visible"
          >
            <motion.p
              variants={fadeUp}
              custom={0}
              className="font-mono text-xs uppercase tracking-widest text-muted-foreground"
            >
              LEGAL
            </motion.p>
            <motion.h1
              variants={fadeUp}
              custom={1}
              className="mt-3 text-3xl font-semibold tracking-tight text-foreground md:text-4xl"
            >
              Privacy Policy
            </motion.h1>
            <motion.p
              variants={fadeUp}
              custom={2}
              className="mt-3 text-sm text-muted-foreground"
            >
              Last updated: August 2026
            </motion.p>
          </motion.div>
        </div>
      </section>

      {/* Content sections */}
      <section className="mx-auto max-w-3xl px-4 py-12 sm:px-6 sm:py-16">
        <div>
          {sections.map((section, si) => (
            <motion.div
              key={section.heading}
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true, margin: '-40px' }}
              className="border-b border-border/40 pb-10 last:border-b-0 last:pb-0"
            >
              <motion.h2
                variants={sectionReveal}
                custom={0}
                className="mb-4 text-sm font-semibold uppercase tracking-wider text-foreground"
              >
                {section.heading}
              </motion.h2>
              {section.paragraphs.map((paragraph, pi) => (
                <motion.p
                  key={pi}
                  variants={sectionReveal}
                  custom={pi + 1}
                  className={`${pi > 0 ? 'mt-4' : ''} text-sm leading-relaxed text-muted-foreground`}
                >
                  {paragraph}
                </motion.p>
              ))}
            </motion.div>
          ))}
        </div>
      </section>
    </div>
  );
}
