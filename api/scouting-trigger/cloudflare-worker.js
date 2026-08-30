const REPO = 'OReinaldo/fosi';
const WORKFLOW = 'update-data.yml';

export default {
  async fetch(request, env) {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });
    const origin = request.headers.get('Origin') || '';
    if (env.ALLOWED_ORIGIN && origin !== env.ALLOWED_ORIGIN) return new Response('Forbidden', { status: 403 });
    let body;
    try { body = await request.json(); } catch { return Response.json({ error: 'invalid_json' }, { status: 400 }); }
    const { country, competition, team } = body || {};
    if (![country, competition, team].every(v => typeof v === 'string' && /^[a-zA-Z0-9 _.-]{1,100}$/.test(v)))
      return Response.json({ error: 'invalid_selection' }, { status: 400 });
    const r = await fetch(`https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches`, {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${env.GITHUB_TOKEN}`, 'Accept': 'application/vnd.github+json', 'Content-Type': 'application/json', 'User-Agent': 'FOSI-scouting-trigger' },
      body: JSON.stringify({ ref: 'main', inputs: { country, competition, team } })
    });
    if (!r.ok) return Response.json({ error: 'github_dispatch_failed', status: r.status }, { status: 502 });
    return Response.json({ accepted: true }, { status: 202 });
  }
};
