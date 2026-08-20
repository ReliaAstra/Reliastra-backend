import { NextRequest } from 'next/server';
import { proxyToBackend } from '@/lib/backend-proxy';

export async function POST(req: NextRequest) {
  return proxyToBackend('/partners/apply', req);
}
