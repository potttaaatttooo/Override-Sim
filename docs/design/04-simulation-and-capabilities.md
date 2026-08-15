# Simulation and capabilities (stub)

Not written yet. Deliberately deferred to M6 (see `docs/roadmap.md`) so that the spatial/travel
model, the discrete-event architecture, and the robot capability vector are designed against
measured parameters (M5) rather than guesses made before any real match data has been looked at.

When written, this document will cover: the replaceable spatial/travel-time interface (starting
region-based, upgradable to a graph or coordinates only if observed data shows it matters), the
discrete-event engine's event types and RNG-substream discipline, the robot capability vector, the
24"/15" pairing, and the duplicate / specialize-to-24 / specialize-to-15 / omit taxonomy that is
this project's actual analytical output.

No spatial model, event loop, or capability representation exists in code yet — see `CLAUDE.md`
"Current milestone."
