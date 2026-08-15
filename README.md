# VEX U Override Decision-Support & Simulation Tool

A decision-support tool for VEX U Robotics Competition (Override, 2026-2027 season): which
combination of capabilities across a team's 24" robot and 15" robot is most likely to remain
competitive at late-season events and at the VEX Robotics World Championship?

This is an early-stage project. See [`CLAUDE.md`](CLAUDE.md) for the project's operating rules,
current milestone, and layout, and [`docs/roadmap.md`](docs/roadmap.md) for the full plan.

## Status

**Session A (M0) and Session B (M1) are complete.** Rules foundation/provenance (M0) and
deterministic scoring (M1) both exist. Simulation, empirical/statistical modeling, and UI do not
exist yet.

## Setup

```bash
pip install -e ".[dev]"
pytest
```
