# Explain a dashboard with no ranked candidates

> Status: ready
> Deps: []
> Release: R1
> Tags: dashboard, usability
> Appetite: small

## Intent

A project with unranked Stories sees “No dashboard candidates match the current
filters,” even when filters are not the cause. Explain how to find the work
and what populates the dashboard.

## Acceptance criteria

- Distinguish no delivery items, filtered-out candidates, and work without ranking/recommendations.
- Offer a work-index or roadmap route that reveals existing work.
- Explain recommendation/assessment setup only when relevant.
- Cover a ready unranked Story, a ranked but filtered Story and an empty graph.

## Evidence and scope

Observed on Vizzer's dashboard on 2026-09-05 with two delivery Stories and no
recommendations. Self-host configuration now supplies recommendations; the
generic UI still needs this change in `src/vizzer/render/constellation/views.js`.
