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

function browserSchema(kind) {
  if (kind === 'team') return {
    type: 'json_schema',
    json_schema: {
      type: 'object',
      properties: {
        team: { type: 'object' },
        players: { type: 'array', items: { type: 'object' } },
        fixtures: { type: 'array', items: { type: 'object' } }
      }
    }
  };
  if (kind === 'events') return {
    type: 'json_schema',
    json_schema: {
      type: 'object',
      properties: { events: { type: 'array', items: { type: 'object' } } },
      required: ['events']
    }
  };
  return {
    type: 'json_schema',
    json_schema: {
      type: 'object',
      properties: {
        event: { type: 'object' },
        statistics: { type: 'array', items: { type: 'object' } },
        incidents: { type: 'array', items: { type: 'object' } },
        lineups: { type: 'object' }
      }
    }
  };
}

async function browserFallback(env, path) {
  if (!env.BROWSER) return null;
  const teamMatch = path.match(/^\/team\/(\d+)(\/players)?$/);
  const eventsMatch = path.match(/^\/team\/(\d+)\/events\/(last|next)\/(\d+)$/);
  const eventMatch = path.match(/^\/event\/(\d+)(?:\/(statistics|incidents|lineups|graph|shotmap|media))?$/);
  let url = null, kind = null, prompt = '';

  if (teamMatch) {
    const id = teamMatch[1];
    url = `https://www.sofascore.com/football/team/pogon-szczecin/${id}`;
    kind = 'team';
    prompt = teamMatch[2]
      ? 'Extract the complete current squad visible on this SofaScore team page. Return only players with player name, player id if visible, position, jersey number if visible, and team id.'
      : 'Extract the team identity, current squad and the most recent and upcoming football fixtures visible on this SofaScore team page. Preserve numeric ids, dates, scores, competition, home/away teams and status when visible. Do not invent missing values.';
  } else if (eventsMatch) {
    const id = eventsMatch[1];
    url = `https://www.sofascore.com/football/team/pogon-szczecin/${id}`;
    kind = 'events';
    prompt = `Extract all football match cards visible for team id ${id} on this SofaScore team page. Return event id, home team, away team, start time/date, competition, round, status and scores when visible. Include as many visible matches as possible and do not invent values.`;
  } else if (eventMatch) {
    const id = eventMatch[1];
    url = `https://www.sofascore.com/event/${id}`;
    kind = 'event';
    const sub = eventMatch[2] || 'event';
    prompt = sub === 'statistics'
      ? 'Extract the detailed full-match statistics shown for this SofaScore football match, grouped by section. Preserve exact home and away values, names and keys when visible. Also include the event id and teams. Do not invent values.'
      : sub === 'incidents'
      ? 'Extract the complete match incident timeline shown for this SofaScore football match: goals, cards, substitutions, VAR and timestamps, with player and team names and event id. Do not invent values.'
      : sub === 'lineups'
      ? 'Extract the complete lineups shown for this SofaScore football match, including formations, starters, substitutes, player ids, positions, ratings and minutes when visible. Do not invent values.'
      : 'Extract the core event information shown for this SofaScore football match: event id, tournament, round, date, venue, home/away teams, status, scores and all visible match information. Do not invent values.';
  } else return null;

  try {
    const result = await env.BROWSER.quickAction('json', {
      url,
      prompt,
      response_format: browserSchema(kind),
      gotoOptions: { waitUntil: 'networkidle2' }
    });
    const data = await result.json();
    if (!data || data.success === false) return null;
    return { source: 'cloudflare-browser-run', source_url: url, data: data.result || data };
  } catch (error) {
    return { error: String(error).slice(0, 300), source: 'cloudflare-browser-run', source_url: url };
  }
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
        if (response.status === 403 || response.status === 429 || response.status >= 500) continue;

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

    // Final fallback: Cloudflare Browser Run. It uses a real managed browser on
    // Cloudflare's edge and renders the public SofaScore page instead of calling
    // the blocked internal API from the Worker egress IP.
    const browser = await browserFallback(env, url.pathname.slice('/api/v1'.length));
    if (browser && !browser.error) {
      return json(browser.data, 200, {
        'x-fosi-gateway': 'sofascore-browser-run',
        'x-fosi-source-url': browser.source_url
      });
    }

    return json({
      error: 'upstream_unavailable',
      attempts,
      browser_fallback: browser || { available: false }
    }, 502, { 'x-fosi-gateway': 'sofascore' });
  }
};
