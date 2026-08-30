const $ = (s) => document.querySelector(s);
async function loadFosi(){
  try{
    const r=await fetch('./data.json?ts='+Date.now());
    if(!r.ok) throw new Error('data.json '+r.status);
    const d=await r.json();
    document.querySelectorAll('[data-team]').forEach(e=>e.textContent=d.team?.name||'—');
    const m=d.metrics||{};
    const map={form:m.form,goals:`${m.goals_for??'—'} / ${m.goals_against??'—'}`,xg:m.xg,xga:m.xga,threat:d.threat_score,data:d.data_quality?.score};
    Object.entries(map).forEach(([k,v])=>document.querySelectorAll(`[data-kpi="${k}"]`).forEach(e=>e.textContent=v==null?'—':v));
    const q=d.data_quality?.score??0; $('#coverageBar')?.style.setProperty('width',q+'%'); $('#coverageText')&&( $('#coverageText').textContent=q+'%' );
    const state=d.status==='awaiting_verified_ingestion'?'Awaiting verified data':'Live dataset';
    $('#liveStatus')&&( $('#liveStatus').textContent=state );
    renderInsights(d.insights||[]);
  }catch(e){console.warn('FOSI data load:',e); $('#liveStatus')&&( $('#liveStatus').textContent='Data unavailable' );}
}
function renderInsights(items){
 const box=$('#insights'); if(!box) return;
 box.innerHTML=items.length?items.map(x=>`<article><b>${x.title||'Insight'}</b><small>${x.evidence||''}</small><em>${x.confidence??'—'}/100</em></article>`).join(''):'<article><b>Evidence engine ready</b><small>Insights will appear only after verified match data is available.</small><em>—</em></article>';
}
loadFosi();
setInterval(loadFosi,60000);
