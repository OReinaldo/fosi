const ALLOWED_ORIGIN = 'https://oreinaldo.github.io';

export default {
  async fetch(request, env) {
    const headers = { 'content-type':'application/json; charset=utf-8', 'access-control-allow-origin': ALLOWED_ORIGIN, 'access-control-allow-methods':'POST, OPTIONS', 'access-control-allow-headers':'content-type' };
    if (request.method === 'OPTIONS') return new Response(null, {status:204, headers});
    if (request.method !== 'POST') return new Response(JSON.stringify({error:'POST required'}), {status:405, headers});
    const origin = request.headers.get('Origin');
    if (origin && origin !== ALLOWED_ORIGIN) return new Response(JSON.stringify({error:'origin denied'}), {status:403, headers});
    try {
      const body = await request.json();
      for (const k of ['country','competition','team']) if (!body[k] || typeof body[k] !== 'string') throw Error(`missing ${k}`);
      const dispatch = await fetch(`https://api.github.com/repos/${env.FOSI_REPOSITORY}/actions/workflows/update-data.yml/dispatches`, {
        method:'POST', headers:{'accept':'application/vnd.github+json','authorization':`Bearer ${env.FOSI_GITHUB_TOKEN}`,'content-type':'application/json','user-agent':'FOSI-trigger'},
        body: JSON.stringify({ref: env.FOSI_REF || 'main', inputs:{country:body.country, competition:body.competition, team:body.team}})
      });
      if (!dispatch.ok) return new Response(JSON.stringify({error:'github dispatch failed', status:dispatch.status}), {status:502, headers});
      return new Response(JSON.stringify({ok:true,status:'initializing'}), {status:202, headers});
    } catch (e) { return new Response(JSON.stringify({error:e.message}), {status:400, headers}); }
  }
};
