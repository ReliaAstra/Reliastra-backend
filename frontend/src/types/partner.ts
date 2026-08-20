/* ─────────────────────────────────────────────
   Types aligned with Reliastra Backend OpenAPI 3.1
   https://reliastra-backend.zevcloud.app/docs
   ───────────────────────────────────────────── */

// ── Auth ───────────────────────────────────────

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  full_name: string;
  org_name?: string | null;
  ref_code?: string | null;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface UserResponseLite {
  id: string;
  email: string;
  full_name?: string;
  is_verified?: boolean;
  created_at?: string;
}

export interface OrganizationLite {
  id: string;
  name: string;
  slug?: string;
}

export interface RegisterResponse {
  user: UserResponseLite;
  organization: OrganizationLite;
  tokens: TokenResponse;
}

export interface ForgotPasswordRequest {
  email: string;
}

export interface ResetPasswordRequest {
  token: string;
  new_password: string;
}

export interface ResetPasswordResponse {
  message: string;
}

// ── Partner ────────────────────────────────────

export interface PartnerApplyRequest {
  agree_terms: boolean;
}

export interface PartnerProfileResponse {
  partner_id: string;
  referral_code: string;
  referral_link: string;
  commission_rate: number;
  status: string;
  created_at: string;
}

export interface PartnerDashboardResponse {
  referral_link: string;
  clicks: number;
  signups: number;
  active_paid_customers: number;
  monthly_commission_minor: number;
  pending_commission_minor: number;
  total_earned_minor: number;
  total_paid_minor: number;
  currency: string;
}

// ── Referrals ──────────────────────────────────

export interface ReferralItem {
  referral_id: string;
  status: string;
  plan: string | null;
  subscription_amount_minor: number;
  commission_rate: number;
  monthly_commission_minor: number;
  masked_email: string | null;
  organization_name: string | null;
  created_at: string;
  subscribed_at: string | null;
}

export interface ReferralListResponse {
  items: ReferralItem[];
  page: number;
  page_size: number;
  total: number;
}

// ── Commissions ────────────────────────────────

export interface CommissionItem {
  id: string;
  referral_id: string | null;
  period: string;
  subscription_amount_minor: number;
  commission_rate: number;
  commission_amount_minor: number;
  currency: string;
  status: string;
  created_at: string;
  payable_at: string | null;
  paid_at: string | null;
}

export interface CommissionListResponse {
  items: CommissionItem[];
  page: number;
  page_size: number;
  total: number;
}

// ── Payouts ────────────────────────────────────

export interface PayoutItem {
  id: string;
  period: string | null;
  amount_minor: number;
  currency: string;
  status: string;
  paid_at: string | null;
  transaction_reference: string | null;
}

export interface PayoutListResponse {
  items: PayoutItem[];
  page: number;
  page_size: number;
  total: number;
}

// ── Referral Program (user-facing) ─────────────

export interface ReferralInfoResponse {
  referral_code: string;
  referral_link: string;
  total_referrals: number;
  active_referrals: number;
  pending_rewards: Record<string, unknown>[];
  earned_rewards: Record<string, unknown>[];
  referral_tier: string;
  is_founding_referrer: boolean;
}

export interface ReferralResolveResponse {
  valid: boolean;
  referral_code: string | null;
  destination: string;
  visitor_id?: string | null;
}

// ── Internal convenience types (camelCase) ─────

export interface PartnerUser {
  id: string;
  email: string;
  fullName?: string;
  isVerified?: boolean;
  createdAt?: string;
}

export interface Partner {
  partnerId: string;
  referralCode: string;
  referralLink: string;
  commissionRate: number;
  status: string;
  createdAt: string;
}

// ── Tier System (frontend-only for marketing) ──

export type PartnerTier = 'bronze' | 'silver' | 'gold' | 'platinum';

export interface TierInfo {
  tier: PartnerTier;
  name: string;
  minReferrals: number;
  commissionRate: number;
  benefits: string[];
  color: string;
}

export const PARTNER_TIERS: TierInfo[] = [
  {
    tier: 'bronze',
    name: 'Bronze',
    minReferrals: 0,
    commissionRate: 30,
    benefits: [
      '30% recurring commission',
      'Standard 90-day attribution',
      'Email support',
      'Basic dashboard access',
      'Monthly payouts',
    ],
    color: 'amber',
  },
  {
    tier: 'silver',
    name: 'Silver',
    minReferrals: 10,
    commissionRate: 32,
    benefits: [
      '32% recurring commission',
      'Extended 120-day attribution',
      'Priority email support',
      'Advanced analytics',
      'Bi-weekly payouts',
      'Custom referral links',
    ],
    color: 'slate',
  },
  {
    tier: 'gold',
    name: 'Gold',
    commissionRate: 35,
    minReferrals: 25,
    benefits: [
      '35% recurring commission',
      '180-day attribution window',
      'Dedicated account manager',
      'Real-time analytics',
      'Weekly payouts',
      'Co-branded materials',
      'Early access to new features',
    ],
    color: 'yellow',
  },
  {
    tier: 'platinum',
    name: 'Platinum',
    commissionRate: 40,
    minReferrals: 50,
    benefits: [
      '40% recurring commission',
      'Lifetime attribution',
      '24/7 dedicated support',
      'Custom API access',
      'On-demand payouts',
      'White-label options',
      'Revenue sharing bonuses',
      'Executive partner events',
    ],
    color: 'zinc',
  },
];

export function getPartnerTier(activeReferrals: number): TierInfo {
  let current = PARTNER_TIERS[0];
  for (const tier of PARTNER_TIERS) {
    if (activeReferrals >= tier.minReferrals) current = tier;
  }
  return current;
}

export function getNextTier(activeReferrals: number): TierInfo | null {
  const current = getPartnerTier(activeReferrals);
  const currentIndex = PARTNER_TIERS.findIndex((t) => t.tier === current.tier);
  if (currentIndex < PARTNER_TIERS.length - 1) {
    return PARTNER_TIERS[currentIndex + 1];
  }
  return null;
}

// ── Page Routes ────────────────────────────────

export type PartnerPage =
  // Main site
  | 'landing'
  // Partner public pages
  | 'home'
  | 'earn'
  | 'how-it-works'
  | 'commission'
  | 'faq'
  | 'tiers'
  | 'resources'
  | 'apply'
  | 'login'
  | 'signup'
  | 'activation'
  | 'forgot-password'
  // Partner dashboard
  | 'dashboard'
  | 'referrals'
  | 'earnings'
  | 'payouts'
  | 'settings'
  // Misc
  | 'support'
  | 'privacy'
  | 'terms'
  | 'premium';
