"""The v2 agent kernel: a bounded hypothesis loop.

Everything in this package is control flow, and none of it is configurable. Teams extend the
agent by contributing probes (`src/agent/probes/`), playbooks, and policy — never by editing
the loop. See the architecture plan for why that boundary is drawn here.
"""
