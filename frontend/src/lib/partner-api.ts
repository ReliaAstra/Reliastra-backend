import type {
  LoginRequest,
  RegisterRequest,
  TokenResponse,
  RegisterResponse,
  PartnerProfileResponse,
  PartnerDashboardResponse,
  ReferralListResponse,
  CommissionListResponse,
  PayoutListResponse,
  ForgotPasswordRequest,
  PartnerApplyRequest,
  Partner,
} from '@/types/partner';

const API_BASE = '/api';

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const token =
    typeof window !== 'undefined'
      ? localStorage.getItem('partner_access_token')
      : null;

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options?.headers as Record<string, string>),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (res.status === 401) {
    // Clear tokens and redirect to login
    if (typeof window !== 'undefined') {
      localStorage.removeItem('partner_access_token');
      localStorage.removeItem('partner_refresh_token');
    }
    throw new Error('UNAUTHORIZED');
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: 'Request failed' }));
    const msg = body?.error?.message || body?.error || `Request failed with status ${res.status}`;
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }

  return res.json();
}

export const partnerApi = {
  // ── Auth ─────────────────────────────────────

  async login(data: LoginRequest) {
    return request<TokenResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async signup(data: RegisterRequest) {
    return request<RegisterResponse>('/auth/signup', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async me() {
    // Real backend returns UserResponse (snake_case) directly, not wrapped
    return request<{
      id: string;
      email: string;
      full_name?: string;
      is_active?: boolean;
      is_superuser?: boolean;
      avatar_url?: string;
      auth_provider?: string;
      created_at?: string;
      updated_at?: string;
    }>('/auth/me');
  },

  async forgotPassword(data: ForgotPasswordRequest) {
    return request<{ message: string }>('/auth/forgot-password', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async resetPassword(data: { token: string; new_password: string }) {
    return request<{ message: string }>('/auth/reset-password', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  // ── Partner ──────────────────────────────────

  async apply(data: PartnerApplyRequest) {
    return request<PartnerProfileResponse>('/partners/apply', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async getMe(): Promise<Partner> {
    const res = await request<PartnerProfileResponse>('/partners/me');
    return {
      partnerId: res.partner_id,
      referralCode: res.referral_code,
      referralLink: res.referral_link,
      commissionRate: res.commission_rate,
      status: res.status,
      createdAt: res.created_at,
    };
  },

  async getDashboard() {
    return request<PartnerDashboardResponse>('/partners/dashboard');
  },

  async getReferrals(page = 1, pageSize = 20) {
    return request<ReferralListResponse>(`/partners/referrals?page=${page}&page_size=${pageSize}`);
  },

  async getCommissions(page = 1, pageSize = 20) {
    return request<CommissionListResponse>(`/partners/commissions?page=${page}&page_size=${pageSize}`);
  },

  async getPayouts(page = 1, pageSize = 20) {
    return request<PayoutListResponse>(`/partners/payouts?page=${page}&page_size=${pageSize}`);
  },

  async requestPayout() {
    return request<{ success: boolean }>('/partners/payouts/request', {
      method: 'POST',
    });
  },

  // ── Support ──────────────────────────────────

  async submitSupport(data: { name: string; email: string; subject: string; message: string }) {
    return request<{ success: boolean }>('/support', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },
};
