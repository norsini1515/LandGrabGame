# Economic Systems

---

## Overview

The economic layer is the game's core. Every other system — terrain, population, military — exists to feed into or constrain the economic simulation. The goal is to create a game where financial decisions are as important as land decisions, and where the two are deeply coupled.

---

## Land Acquisition

- Players can purchase unowned land tiles they currently occupy (Monopoly-style)
- Land has a base value determined by terrain type
- Once owned, a tile can be developed
- Land value is **dynamic** — see Land Valuation Model below
- Unowned land generates no income; owned undeveloped land generates minimal income; value accrues through development

---

## Terrain Development Ladder

Development is **gated and sequential**. You cannot skip steps. The development state of a tile is a flyweight reference — transitioning a tile's development is a single reference change.

```
Raw Land
  └─► Dredge (marsh only) / Clear (forest, jungle) / Grade (hills)
        └─► Make Arable (eligible terrain only)
              └─► Urbanize (if eligibility criteria met)
                    └─► Build (buildings unlocked by urban status)
```

Early game is deliberately slow — infrastructure must be built before advanced options unlock. This ensures land grabs matter early, even before tiles can be fully developed. Players interact with markets and accumulate capital during the early development phase.

### Tile Improvements (Non-Building Infrastructure)

Improvements are infrastructure overlays on tiles, separate from buildings:

| Improvement | Effect |
|---|---|
| **Roads** | Halve movement cost; lower trade transport costs |
| **Canals** | Enable water-based movement and trade on inland tiles |
| **Bridges** | Connect tiles across water features |
| **Outposts** | Extend vision range |
| **Farms** | Agricultural output (grain, produce) |
| **Mines** | Mineral extraction (iron ore, copper, coal) |
| **Logging Facilities** | Lumber output |
| **Camps** | Temporary resource extraction (no permanent yield) |

---

## Buildings & Urban Centers

### Urbanization

A tile must complete the development ladder before urbanizing. Urban tiles unlock the full building slate. Each urban tile has a maximum of **3 buildings**. Building **tier** is gated by the **population of the metropolitan area** — the agglomeration of adjacent urban tiles.

### Metropolitan Agglomeration

Adjacent urban tiles form a **metropolitan area**. Combined population determines the maximum building tier across the entire metro. Agglomeration creates compounding value: more tiles urbanized together → higher population ceiling → higher-tier buildings → more output → more value.

### Building Types

| Building | Function |
|---|---|
| **Marketplace** | Trade hub; enables goods flow; generates toll income for owner |
| **Bank** | Financial services; loans, bonds, interest income |
| **Granary / Warehouse** | Resource storage; buffer against supply shocks; third-party storage for rent |
| **Hospital** | Population health; reduces plague mortality |
| **Cathedral** | Amenity; population attraction; tithe income |
| **Tavern** | Amenity; population attraction; casino minigame access |
| **Docks / Port** | Enables vessels; sea trade; exploration missions |

### Building Tier Scaling

| Building | Tier 1 | Tier 2 | Tier 3 |
|---|---|---|---|
| **Marketplace** | Local trade only | Regional pull; goods route through | Dominant hub; warps trade geography |
| **Granary** | Small buffer | Medium buffer | Large buffer; extends trade reach; amplifies marketplace pull |
| **Port** | 1 small vessel | Medium fleet | Large fleet + condottieri docking |

### Institution Race

Key institutions (marketplace, bank, docks) are **globally locked** until the first instance is built by any player. The player who builds it **owns** it. Other players pay a small tax to use it. This creates a first-mover race meta in the early-mid game. Higher-tier versions of institutions provide greater reach and capability.

### Building Interactions

Players visiting another player's urban center can interact with their buildings:

- **Bank** — take loans, purchase bonds, manage financial instruments
- **Docks** — discuss port expansions, secure voyage funding
- **Tavern / Casino** — minigames; wager liquid assets, property, or other assets
- **Cathedral** — pay tithes; receive boons
- **Marketplace** — buy/sell goods; negotiate contracts

---

## Population System

### Requirements

Population requires:
- **Food supply** — grain, baked goods (from own farms or imports)
- **Amenities** — hospital, cathedral, tavern attract and retain population

Failure to maintain either causes stagnation or decline.

### Growth Loop

```
Food Supply → Supports Population → Demands Amenities
     ↑                                       ↓
Infrastructure                  Amenities Attract Population
     ↑                                       ↓
Higher Tier Buildings ←── Higher Population ←┘
```

### Decline Pathways

**Catastrophic Collapse** (sudden, large-scale):
- Plague event (from historical event engine)
- Severe famine from supply chain failure

**Structural Decline** (slow burn):
- Bad farming practices / soil exhaustion
- Resource mismanagement
- Failure to invest in agricultural infrastructure

**Economic Exodus** (player-driven):
- Over-taxation
- Failure to provide amenities
- Food prices spiking due to poor trade management
- People leave for more attractive rival cities — a competitor with a well-run city may absorb your population loss as their gain

### Food Storage & Granaries

Granaries provide a buffer against single bad harvest events or supply disruptions. A well-stocked granary buys approximately 2–3 turns to find alternative supply before famine triggers. Strategic question: how much storage capacity to maintain vs. capital deployed elsewhere? Third parties can rent storage space in your granaries (rent income to owner).

---

## Land Valuation Model

Land value is a function of own tile characteristics plus spatial spillover from neighbours. The `land_value` field is **dirty-flagged**: it is marked stale when inputs change and recomputed lazily on next access.

### Formula

```
V(tile) = α·Capital + β·AvgOutput(5 turns) + γ·Activity + Σ Spillover(neighbor_i) / d²
```

Where:
- `d` = distance in tiles to neighbour
- `Spillover` = function of neighbour's development, buildings, and urban status
- `α, β, γ` = tunable weights

### Own Tile Components

**Capital Value**
- Value of all improvements and buildings on the tile
- Relatively stable; changes only on build/upgrade events

**Income Value (trailing 5-turn average)**
- Average output over the last 5 turns
- Smooths volatility from the event engine — a plague year does not permanently crater value
- Prevents feel-bad moments from single catastrophic events

**Activity Value**
- Employment + visits to the tile
- Endogenous to player behavior — a well-trafficked tavern is worth more than an empty one
- A tile on a major trade route has higher activity than one in a corner of the map
- Randomized component adds natural variance

### Employment (Derived Quantity)

Employment is not set directly — it **emerges** from:
- Total output of the tile
- Influence and tier of buildings present
- Population of the metropolitan area
- Dependency chain: Population → Building Tiers → Output Capacity → Employment → Activity Value → Land Valuation

### Spatial Spillover

- **Positive spillover**: An urban center raises the value of adjacent farm tiles
- **Negative spillover**: A mine or tannery next to a residential area decreases adjacent value
- **Radius parameter X**: Tunable dial — small radius = local/tactical; large radius = highly interdependent map
- Implemented as a vectorized matrix operation over the N×M grid (numpy-friendly, similar to a convolution)

### Land Speculation

The valuation model makes **speculation a viable strategy**: buy undeveloped tiles adjacent to a competitor's growing urban center and profit passively from their development spillover. No development required — the investor profits from someone else's activity.

---

## Trade Goods & Market System

### Trade Goods (Partial List)

**Raw goods**: grain, iron ore, copper ore, lumber, wool, fish, coal
**Processed goods**: cloth, silk, tools, glass (stained), baked goods, cut gems
**Import goods**: silk, spices — flow in from outside the map via the external market engine (generated by the event engine, not by any player)

### Production Chains

Raw goods can be exported cheaply or processed into higher-value finished goods. Processing requires appropriate buildings (e.g. a textile workshop for wool → cloth) and adds value but requires capital investment.

Strategic axis: **export raw cheaply** (fast cash, simple logistics) vs **invest in processing capacity** (higher margins, more infrastructure).

### Trade Routing

Goods do not teleport — they move **physically through tiles**. Trade routes are defined paths between origin and destination tiles. Transport costs accumulate as goods move through tiles, scaled by road/canal presence.

A player who owns tiles along a trade route can **extract toll income** from passing goods. This makes strategic land placement along trade corridors high-value.

### Market Dynamics

- Multiple players competing for the same commodity apply **downward price pressure**
- A player controlling a large share of grain production can squeeze the food supply of rival cities
- **Player market influence**: large supply actions by a single player move prices — this is not a perfectly competitive market
- The event engine sets **baseline commodity prices** (see Financial Engine); player actions create deviations from those baselines

---

## Financial Engine

### Historical Event Engine

A random draw each turn from a pool of historically grounded medieval events that affect baseline commodity prices and interest rates:

- **Plague** — population collapse in affected regions; demand for grain falls, demand for medicine rises
- **Famine** — crop failure; grain prices spike
- **Trade disruption** — piracy, blockade, or political conflict closes a major route; goods that relied on it become scarce
- **Mini Ice Age / Harsh Winter** — agricultural output drops; heating goods premium
- **Religious Conflict** — tithes and cathedral revenues modified
- **Mercenary Scarcity** — condottieri become more expensive and harder to contract
- **Mining Boom** — metal prices fall; processed goods become cheaper
- **Port Expansion** — new external market supply of import goods opens

Events serve as **exogenous shocks** that can break economic spirals. A snowballing player's dominant city getting hit by plague resets the playing field.

### Loans and Bonds

- **Loans**: taken at a bank; repaid over N turns with interest
- **Bonds**: issued by players (via their bank); other players or AI can purchase them; fixed coupon rate, maturity date
- **Interest rates** are set by the event engine's baseline and modified by individual bank tier and player creditworthiness

### Derivatives Layer

The game includes a **futures and swaps layer** on trade goods — mechanically inspired by historical medieval commodity finance.

**Futures contracts**:
- Lock in a purchase or sale of a trade good at a fixed price for delivery N turns in the future
- Strategic use: hedge against event engine shocks (buy grain futures before a famine you anticipate)
- Speculative use: profit from price movements without holding physical goods

**Swaps**:
- Exchange streams of income — e.g. swap a fixed toll income stream for a variable trade revenue stream
- Allows players to restructure their income profile without selling underlying assets

**Financial Instrument Collectible Variant (optional)**:
- Instruments appear as tokens on the game board
- Players race to physically reach and acquire them
- Alternative: accessed via menu interaction at a bank building on your turn

---

## Naval & Military System

### Design Philosophy

Military force exists **only as an economic tool**. It cannot capture tiles or destroy buildings. It can only **disrupt economic flows**. A purely military strategy cannot win — you must win economically.

### Own Navy

Built at ports; capacity scales with port tier:

| Port Tier | Fleet Capacity |
|---|---|
| 1 | 1 small vessel |
| 2 | Medium fleet |
| 3 | Large fleet + can dock/service condottieri fleets (rent income) |

**Naval purposes**:
- Exploration missions (multi-turn; fog-of-war removal; new tile discovery)
- Trade route protection
- Coastal patrol

### Condottieri (Rented Military)

Historical mercenary companies available for hire under contract.

**Contract structure**:
- Player selects a named fleet/company (e.g. "3rd Fleet of Genoa")
- **Delivery delay** of Y turns before they arrive and are available
- Contract lasts N turns; renewable at current market rate
- Named units have specific capabilities and characteristics

**Market dynamics**:
- Named fleets are **scarce** — if another player has contracted the 3rd Fleet of Genoa, it is unavailable to you
- Prices fluctuate based on demand and the event engine (instability = more expensive)
- **Reliability risk**: condottieri historically were unreliable; random chance of underperformance built into each contract

**Available actions**:
- Blockade a rival's port (disrupts trade flow and vessel operations)
- Protect your own trade fleet on a specific route
- Break a rival's blockade
- Escort merchant vessels through contested waters

### Counter-Strategies (No Combat Required)

Military is not the only answer to a dominant player:
- **Cut food supply** — disrupt grain contracts; cause population decline in their cities
- **Alternative routing** — build infrastructure that bypasses their trade hub
- **Financial warfare** — manipulate futures on goods they depend on
- **Compete for population** — make your city more attractive so their workers leave

---

## AI Player System

### Archetype Vectors

AI player behavior is modeled as a set **P** of archetype vectors. Each AI player is a **weighted linear combination** of four archetypes:

| Archetype | Focus |
|---|---|
| **Merchant** | Aggressively plays trade and futures markets |
| **Landlord** | Focuses on land acquisition and toll extraction |
| **Builder** | Races to urbanize and control institutions |
| **Speculator** | Watches the event engine; positions to profit from shocks |

An AI player with weights `[0.6, 0.2, 0.1, 0.1]` is primarily a merchant with minor diversification into landlord and builder strategies.

### Key Design Principle

Diffuse AI (spread across multiple archetypes) is **not inherently weaker** than specialist AI. A pure landlord AI is easy to counter once identified. A diffuse AI may stumble into good moves across multiple domains that a specialist would ignore. Average decision quality is lower per decision, but variance in outcomes can make it harder to play against in certain matchups.

### Decision Architecture

Each turn, an AI player:
1. Scores available actions by expected value contribution to their weighted objective function
2. Applies archetype weights to bias the scoring
3. Selects the highest-scoring feasible action

Implementation detail: the AI evaluates its current position against all four archetype scoring functions simultaneously, weighs them by the archetype vector, and picks the highest combined score action. This is a weighted linear combination at decision time, not strategy switching.
