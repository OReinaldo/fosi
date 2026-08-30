const FOSI_SCOUTING_KEY='fosi_active_scouting';
const FOSI_CATALOG='./catalog.json';
async function fosiCatalog(){const r=await fetch(FOSI_CATALOG+'?ts='+Date.now());if(!r.ok)throw Error('catalog unavailable');return r.json()}
function getScouting(){try{return JSON.parse(localStorage.getItem(FOSI_SCOUTING_KEY)||'null')}catch{return null}}
function setScouting(s){localStorage.setItem(FOSI_SCOUTING_KEY,JSON.stringify(s))}
function clearScouting(){localStorage.removeItem(FOSI_SCOUTING_KEY)}
function lockTeam(s){document.querySelectorAll('[data-scout-team]').forEach(e=>{e.textContent=s.team_name});document.body.classList.add('scouting-locked')}
function scoutingStatus(s){return {status:s?.status||'idle',team:s?.team_name||null,started_at:s?.started_at||null,updated_at:s?.updated_at||null,coverage:s?.coverage??0}}
async function startScouting(country,competition,team){const s={id:`${competition}--${team}--${Date.now()}`,country,competition,team,team_name:team,status:'initializing',coverage:0,started_at:new Date().toISOString()};setScouting(s);lockTeam(s);return s}
window.FOSI={catalog:fosiCatalog,getScouting,setScouting,clearScouting,lockTeam,scoutingStatus,startScouting};
