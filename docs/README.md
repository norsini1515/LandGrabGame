# Land Game — Documentation Index

> A medieval economic strategy game. Conceived 2018. Development started May 2026.

---

## Documents

| File | Contents |
|---|---|
| [`01_game_design_document.md`](01_game_design_document.md) | Vision, win condition, core game loop, map, UI map modes, starting conditions |
| [`02_terrain_system.md`](02_terrain_system.md) | All 14 terrain types, movement system, full 8-pass generation pipeline, adjacency matrix, world settings, terrain.config reference |
| [`03_economic_systems.md`](03_economic_systems.md) | Development ladder, buildings, population, land valuation, trade goods, financial engine, derivatives, military/condottieri, AI archetypes |
| [`04_algorithms.md`](04_algorithms.md) | Mathematical formulas: movement, hills scalar, terrain generation, land valuation, AI scoring, financial instrument pricing, render pipeline |
| [`05_architecture.md`](05_architecture.md) | Tech stack, package structure, core data classes, design patterns, simulation layer breakdown, testing strategy, milestones |
| [`06_design_notes.md`](06_design_notes.md) | Resolved decisions, open questions, deferred ideas, implementation gotchas |

---

## Quick Reference

**Win condition**: highest total asset value at turn limit or first to reach value threshold.

**Core stack**: Python + numpy/scipy + pygame (prototype renderer).

**Key patterns**: config-driven, flyweight terrain types, dirty-flag land value, render-time map modes.

**Next milestone**: renderable procedurally generated map (Perlin → ocean → rivers → terrain seeds → expansion → hills → pygame display).

**Do not**:
- Store render colors on tiles
- Normalize adjacency matrix rows (columns only)
- Compute land value eagerly
- Add Jupyter notebooks

---

## Thematic Inspiration

Set in loosely 14th-century Europe with Dutch/Flemish marshland colonization and drainage history as the primary geographic and cultural reference. The default world preset ("Low Countries") produces a flat, marsh-heavy map with abundant coastal terrain — mechanically and aesthetically distinct from the generic fantasy setting of most tile-based strategy games.

The game is at the intersection of:
- **Monopoly** — land acquisition, property rent, player interaction
- **Civilization** — tile map, terrain variety, development ladder  
- **EU4 / Victoria 3** — deep economic simulation, trade flows, financial instruments
