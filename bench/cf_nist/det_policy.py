"""Scripted (no-LLM) search policy for CADFather's harness: greedy det + optimize.

This REPLACES the `dialogue_lean` policy (the Qwen assistant) with a fixed rule. Everything else
(tool registry, det_cold/det_warm/optimize capabilities, candidate execution, scoring, budgets,
best-candidate selection) is CADFather's own harness code, unmodified.

Rule, one turn at a time:
  1. While the det_cold pool of the empty start is not used up: det_cold on the empty start, up to
     N_COLD ops per turn. (One det call; the pool is the list of pieces of cadfit's union assembly,
     primitives first, NOT sorted by gain, so the whole list is built and scored to pick the first op.
     Later slices of the same pool cost executions but no det call.)
  2. Otherwise look at the harness's best candidate (ranked by the harness score = mean(IoU, GMS_norm)):
       a. if `optimize` is legal on it and it was not itself produced by `optimize`: run optimize;
       b. else if `det_warm` is legal on it: run det_warm (next N_WARM ops of its pool);
     If neither is legal/affordable on the best, try the same on the next candidates by score
     (and det_cold alternatives on the empty start).
  3. If no action is legal/affordable anywhere, or the best has not changed for `patience` turns: finish.
"""
from __future__ import annotations

from cad_agent.harness.search_types import Action, Plan, SearchState


class DetGreedyPolicy:
    needs_assistant = False
    # `DialogueLeanPolicy.FIXED_N["rank_depth"]` is 4 (the assistant can re-ask for the next slice).
    # The pilot sweep (runs/pilot_n4) used 4 for both and did not drain the cold pool.
    N_COLD = 32
    N_WARM = 12

    def __init__(self, patience: int | None = None, use_optimize: bool = True,
                 n_cold: int | None = None, n_warm: int | None = None):
        self.patience = patience
        self.use_optimize = use_optimize
        self.n_cold = n_cold or self.N_COLD
        self.n_warm = n_warm or self.N_WARM

    def plan(self, state: SearchState) -> Plan:
        if (self.patience is not None and state.best_id is not None
                and state.iteration - state.best_set_iteration >= self.patience):
            return Plan(done=True, stalled=True,
                        reason=f"stalled: best unchanged for {self.patience} turns")

        by_parent: dict[str, dict[str, object]] = {}
        for legal in state.legal:
            by_parent.setdefault(legal.parent_id or "", {})[legal.tool] = legal

        # 1. drain the cold pool first
        for candidate in state.pool:
            legal = (by_parent.get(candidate.id) or {}).get("det_cold") if candidate.depth == 0 else None
            if legal is not None:
                n = state.affordable_n("det_cold", min(self.n_cold, legal.max_n))
                if n > 0:
                    return Plan(actions=[Action(tool="det_cold", parent_id=candidate.id, n=n,
                                                reason="scripted: drain det_cold pool")])

        def fitness(candidate):
            value = state.fitness_of(candidate)
            return -1.0 if value is None else float(value)

        ranked = sorted((c for c in state.pool if c.alive), key=fitness, reverse=True)
        order = []
        best = state.get(state.best_id) if state.best_id else None
        if best is not None:
            order.append(best)
        order += [c for c in ranked if best is None or c.id != best.id]
        order += [c for c in state.pool if c.depth == 0]

        for rank, candidate in enumerate(order):
            options = by_parent.get(candidate.id) or {}
            if not options:
                continue
            is_best = best is not None and candidate.id == best.id
            sequence = []
            if self.use_optimize and is_best and candidate.origin.tool != "optimize":
                sequence.append("optimize")
            sequence += ["det_warm", "det_cold"]
            for tool in sequence:
                legal = options.get(tool)
                if legal is None:
                    continue
                want = 1 if tool == "optimize" else self.n_warm
                n = state.affordable_n(tool, min(want, legal.max_n))
                if n <= 0:
                    continue
                return Plan(actions=[Action(tool=tool, parent_id=candidate.id, n=n,
                                            reason=f"scripted: {tool} on rank-{rank} candidate")])
        return Plan(done=True, stalled=True, reason="stalled: no legal affordable action left")


def entrypoint() -> DetGreedyPolicy:
    return DetGreedyPolicy()
