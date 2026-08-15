# Principles and scope

## The decision question

Which combination of capabilities across a VEX U team's 24" robot and 15" robot is most likely to
remain competitive at late-season events and at the VEX Robotics World Championship?

## Principles (project law)

1. The official Game Manual is a primary source of truth for rules, but not the *only* one:
   official V5RC/VEX U Q&A rulings are also binding rule provenance. See
   `05-data-provenance-and-validation.md`.
2. Official rules, simulation assumptions, and empirical parameters must be clearly separated —
   four data stores, never mixed in one file (`data/rules/`, `data/assumptions/`,
   `data/parameters/`, `data/observations/`).
3. Game rules must be versioned, because the Game Manual changes during the season (v1.1 today;
   v2.0/2.1/2.2/3.0/4.0 scheduled to follow).
4. Scoring and rule evaluation must be deterministic and must never depend on an LLM.
5. The simulator must eventually be reproducible from a random seed.
6. The initial simulator is a stochastic discrete-event simulator, not a detailed rigid-body
   physics simulator.
7. Robot architectures are represented by measurable capabilities, not CAD geometry.
8. A VEX U architecture is a coordinated 24" robot + 15" robot pair. The project's output is which
   capabilities should be duplicated, specialized to the 24" robot, specialized to the 15" robot,
   or omitted.
9. No machine learning where deterministic or statistical methods are sufficient.
10. No computer vision, automatic video labeling, optimization, or UI until the underlying
    simulation has been validated (see the staged gates in `05-data-provenance-and-validation.md`).
11. Never invent a Game Manual rule. Unclear items go through the rule-gap workflow in
    `CLAUDE.md` and, if genuinely unresolved, into `docs/open-questions.md` — never guessed.

## Non-goals right now

No physics engine, no CAD import, no ML, no computer vision, no UI, no web server, no
notebooks, no plotting. These may arrive in later milestones (`docs/roadmap.md`, M9+); none of
them are needed to answer the decision question at the fidelity this project starts at.

## V5RC / VEX U program separation

Real V5RC Override match video is available and will be used as empirical evidence — some match
mechanics (e.g. acquisition and placement mechanics) plausibly transfer from V5RC to VEX U, but
game structure does not (VEX U is 1v1 with two robots per team, different timing, different field
setup). Every piece of data in this project — rules, observations, parameters, matches — is
tagged with the program it came from, and V5RC-derived values are never silently treated as VEX U
truth. See `CLAUDE.md` "Program tagging" and `05-data-provenance-and-validation.md`.
