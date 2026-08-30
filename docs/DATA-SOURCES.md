# FOSI data-source strategy

FOSI uses an on-demand, multi-source model. We do **not** mirror every league into a permanent giant database. When a user selects a team, the pipeline refreshes the deepest available dataset for that team.

## Priority layers

1. **FotMob** — match detail, events, lineups, statistics and shotmap when exposed.
2. **FBref** — season/player/goalkeeping/shooting and fixture context.
3. **Transfermarkt** — squad, transfers, market context and public availability information.
4. **Sofascore** — complementary match/event/stat/shot information and heatmaps where publicly available.
5. **Understat** — xG/xGA/shot context where the competition is covered.
6. **Official club sources** — squad confirmation, news, press material and official video.

Every field should retain `source`, `retrieved_at` and `confidence`. Conflicts are preserved rather than silently overwritten.

## Target dashboard layers

- Executive overview
- Recent form
- Season performance
- Squad / player intelligence
- Chance creation and prevention
- Shotmap / xG
- Possession and passing
- Progression / territory
- Defensive actions
- Transitions
- Set pieces
- Game-state splits
- Home/away splits
- Tactical patterns
- Strengths / weaknesses
- Video evidence
- Match plan
- PDF export

Spatial and event layers are only rendered when source coverage supports them.
