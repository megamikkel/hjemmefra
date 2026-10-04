# ADR-0002: CP-SAT for joint plan + basket optimization

**Status:** Accepted

## Context
Meal selection, package counts, store assignment, pantry consumption and
leftover allocation are coupled integer decisions. Greedy/brute force is either
wrong or combinatorially infeasible.

## Decision
Model the problem as a constraint program solved by OR-Tools CP-SAT with
integer øre and integer base units (g / ml / stk). Multi-buy and min/max
quantity price rules are expressed exactly through `AddElement` lookup tables
computed by the deterministic pricing engine, so the solver never approximates a
checkout price. Candidate pruning (hard filters → coverage → ranking → Top-K)
keeps the model small. One worker and a fixed seed give reproducible results;
`num_search_workers` can be raised for throughput at the cost of determinism.

Status mapping: OPTIMAL / FEASIBLE / TIME_LIMIT / INFEASIBLE / ERROR. A
FEASIBLE or TIME_LIMIT result is always labelled as "not proven optimal".

## Alternatives considered
- MIP (PuLP/CBC): workable, but multi-buy tables are more natural in CP-SAT.
- Heuristics only: fast but cannot prove infeasibility or report minimum budget.
