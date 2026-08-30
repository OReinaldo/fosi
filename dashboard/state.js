const KEY='fosi.activeScouting';
export function getState(){try{return JSON.parse(localStorage.getItem(KEY)||'null')}catch{return null}}
export function startScouting(team,competition,country){const state={id:`${country}-${competition}-${team}`.toLowerCase().replace(/[^a-z0-9]+/g,'-'),country,competition,team,startedAt:new Date().toISOString(),status:'INITIALIZING',locked:true};localStorage.setItem(KEY,JSON.stringify(state));return state}
export function clearScouting(){localStorage.removeItem(KEY)}
