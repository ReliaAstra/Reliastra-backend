import { PrismaClient } from '@prisma/client';
const p = new PrismaClient();

const d = 86400000;

async function seed() {
  const u = await p.user.findFirst({ include: { partner: true } });
  if (!u?.partner) { console.log('No partner found'); return; }
  const pid = u.partner.id;

  const refs = [
    { partnerId: pid, referredEmail: 'alex@meridian.io', referredName: 'Alex Chen', plan: 'Pro', status: 'active', createdAt: new Date(Date.now() - 155 * d) },
    { partnerId: pid, referredEmail: 'sarah@brightcore.dev', referredName: 'Sarah Kim', plan: 'Pro', status: 'active', createdAt: new Date(Date.now() - 120 * d) },
    { partnerId: pid, referredEmail: 'marcus@stacklane.co', referredName: 'Marcus Webb', plan: 'Team', status: 'active', createdAt: new Date(Date.now() - 85 * d) },
    { partnerId: pid, referredEmail: 'jordan@opstoolkit.com', referredName: 'Jordan Blake', plan: 'Pro', status: 'cancelled', createdAt: new Date(Date.now() - 60 * d) },
    { partnerId: pid, referredEmail: 'priya@nexacore.io', referredName: 'Priya Sharma', plan: 'Team', status: 'active', createdAt: new Date(Date.now() - 22 * d) },
  ];

  for (const r of refs) {
    await p.referral.upsert({ where: { id: r.referredEmail + '_' + pid }, update: r, create: r });
  }

  const plans: Record<string, number> = { Pro: 4900, Team: 8700 };
  let ci = 200;

  for (const rf of refs) {
    const ma = plans[rf.plan] || 4900;
    const startOffset = Math.floor((Date.now() - new Date(rf.createdAt).getTime()) / d);

    for (let m = startOffset; m >= 0; m--) {
      const dt = new Date(rf.createdAt);
      dt.setDate(dt.getDate() + m);

      if (rf.status === 'cancelled' && m < startOffset - 30) continue;
      if (rf.status === 'cancelled' && m === startOffset - 30) {
        await p.commission.create({
          data: { id: 'c' + ci, partnerId: pid, referralId: rf.referredEmail + '_' + pid, amount: ma, currency: 'USD', status: 'paid', period: dt.toISOString().slice(0, 7), createdAt: dt },
        });
        ci++;
        continue;
      }

      const age = startOffset - m;
      let st: string;
      if (age > 2) st = 'paid';
      else if (age > 1) st = 'payable';
      else st = 'pending';

      await p.commission.create({
        data: { id: 'c' + ci, partnerId: pid, referralId: rf.referredEmail + '_' + pid, amount: ma, currency: 'USD', status: st, period: dt.toISOString().slice(0, 7), createdAt: dt },
      });
      ci++;
    }
  }

  await p.payout.create({
    data: { id: 'pay_1', partnerId: pid, amount: 100000, currency: 'USD', status: 'completed', method: 'bank_transfer', paidAt: new Date(Date.now() - 35 * d) },
  });
  await p.payout.create({
    data: { id: 'pay_2', partnerId: pid, amount: 80000, currency: 'USD', status: 'pending', method: 'bank_transfer' },
  });

  console.log('Seeded: 5 referrals,', (ci - 200), 'commissions, 2 payouts');
  await p.$disconnect();
}

seed().then(() => console.log('done')).catch((e) => console.error(e.message));
