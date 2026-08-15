# VEX U Override Decision-Support & Simulation Tool

A decision-support tool for VEX U Robotics Competition (Override, 2026-2027 season): which
combination of capabilities across a team's 24" robot and 15" robot is most likely to remain
competitive at late-season events and at the VEX Robotics World Championship?

This is an early-stage project. See [`CLAUDE.md`](CLAUDE.md) for the project's operating rules,
current milestone, and layout, and [`docs/roadmap.md`](docs/roadmap.md) for the full plan.

## Status

**M0, M1, and M2 are complete.** Rules foundation/provenance (M0), deterministic scoring (M1), and
official starting Field states (M2) all exist. **M3 (observation schema and labeling) is next.**
Simulation, empirical/statistical modeling, and UI do not exist yet.

## Setup

```bash
pip install -e ".[dev]"
pytest
```
