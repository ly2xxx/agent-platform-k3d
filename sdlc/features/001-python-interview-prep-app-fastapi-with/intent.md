<!-- sdlc stage=intent model=glm-5.3:cloud from=idea@f4c4cfa -->
# Intent: Python interview-prep app: multiprocessing vs asyncio comparison plus order book module

**Owner:** @ly2xxx · **Status:** proposed (approving the review gate approves it)

## Problem
Engineers preparing for Python interviews lack a small, runnable example that demonstrates, on the same CPU-bound task, why multiprocessing and asyncio behave differently and by how much. Textbook explanations give numbers without context, so candidates can't see the real timing difference on their own machine, and they also need a compact, idiomatic data-structures example (a heap-based order book) to study from.

## Outcome
A small Python app built with FastAPI exposes two REST endpoints that each run the same CPU-bound task — a Monte Carlo option-pricing simulation — one via multiprocessing and one via asyncio, and return their timings so the caller can compare the approaches directly. Alongside it, a small data-structures module implements an order book backed by a heap. The repository files don't make a module location clear, so the later stages should propose one.

## Done when
- A FastAPI app exists with two REST endpoints that both execute the same Monte Carlo option-pricing task.
- One endpoint performs the task via multiprocessing, the other via asyncio.
- Each endpoint returns timing information sufficient to compare the two approaches side by side.
- A separate module implements an order book using a heap as its core structure.
- The existing tests still pass.

## Not in scope
- Any UI beyond the REST endpoints themselves.
- Real-market data, persistence, or authentication of any kind.
- Additional concurrency strategies beyond the two named (e.g., threading, task queues, async process pools).
- Non-option-pricing Monte Carlo variants or other data structures.
- Deployment to the Kubernetes/Helm platform already in this repository.

## Open questions
None
