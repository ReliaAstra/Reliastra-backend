import { NextRequest } from 'next/server';
import { proxyToBackend } from '@/lib/backend-proxy';

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const params = url.searchParams.toString();
  const path = `/partners/payouts${params ? `?${params}` : ''}`;
  return proxyToBackend(path, req);
}
