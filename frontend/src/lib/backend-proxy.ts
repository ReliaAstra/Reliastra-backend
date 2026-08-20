const BACKEND_URL = 'https://reliastra-backend.zevcloud.app';

export async function proxyToBackend(
  path: string,
  req: Request,
  options?: {
    /** Override the HTTP method */
    method?: string;
    /** Omit the request body (e.g. for GET) */
    noBody?: boolean;
  }
): Promise<Response> {
  const url = `${BACKEND_URL}/v1${path}`;
  const method = options?.method || req.method;

  const headers: Record<string, string> = {};

  // Forward authorization
  const authHeader = req.headers.get('authorization');
  if (authHeader) headers['Authorization'] = authHeader;

  // Forward content-type for requests with body
  if (!options?.noBody && method !== 'GET' && method !== 'HEAD') {
    headers['Content-Type'] = 'application/json';
    // Also forward the org header if present
    const orgHeader = req.headers.get('x-organization-id');
    if (orgHeader) headers['X-Organization-ID'] = orgHeader;
  }

  const fetchOptions: RequestInit = { method, headers };

  if (!options?.noBody && method !== 'GET' && method !== 'HEAD') {
    fetchOptions.body = await req.text();
  }

  const res = await fetch(url, fetchOptions);

  // Return the response as-is to the client
  const responseHeaders = new Headers();
  responseHeaders.set('Content-Type', res.headers.get('Content-Type') || 'application/json');

  return new Response(res.body, {
    status: res.status,
    statusText: res.statusText,
    headers: responseHeaders,
  });
}
