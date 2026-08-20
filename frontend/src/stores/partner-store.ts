'use client';

import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type {
  PartnerUser,
  PartnerPage,
  PartnerDashboardResponse,
  ReferralItem,
  CommissionItem,
  PayoutItem,
  Partner,
} from '@/types/partner';

type PartnerAuthStatus = 'idle' | 'loading' | 'authenticated' | 'unauthenticated';

interface PartnerStore {
  // Navigation
  currentPage: PartnerPage;
  previousPage: PartnerPage | null;
  intendedDestination: PartnerPage | null;
  navigate: (page: PartnerPage) => void;
  setIntendedDestination: (page: PartnerPage) => void;

  // Auth
  authStatus: PartnerAuthStatus;
  user: PartnerUser | null;
  accessToken: string | null;
  refreshToken: string | null;
  setAuthStatus: (status: PartnerAuthStatus) => void;
  setUser: (user: PartnerUser | null) => void;
  setTokens: (access: string, refresh: string) => void;

  // Partner profile
  partner: Partner | null;
  setPartner: (partner: Partner | null) => void;

  // Partner data (raw from API)
  dashboardData: PartnerDashboardResponse | null;
  referrals: ReferralItem[];
  referralsTotal: number;
  commissions: CommissionItem[];
  commissionsTotal: number;
  payouts: PayoutItem[];
  payoutsTotal: number;
  setDashboardData: (data: PartnerDashboardResponse) => void;
  setReferrals: (items: ReferralItem[], total: number) => void;
  setCommissions: (items: CommissionItem[], total: number) => void;
  setPayouts: (items: PayoutItem[], total: number) => void;

  // UI state
  isSidebarOpen: boolean;
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;

  // Reset
  logout: () => void;
}

const initialState = {
  currentPage: 'landing' as PartnerPage,
  previousPage: null as PartnerPage | null,
  intendedDestination: null as PartnerPage | null,
  authStatus: 'idle' as PartnerAuthStatus,
  user: null as PartnerUser | null,
  accessToken: null as string | null,
  refreshToken: null as string | null,
  partner: null as Partner | null,
  dashboardData: null as PartnerDashboardResponse | null,
  referrals: [] as ReferralItem[],
  referralsTotal: 0,
  commissions: [] as CommissionItem[],
  commissionsTotal: 0,
  payouts: [] as PayoutItem[],
  payoutsTotal: 0,
  isSidebarOpen: false,
};

export const usePartnerStore = create<PartnerStore>()(
  persist(
    (set) => ({
      ...initialState,

      navigate: (page) =>
        set((state) => ({
          previousPage: state.currentPage,
          currentPage: page,
        })),

      setIntendedDestination: (page) =>
        set({ intendedDestination: page }),

      setAuthStatus: (authStatus) => set({ authStatus }),
      setUser: (user) => set({ user }),
      setTokens: (access, refresh) => {
        localStorage.setItem('partner_access_token', access);
        localStorage.setItem('partner_refresh_token', refresh);
        set({ accessToken: access, refreshToken: refresh });
      },

      setPartner: (partner) => set({ partner }),

      setDashboardData: (data) => set({ dashboardData: data }),
      setReferrals: (items, total) => set({ referrals: items, referralsTotal: total }),
      setCommissions: (items, total) => set({ commissions: items, commissionsTotal: total }),
      setPayouts: (items, total) => set({ payouts: items, payoutsTotal: total }),

      toggleSidebar: () =>
        set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),
      setSidebarOpen: (open) => set({ isSidebarOpen: open }),

      logout: () => {
        localStorage.removeItem('partner_access_token');
        localStorage.removeItem('partner_refresh_token');
        set({
          ...initialState,
          currentPage: 'home',
          authStatus: 'unauthenticated',
        });
      },
    }),
    {
      name: 'partner-store',
      storage: createJSONStorage(() => {
        if (typeof window !== 'undefined') return localStorage;
        return {
          getItem: () => null,
          setItem: () => {},
          removeItem: () => {},
        };
      }),
      partialize: (state) => ({
        user: state.user,
        authStatus: state.authStatus,
        accessToken: state.accessToken,
        refreshToken: state.refreshToken,
        partner: state.partner,
      }),
    }
  )
);
