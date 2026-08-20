'use client';

import { motion } from 'framer-motion';
import { usePartnerStore } from '@/stores/partner-store';
import { toast } from 'sonner';
import { maskEmail } from '@/lib/format';
import { ReferralLinkCard } from '@/components/partner/shared/referral-link-card';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Separator } from '@/components/ui/separator';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import { DashboardSettingsSkeleton } from '@/components/partner/shared/dashboard-skeleton';
import { useState, useEffect } from 'react';

type PayoutMethod = 'crypto_usdc' | 'crypto_usdt' | 'bank';

// --- Account tab ---
function AccountTab() {
  const user = usePartnerStore((s) => s.user);

  const initials = user?.name
    ? user.name
        .split(' ')
        .map((n) => n[0])
        .join('')
        .slice(0, 2)
        .toUpperCase()
    : user?.email?.[0]?.toUpperCase() || 'P';

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <div className="flex items-center justify-center size-12 rounded-full bg-muted text-sm font-mono font-medium">
          {initials}
        </div>
        <div>
          <p className="font-medium">{user?.name || 'Partner'}</p>
          <p className="text-sm text-muted-foreground font-mono">
            {user?.email || ''}
          </p>
        </div>
      </div>

      <Separator />

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2">
          <Label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">
            Name
          </Label>
          <Input
            value={user?.name || ''}
            disabled
            className="font-mono text-sm bg-muted/50"
          />
        </div>
        <div className="space-y-2">
          <Label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">
            Email
          </Label>
          <Input
            value={user?.email || ''}
            disabled
            className="font-mono text-sm bg-muted/50"
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">
          Partner status
        </Label>
        <div>
          <Badge variant="outline" className="text-xs font-mono">
            {user?.partner?.status?.toUpperCase() || 'ACTIVE'}
          </Badge>
        </div>
      </div>

      <p className="text-xs text-muted-foreground">
        Account details are managed through your RELIASTRA account. Contact support to make changes.
      </p>

      <Separator />

      {/* Customer Support */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 rounded-lg border border-border/60 p-4 md:p-5">
        <div>
          <p className="text-sm font-medium">Need help?</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            Our partner support team is here to assist you with any questions.
          </p>
        </div>
        <button
          onClick={() => usePartnerStore.getState().navigate('support')}
          className="inline-flex items-center justify-center gap-2 rounded-md bg-foreground px-4 py-2.5 text-xs font-mono font-medium uppercase tracking-wider text-background transition-colors hover:bg-foreground/90 shrink-0"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
          </svg>
          Contact Support
        </button>
      </div>
    </div>
  );
}

// --- Crypto option card ---
function CryptoOptionCard({
  name,
  symbol,
  network,
  recommended,
  selected,
  onSelect,
}: {
  name: string;
  symbol: string;
  network: string;
  recommended: boolean;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        'relative w-full text-left rounded-lg border-2 p-4 md:p-5 transition-all duration-200',
        'hover:border-foreground/40 hover:shadow-sm',
        selected
          ? 'border-foreground/80 bg-muted/30'
          : 'border-border/60 bg-background'
      )}
    >
      {/* Most Recommended badge */}
      {recommended && (
        <div className="absolute -top-2.5 left-4">
          <Badge className="bg-foreground text-background border-0 text-[9px] font-mono uppercase tracking-[0.15em] px-2 py-0.5">
            Most Recommended
          </Badge>
        </div>
      )}

      <div className="flex items-center gap-3 mt-1">
        {/* Crypto icon */}
        <div className={cn(
          'flex items-center justify-center size-10 rounded-full border shrink-0',
          selected ? 'border-foreground/40 bg-muted/50' : 'border-border/60'
        )}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" className="text-foreground">
            <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="1.5" />
            <path d="M12 6v12M8 10c0-2.2 1.8-4 4-4s4 1.8 4 4-1.8 4-4 4M8 14c0 2.2 1.8 4 4 4s4-1.8 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </div>

        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold tracking-tight">{name}</p>
          <p className="text-[11px] font-mono text-muted-foreground mt-0.5">
            {network}
          </p>
        </div>

        {/* Selection indicator */}
        <div className={cn(
          'flex items-center justify-center size-5 rounded-full border-2 shrink-0 transition-colors',
          selected
            ? 'border-foreground bg-foreground'
            : 'border-border'
        )}>
          {selected && (
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
              <path d="M5 12l5 5L20 7" />
            </svg>
          )}
        </div>
      </div>
    </button>
  );
}

// --- Payout information tab ---
function PayoutInfoTab() {
  const [selectedMethod, setSelectedMethod] = useState<PayoutMethod>('crypto_usdc');
  const [walletAddress, setWalletAddress] = useState('');

  const methods: { id: PayoutMethod; name: string; symbol: string; network: string; recommended: boolean }[] = [
    { id: 'crypto_usdc', name: 'USD Coin (USDC)', symbol: 'USDC', network: 'Ethereum / Polygon / Solana', recommended: true },
    { id: 'crypto_usdt', name: 'Tether (USDT)', symbol: 'USDT', network: 'Ethereum / Tron / BSC', recommended: false },
    { id: 'bank', name: 'Bank Transfer', symbol: 'USD', network: 'ACH / Wire / SWIFT', recommended: false },
  ];

  const selectedMethodInfo = methods.find((m) => m.id === selectedMethod);

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">
        Configure your payout details. These are used when you request a withdrawal.
      </p>

      <Separator />

      {/* Payout method selection */}
      <div className="space-y-3">
        <Label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">
          Payout method
        </Label>
        <div className="space-y-3 max-w-lg">
          {methods.map((m) => (
            <CryptoOptionCard
              key={m.id}
              name={m.name}
              symbol={m.symbol}
              network={m.network}
              recommended={m.recommended}
              selected={selectedMethod === m.id}
              onSelect={() => setSelectedMethod(m.id)}
            />
          ))}
        </div>
      </div>

      <Separator />

      {/* Crypto wallet address fields */}
      {(selectedMethod === 'crypto_usdc' || selectedMethod === 'crypto_usdt') && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          className="space-y-4 max-w-lg"
        >
          <div className="space-y-2">
            <Label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">
              Wallet address
            </Label>
            <Input
              placeholder={selectedMethod === 'crypto_usdc' ? '0x... or your Solana address' : '0x... or your Tron address'}
              value={walletAddress}
              onChange={(e) => setWalletAddress(e.target.value)}
              className="font-mono text-sm"
            />
            <p className="text-[11px] text-muted-foreground">
              Enter your {selectedMethodInfo?.name} wallet address. Double-check before saving — crypto transactions are irreversible.
            </p>
          </div>

          <div className="space-y-2">
            <Label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">
              Network
            </Label>
            <div className="grid grid-cols-3 gap-2">
              {selectedMethod === 'crypto_usdc' && (
                <>
                  {['Ethereum', 'Polygon', 'Solana'].map((n) => (
                    <button
                      key={n}
                      type="button"
                      className="rounded-md border border-border/60 px-3 py-2 text-xs font-mono text-muted-foreground hover:border-foreground/40 hover:text-foreground transition-colors"
                    >
                      {n}
                    </button>
                  ))}
                </>
              )}
              {selectedMethod === 'crypto_usdt' && (
                <>
                  {['Ethereum', 'Tron', 'BSC'].map((n) => (
                    <button
                      key={n}
                      type="button"
                      className="rounded-md border border-border/60 px-3 py-2 text-xs font-mono text-muted-foreground hover:border-foreground/40 hover:text-foreground transition-colors"
                    >
                      {n}
                    </button>
                  ))}
                </>
              )}
            </div>
          </div>
        </motion.div>
      )}

      {/* Bank transfer fields */}
      {selectedMethod === 'bank' && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3 }}
          className="space-y-4 max-w-md"
        >
          <div className="space-y-2">
            <Label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">
              Name on account
            </Label>
            <Input placeholder="Full legal name" className="font-mono text-sm" />
          </div>

          <div className="space-y-2">
            <Label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">
              Bank name
            </Label>
            <Input placeholder="Bank name" className="font-mono text-sm" />
          </div>

          <div className="space-y-2">
            <Label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">
              Account number
            </Label>
            <Input placeholder="Account number" className="font-mono text-sm" />
          </div>

          <div className="space-y-2">
            <Label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">
              Routing number
            </Label>
            <Input placeholder="Routing number" className="font-mono text-sm" />
          </div>

          <div className="space-y-2">
            <Label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">
              SWIFT / BIC (international)
            </Label>
            <Input placeholder="Optional" className="font-mono text-sm" />
          </div>
        </motion.div>
      )}

      <Badge variant="outline" className="text-[10px] font-mono uppercase tracking-wide">
        Payout information is not yet saved to your account
      </Badge>
    </div>
  );
}

// --- Partner link tab ---
function PartnerLinkTab() {
  const dashboardData = usePartnerStore((s) => s.dashboardData);
  const user = usePartnerStore((s) => s.user);
  const referralLink = dashboardData?.referralLink || '';

  const shareChannels = [
    {
      name: 'Email',
      description: 'Send directly to a contact',
      action: () => {
        const subject = encodeURIComponent('Check out RELIASTRA');
        const body = encodeURIComponent(`I thought you'd find this useful — it's a platform for critical infrastructure intelligence.\n\n${referralLink}`);
        window.open(`mailto:?subject=${subject}&body=${body}`);
        toast.success('Email client opened');
      },
    },
    {
      name: 'Twitter / X',
      description: 'Post to your followers',
      action: () => {
        const text = encodeURIComponent(`If you depend on critical infrastructure, check out @reliastra. Full incident timelines, cross-system correlation, actionable evidence.\n\n${referralLink}`);
        window.open(`https://twitter.com/intent/tweet?text=${text}`, '_blank');
        toast.success('Opening Twitter');
      },
    },
    {
      name: 'LinkedIn',
      description: 'Share with your network',
      action: () => {
        const text = encodeURIComponent(`RELIASTRA — infrastructure intelligence for critical operations. Track, correlate, and prove what happened.\n\n${referralLink}`);
        window.open(`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(referralLink)}&summary=${text}`, '_blank');
        toast.success('Opening LinkedIn');
      },
    },
  ];

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">
        Your unique referral link. Share it with potential customers to earn 30% recurring commission.
      </p>

      <ReferralLinkCard link={referralLink} size="large" />

      {user?.partner?.referralCode && (
        <div className="space-y-2">
          <Label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">
            Referral code
          </Label>
          <p className="font-mono text-sm text-foreground/80">
            {user.partner.referralCode.toUpperCase()}
          </p>
        </div>
      )}

      <Separator />

      {/* Share channels */}
      <div className="space-y-4">
        <Label className="text-xs font-mono uppercase tracking-widest text-muted-foreground">
          Share via
        </Label>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {shareChannels.map((channel) => (
            <button
              key={channel.name}
              onClick={channel.action}
              className="rounded-lg border border-border/60 bg-background p-4 text-left transition-colors hover:border-border hover:bg-muted/30"
            >
              <p className="text-sm font-medium">{channel.name}</p>
              <p className="text-xs text-muted-foreground mt-0.5">{channel.description}</p>
            </button>
          ))}
        </div>
      </div>

      {/* Tracking info */}
      <Separator />
      <div className="grid grid-cols-3 gap-4">
        <div className="text-center">
          <p className="font-mono text-2xl font-semibold tracking-tight">30%</p>
          <p className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mt-1">Commission</p>
        </div>
        <div className="text-center">
          <p className="font-mono text-2xl font-semibold tracking-tight">90d</p>
          <p className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mt-1">Cookie window</p>
        </div>
        <div className="text-center">
          <p className="font-mono text-2xl font-semibold tracking-tight">∞</p>
          <p className="text-[10px] font-mono uppercase tracking-widest text-muted-foreground mt-1">No cap</p>
        </div>
      </div>
    </div>
  );
}

// --- Notifications tab ---
function NotificationsTab() {
  const [commissionNotif, setCommissionNotif] = useState(true);
  const [payoutNotif, setPayoutNotif] = useState(true);
  const [referralNotif, setReferralNotif] = useState(true);
  const [marketingNotif, setMarketingNotif] = useState(false);

  const items = [
    {
      label: 'New commission',
      description: 'Get notified when a new commission is earned.',
      checked: commissionNotif,
      onCheckedChange: setCommissionNotif,
    },
    {
      label: 'Payout updates',
      description: 'Receive updates about your payout requests.',
      checked: payoutNotif,
      onCheckedChange: setPayoutNotif,
    },
    {
      label: 'New referrals',
      description: 'Know when someone signs up through your link.',
      checked: referralNotif,
      onCheckedChange: setReferralNotif,
    },
    {
      label: 'Marketing & tips',
      description: 'Occasional partner program updates and resources.',
      checked: marketingNotif,
      onCheckedChange: setMarketingNotif,
    },
  ];

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">
        Manage your email notification preferences.
      </p>

      <Separator />

      <div className="space-y-0 divide-y divide-border/40">
        {items.map((item) => (
          <div
            key={item.label}
            className="flex items-center justify-between py-4 first:pt-0 last:pb-0"
          >
            <div className="pr-4">
              <p className="text-sm font-medium">{item.label}</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                {item.description}
              </p>
            </div>
            <Switch
              checked={item.checked}
              onCheckedChange={item.onCheckedChange}
              aria-label={item.label}
            />
          </div>
        ))}
      </div>

      <Badge variant="outline" className="text-[10px] font-mono uppercase tracking-wide">
        Notification preferences are not yet saved
      </Badge>
    </div>
  );
}

// --- Main page ---
export function PageSettings() {
  const [mounted, setMounted] = useState(false);
  const user = usePartnerStore((s) => s.user);

  // Brief skeleton on initial mount
  useEffect(() => {
    const timer = setTimeout(() => setMounted(true), 300);
    return () => clearTimeout(timer);
  }, []);

  if (!mounted || !user) {
    return <DashboardSettingsSkeleton />;
  }

  return (
    <div className="max-w-4xl space-y-6">
      {/* Heading */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
      >
        <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">
          Settings
        </h1>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, delay: 0.05 }}
      >
        <Tabs defaultValue="account" className="w-full">
          <TabsList className="w-full sm:w-auto overflow-x-auto">
            <TabsTrigger value="account" className="text-xs font-mono uppercase tracking-wide">
              Account
            </TabsTrigger>
            <TabsTrigger value="payout" className="text-xs font-mono uppercase tracking-wide">
              Payout Info
            </TabsTrigger>
            <TabsTrigger value="link" className="text-xs font-mono uppercase tracking-wide">
              Partner Link
            </TabsTrigger>
            <TabsTrigger value="notifications" className="text-xs font-mono uppercase tracking-wide">
              Notifications
            </TabsTrigger>
          </TabsList>

          <TabsContent value="account" className="mt-6">
            <AccountTab />
          </TabsContent>

          <TabsContent value="payout" className="mt-6">
            <PayoutInfoTab />
          </TabsContent>

          <TabsContent value="link" className="mt-6">
            <PartnerLinkTab />
          </TabsContent>

          <TabsContent value="notifications" className="mt-6">
            <NotificationsTab />
          </TabsContent>
        </Tabs>
      </motion.div>
    </div>
  );
}
