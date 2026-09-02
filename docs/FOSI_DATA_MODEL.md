# FOSI — Data Dictionary & Universal Data Model

## Purpose

FOSI separates **RAW evidence** from **normalized data**, derived metrics and scouting intelligence. RAW is immutable evidence: fields are never discarded simply because the current dashboard does not use them.

Pipeline:

`RAW → NORMALIZED → METRICS → PATTERNS → INTELLIGENCE → PRESENTATION`

## Universal entities

| Entity | Purpose | Typical fields |
|---|---|---|
| `competition` | Competition identity/context | id, name, country, season |
| `team` | Team identity | id, name, country, stadium |
| `season` | Temporal scope | season_id, start, end |
| `match` | One match | id, date, competition, home, away, score, status |
| `lineup` | Starting XI and bench | match_id, player_id, starter, position |
| `player` | Player identity/profile | id, name, position, team |
| `player_match` | Player participation | match_id, player_id, minutes, starter, substitute |
| `event` | Match event | minute, type, player, team, outcome |
| `shot` | Shot/finalization event | x, y, xG, outcome, body_part, player |
| `pass` | Pass event when available | x, y, end_x, end_y, outcome, player |
| `possession_sequence` | Possession/sequence when reconstructable | start/end, team, duration, actions |
| `team_match_stats` | Team-level match statistics | possession, shots, passes, duels, etc. |
| `player_match_stats` | Player-level match statistics | minutes, shots, passes, duels, etc. |
| `spatial_action` | Generic spatial action | action_type, x, y, end_x, end_y |
| `heatmap` | Spatial density | player/team, coordinates/bins |
| `news` | Public contextual information | date, title, url, source |
| `source_record` | Provenance | source, retrieved_at, raw_path, quality |

## Normalization rules

1. Preserve provider IDs alongside the FOSI canonical ID.
2. Preserve `source` and `retrieved_at` for every normalized record.
3. Preserve the original RAW path for auditability.
4. Store missing values as `null`; never convert missing into zero.
5. Distinguish `0` from `null`.
6. Keep competition type (`league`, `cup`, `friendly`, `European`, etc.) so friendlies can be excluded from league analysis without deleting them.
7. Keep event timestamps in seconds/minutes where possible and retain the provider timestamp too.
8. Keep coordinates in provider-native form plus a normalized pitch representation when conversion is reliable.
9. Do not combine provider statistics by simple averaging when the providers use different definitions.
10. When two sources disagree, retain both observations and assign provenance rather than silently overwriting one.

## Metric families

### Results
- W/D/L
- points
- goals for/against
- goal difference
- clean sheets

### Chance creation
- xG
- xGA
- xG/shot
- shots/90
- shots on target/90
- big/high-value chances when explicitly available

### Possession & progression
- possession
- passes and pass accuracy
- progressive actions when available
- final-third entries
- penalty-area entries
- crossing

### Defensive
- shots conceded
- xGA
- tackles
- interceptions
- recoveries
- duels
- aerial duels
- blocks/clearances when available

### Transitions
Derived only where event/sequence data is sufficient:
- possession regain → attack
- possession loss → defensive response
- transition shots
- transition xG
- counterattack frequency when identifiable

### Spatial
- shot maps
- conceded-shot maps
- xG maps
- heatmaps
- action zones
- left/centre/right distribution
- thirds of pitch

### Players
- minutes
- starts/sub appearances
- goals/assists
- xG/xA where available
- shots
- passing
- progression
- defensive actions
- duels
- recoveries/losses

### Set pieces
- corners for/against
- free kicks
- shots/goals from set pieces where identifiable
- delivery zones
- second-ball events when reconstructable

### Game state
Metrics should be split by score state where sample size allows:
- winning
- drawing
- losing

## Presentation model

The dashboard should not expose every raw field. It should expose decisions and evidence:

1. **Overview** — current form, KPIs, sample size, data quality.
2. **Team DNA** — attack, defence, possession, progression and transition profile.
3. **Attack** — shot map, xG, creation zones, progression.
4. **Defence** — conceded shots/xGA, vulnerable zones, defensive activity.
5. **Transitions** — regain/loss behaviour where supported by data.
6. **Players** — player profiles and comparable metrics.
7. **Key Players** — evidence-based threat/importance rankings with component metrics visible.
8. **Set Pieces** — attacking and defensive ABP.
9. **Game State** — behaviour while winning/drawing/losing.
10. **Matches** — match-by-match evidence and event detail.
11. **Trends** — rolling and period comparisons.
12. **Evidence** — source, match and event trail behind conclusions.
13. **Match Plan** — How to Defend / How to Attack, generated only from sufficiently supported patterns.

## Confidence

Every analytical conclusion should carry a confidence level based on:
- sample size;
- data completeness;
- source quality;
- consistency across matches;
- whether the metric is directly observed or derived.

A hypothesis must never be displayed as a fact. The UI should distinguish **Observed**, **Derived**, **Pattern**, and **Scouting Recommendation**.

## Current Pogoń source reality

- FotMob: primary acquired public structured source.
- Ekstraklasa/official competition pages: contextual/news source, currently partial.
- SofaScore: attempted but currently HTTP 403; no data should be inferred from it.
- Understat: not applicable to Ekstraklasa.
- FBref and Transfermarkt remain compliance-gated and should not be automated unless an appropriate access basis exists.
