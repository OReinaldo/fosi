const $=(s)=>document.querySelector(s);
const TRIGGER_URL=window.FOSI_TRIGGER_URL||'';

function metricValue(m,k){const v=m?.[k];return v&&typeof v==='object'?v.value:v;}
function evidenceClass(meta){return meta?.status==='derived'?'Derived':meta?.status==='observed'?'Observed':'Unavailable';}
function renderEvidenceMetric(k,label){const meta=window.__FOSI_META?.[k];const value=metricValue(window.__FOSI_METRICS,k);return `<div class="bar"><span>${label}</span><div class="track"><div class="fill" style="width:${meta?.coverage?Math.min(100,meta.coverage*100):0}%"></div></div><b>${value??'—'}</b></div>`;}

async function loadFosi(){
  try{
    const r=await fetch('./data.json?ts='+Date.now());
    if(!r.ok)throw new Error('data.json '+r.status);
    const d=await r.json();
    window.__FOSI_METRICS=d.metrics||{};
    window.__FOSI_META=d.metric_meta||{};
    document.querySelectorAll('[data-team]').forEach(e=>e.textContent=d.team?.name||'—');
    const m=d.metrics||{};
    const map={form:m.form,goals:`${m.goals_for??'—'} / ${m.goals_against??'—'}`,xg:m.xg,xga:m.xga,threat:d.threat_score,data:d.data_quality?.score};
    Object.entries(map).forEach(([k,v])=>document.querySelectorAll(`[data-kpi="${k}"]`).forEach(e=>e.textContent=v==null?'—':v));
    const q=d.data_quality?.score??0;
    $('#coverageBar')?.style.setProperty('width',q+'%');
    if($('#coverageText'))$('#coverageText').textContent=q+'%';
    $('#liveStatus')&&($('#liveStatus').textContent=d.status==='verified_partial'?'Verified partial dataset':'Awaiting verified ingestion');
    renderInsights(d.insights||[]);
    renderMatches(d.matches||[]);
    renderEvidence(d);
  }catch(e){console.warn('FOSI data load:',e);$('#liveStatus')&&($('#liveStatus').textContent='Data unavailable');}
}

function renderEvidence(d){
  const box=$('#teamEvidence');
  if(box){
    box.innerHTML=[
      renderEvidenceMetric('shots_count','Shots'),
      renderEvidenceMetric('shots_with_xg','Shots with xG'),
      renderEvidenceMetric('xgot','xGOT'),
      renderEvidenceMetric('recoveries','Recoveries'),
      renderEvidenceMetric('losses','Losses'),
      renderEvidenceMetric('tackles','Tackles'),
      renderEvidenceMetric('interceptions','Interceptions'),
      renderEvidenceMetric('duels','Duels')
    ].join('');
  }
  const zones=$('#shotZones');
  if(zones){const z=d.shot_zones_for||{};zones.innerHTML=Object.keys(z).length?Object.entries(z).map(([k,v])=>`<div class="threat"><b>${k}</b><small>${v} observed shots</small></div>`).join(''):'<div class="muted">No reliable shot-zone coordinates available.</div>';}
}

function renderInsights(items){const box=$('#insights');if(!box)return;box.innerHTML=items.length?items.map(x=>`<article><b>${x.title||'Insight'}</b><small>${x.evidence||''}</small><em>${x.confidence??'—'}/100</em></article>`).join(''):'<article><b>Evidence engine ready</b><small>Insights appear only after verified match data is available.</small><em>—</em></article>';}

function renderMatches(matches){
  let box=$('#fosiMatches');
  if(!box){box=document.createElement('section');box.id='fosiMatches';box.className='card';box.style.marginTop='14px';document.querySelector('main').insertBefore(box,document.querySelector('.footer'));}
  box.innerHTML='<div class="title"><b>RECENT MATCHES</b><span class="muted">Verified match detail</span></div>'+(matches.length?matches.map(m=>{const h=m.home_team?.name||m.home||'—',a=m.away_team?.name||m.away||'—',s=m.score?.home!=null?`${m.score.home} — ${m.score.away}`:(m.score||'—');return `<div class="threat" style="display:flex;justify-content:space-between;gap:10px"><span><b>${h} — ${a}</b><small>${m.date?new Date(m.date).toLocaleDateString('en-GB'):''} · ${m.competition||''}</small></span><b>${s}</b></div>`}).join(''):'<div class="muted">No verified match details available yet.</div>');
}

async function startScouting(){const selects=document.querySelectorAll('select');const country=selects[0]?.value||'Poland';const competition=selects[1]?.value||'Ekstraklasa';const team=selects[2]?.value||'Pogoń Szczecin';const btn=[...document.querySelectorAll('button')].find(b=>/START SCOUTING/i.test(b.textContent));btn&&(btn.disabled=true,btn.textContent='INITIALIZING…');const s=await FOSI.startScouting(country,competition,team);$('#liveStatus')&&($('#liveStatus').textContent='SCOUTING INITIALIZING · '+s.team_name);if(TRIGGER_URL){try{const r=await fetch(TRIGGER_URL,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({country,competition,team})});if(!r.ok)throw new Error('trigger '+r.status);s.status='collecting';FOSI.setScouting(s);$('#liveStatus')&&($('#liveStatus').textContent='COLLECTING DATA · '+s.team_name);}catch(e){console.warn('FOSI trigger:',e);s.status='trigger_error';FOSI.setScouting(s);$('#liveStatus')&&($('#liveStatus').textContent='TRIGGER NOT AVAILABLE');}}else $('#liveStatus')&&($('#liveStatus').textContent='SCOUTING SESSION READY · TRIGGER PENDING');btn&&(btn.textContent='SCOUTING ACTIVE');}
async function initScouting(){const existing=FOSI.getScouting();if(existing){FOSI.lockTeam(existing);$('#liveStatus')&&($('#liveStatus').textContent='SCOUTING ACTIVE · '+existing.team_name);return;}const btn=[...document.querySelectorAll('button')].find(b=>/START SCOUTING/i.test(b.textContent));if(btn)btn.addEventListener('click',startScouting);}
loadFosi();setInterval(loadFosi,60000);import('./scouting.js').then(initScouting).catch(()=>{});