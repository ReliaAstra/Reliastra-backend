import { NextRequest } from 'next/server';
import { proxyToBackend } from '@/lib/backend-proxy';

export async function GET(req: NextRequest) {
  // Forward query params for pagination
  const url = new URL(req.url);
  const params = url.searchParams.toString();
  const path = `/partners/referrals${params ? `?${params}` : ''}`;
  return proxyToBackend(path, req);
}
