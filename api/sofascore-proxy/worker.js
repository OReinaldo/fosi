const UPSTREAMS = [
  'https://api.sofascore.com/api/v1',
  'https://api.sofascore.app/api/v1',
  'https://www.sofascore.com/api/v1'
];
const MAX_PATH = 2048;

function json(data, status = 200, extra = {}) {
  const headers = new Headers({
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store'
  });
  for (const [k, v] of Object.entries(extra)) headers.set(k, String(v));
  return new Response(JSON.stringify(data), { status, headers });
}

export default {
  async fetch(request, env) {
    if (request.method !== 'GET') return json({ error: 'method_not_allowed' }, 405);

    const token = env.FOSI_PROXY_TOKEN || '';
    if (!token || request.headers.get('Authorization') !== `Bearer ${token}`) {
      return json({ error: 'unauthorized' }, 401);
    }

    const url = new URL(request.url);
    if (url.pathname.length > MAX_PATH || !url.pathname.startsWith('/api/v1/')) {
      return json({ error: 'path_not_allowed' }, 400);
    }

    const suffix = `${url.pathname.slice('/api/v1'.length)}${url.search}`;
    const attempts = [];

    for (const upstream of UPSTREAMS) {
      const upstreamUrl = `${upstream}${suffix}`;
      try {
        const response = await fetch(new Request(upstreamUrl, {
          method: 'GET',
          headers: {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': 'https://www.sofascore.com/',
            'Origin': 'https://www.sofascore.com',
            'X-Requested-With': 'XMLHttpRequest',
            'User-Agent': request.headers.get('User-Agent') || 'FOSI-SofaScore-Gateway/1.0'
          }
        }), { cf: { cacheTtl: 30, cacheEverything: false } });

        attempts.push({ upstream, status: response.status });

        // Try the next public SofaScore host on WAF/rate-limit responses.
        if (response.status === 403 || response.status === 429 || response.status >= 500) {
          continue;
        }

        const headers = new Headers(response.headers);
        headers.set('cache-control', 'public, max-age=30');
        headers.set('x-fosi-gateway', 'sofascore');
        headers.set('x-fosi-upstream', upstream);
        headers.delete('set-cookie');
        return new Response(response.body, { status: response.status, headers });
      } catch (error) {
        attempts.push({ upstream, error: String(error).slice(0, 180) });
      }
    }

    return json({ error: 'upstream_unavailable', attempts }, 502, {
      'x-fosi-gateway': 'sofascore'
    });
  }
};
