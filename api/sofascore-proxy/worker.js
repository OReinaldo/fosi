const UPSTREAM = 'https://api.sofascore.com/api/v1';
const MAX_PATH = 2048;

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' }
  });
}

export default {
  async fetch(request, env, ctx) {
    if (request.method !== 'GET') return json({ error: 'method_not_allowed' }, 405);

    const token = env.FOSI_PROXY_TOKEN || '';
    if (!token || request.headers.get('Authorization') !== `Bearer ${token}`) {
      return json({ error: 'unauthorized' }, 401);
    }

    const url = new URL(request.url);
    if (url.pathname.length > MAX_PATH || !url.pathname.startsWith('/api/v1/')) {
      return json({ error: 'path_not_allowed' }, 400);
    }

    // Fixed upstream + fixed API prefix: this is intentionally NOT an open proxy.
    const upstreamUrl = `${UPSTREAM}${url.pathname.slice('/api/v1'.length)}${url.search}`;
    const upstreamRequest = new Request(upstreamUrl, {
      method: 'GET',
      headers: {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.sofascore.com/',
        'Origin': 'https://www.sofascore.com',
        'X-Requested-With': 'XMLHttpRequest',
        'User-Agent': request.headers.get('User-Agent') || 'FOSI-SofaScore-Gateway/1.0'
      }
    });

    const response = await fetch(upstreamRequest, {
      cf: { cacheTtl: 30, cacheEverything: false }
    });

    const headers = new Headers(response.headers);
    headers.set('cache-control', 'public, max-age=30');
    headers.delete('set-cookie');
    return new Response(response.body, { status: response.status, headers });
  }
};
