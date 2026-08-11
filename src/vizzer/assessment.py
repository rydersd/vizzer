"""Deterministic delivery-size, impact, and parallel-safety assessment.

The assessor deliberately does not collapse its outputs into one magic score.
Delivery size is a forecast about work, impact is a statement about graph
leverage, and parallel safety is a coordination claim.  Mixing those claims
would make an attractive number whose provenance nobody could audit.

The assessment functions are pure: callers supply normalized graph records
and discovered evidence.  The opt-in ``apply_assessments`` adapter scans only
configured in-project sources and then calls that core.  No path invokes a
network, model, or clock, so the same repository state produces the same
assessment for Claude, Codex, Gemini, a local model, or a human client.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
import re
from typing import Mapping, Sequence

from .model import Graph, Item


SIZE_BANDS = ("XS", "S", "M", "L", "XL")
DIMENSIONS = ("implementation", "verification", "integration", "coordination")
PROVENANCE = ("observed", "authored", "inferred", "unknown")

_BAND_INDEX = {band: index for index, band in enumerate(SIZE_BANDS)}
_ALIASES = {
    "xs": "XS", "x-small": "XS", "extra-small": "XS", "extra small": "XS",
    "tiny": "XS", "trivial": "XS", "1": "XS",
    "s": "S", "small": "S", "short": "S", "2": "S", "3": "S",
    "m": "M", "medium": "M", "med": "M", "moderate": "M", "5": "M",
    # Explicit range aliases use their conservative upper bound. The raw value
    # remains in the profile and uncertainty widens the plausible range.
    "small-to-medium": "M", "small-medium": "M", "small–medium": "M",
    "small/medium": "M",
    "l": "L", "large": "L", "big": "L", "8": "L",
    "medium-to-large": "L", "medium-large": "L", "medium–large": "L",
    "medium/large": "L",
    "xl": "XL", "x-large": "XL", "extra-large": "XL", "extra large": "XL",
    "huge": "XL", "epic": "XL", "large batch": "XL", "13": "XL", "13+": "XL",
}


@dataclass(frozen=True)
class AssessmentSignals:
    """Evidence supplied by adapters or an explicit assessment record.

    ``None`` means the scanner did not establish the fact.  An empty tuple
    means it did establish that the collection is empty.  That distinction is
    important: absence of dependency edges or test names is not evidence that
    a story is parallel-safe or cheap to verify.

    Dimension mappings accept the same exact aliases as ``normalize_appetite``.
    Observed dimensions take precedence over authored dimensions.  Acceptance
    check names describe a contract; only ``verified_checks`` plus an observed
    harness describe execution evidence.
    """

    observed_size: str | None = None
    observed_dimensions: Mapping[str, str] = field(default_factory=dict)
    authored_dimensions: Mapping[str, str] = field(default_factory=dict)
    observed_paths: tuple[str, ...] | None = None
    planned_surfaces: tuple[str, ...] | None = None
    verification_harnesses: tuple[str, ...] | None = None
    acceptance_checks: tuple[str, ...] | None = None
    harnessed_checks: tuple[str, ...] | None = None
    verified_checks: tuple[str, ...] | None = None
    integration_points: tuple[str, ...] | None = None
    coordination_parties: tuple[str, ...] | None = None
    write_surfaces: tuple[str, ...] | None = None
    serial_surfaces: tuple[str, ...] = ()
    parallel_evidence: tuple[str, ...] = ()
    unresolved_gates: tuple[str, ...] = ()
    unresolved_questions: tuple[str, ...] = ()
    scope_tokens: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()


def _coerce_signals(value: AssessmentSignals | Mapping | None) -> AssessmentSignals:
    if value is None:
        return AssessmentSignals()
    if isinstance(value, AssessmentSignals):
        value = asdict(value)
    if not isinstance(value, Mapping):
        raise TypeError("assessment signals must be an AssessmentSignals or mapping")
    allowed = set(AssessmentSignals.__dataclass_fields__)
    unknown = set(value) - allowed
    if unknown:
        raise ValueError("unknown assessment signal fields: " + ", ".join(sorted(unknown)))
    data = dict(value)
    for name in ("observed_dimensions", "authored_dimensions"):
        raw = data.get(name, {})
        if not isinstance(raw, Mapping) or not all(
            isinstance(key, str) and isinstance(entry, str)
            for key, entry in raw.items()
        ):
            raise TypeError(f"assessment signal {name} must be a string mapping")
        bad_dimensions = set(raw) - set(DIMENSIONS)
        if bad_dimensions:
            raise ValueError(
                f"assessment signal {name} has unknown dimensions: "
                + ", ".join(sorted(bad_dimensions))
            )
        bad_values = {
            key: entry for key, entry in raw.items()
            if normalize_appetite(entry) is None
        }
        if bad_values:
            rendered = ", ".join(
                f"{key}={entry!r}" for key, entry in sorted(bad_values.items())
            )
            raise ValueError(
                f"assessment signal {name} has unrecognized size values: {rendered}"
            )
        data[name] = dict(raw)
    for name in allowed - {"observed_dimensions", "authored_dimensions"}:
        if name not in data or data[name] is None or name == "observed_size":
            continue
        if isinstance(data[name], (str, bytes)) or not isinstance(data[name], Sequence):
            raise TypeError(f"assessment signal {name} must be a string sequence or null")
        if not all(isinstance(entry, str) and entry for entry in data[name]):
            raise TypeError(f"assessment signal {name} entries must be non-empty strings")
        data[name] = tuple(data[name])
    if "observed_size" in data and data["observed_size"] is not None \
            and not isinstance(data["observed_size"], str):
        raise TypeError("assessment signal observed_size must be a string or null")
    return AssessmentSignals(**data)


def normalize_appetite(raw: str | None) -> str | None:
    """Map an exact legacy appetite/point alias to XS--XL.

    Deliberately no substring guessing: ``"small-ish / medium"`` is a junk
    drawer, not an estimate, and silently blessing it would manufacture data.
    The caller retains ``raw`` alongside this normalized value.
    """
    if not isinstance(raw, str):
        return None
    token = " ".join(raw.strip().lower().replace("_", "-").split())
    return _ALIASES.get(token)


def _band_for_count(count: int, thresholds: tuple[int, int, int, int]) -> str:
    if count <= thresholds[0]:
        return "XS"
    if count <= thresholds[1]:
        return "S"
    if count <= thresholds[2]:
        return "M"
    if count <= thresholds[3]:
        return "L"
    return "XL"


def _explicit_dimension(signals: AssessmentSignals, name: str) -> dict | None:
    if name in signals.observed_dimensions:
        raw = signals.observed_dimensions[name]
        band = normalize_appetite(raw)
        if band:
            return {
                "band": band, "provenance": "observed",
                "evidence": [f"observed {name} assessment: {raw}"], "unknowns": [],
            }
        return {
            "band": None, "provenance": "unknown", "evidence": [],
            "unknowns": [f"unrecognized observed {name} assessment: {raw}"],
        }
    if name in signals.authored_dimensions:
        raw = signals.authored_dimensions[name]
        band = normalize_appetite(raw)
        if band:
            return {
                "band": band, "provenance": "authored",
                "evidence": [f"authored {name} assessment: {raw}"], "unknowns": [],
            }
        return {
            "band": None, "provenance": "unknown", "evidence": [],
            "unknowns": [f"unrecognized authored {name} assessment: {raw}"],
        }
    return None


def _dimension(name: str, signals: AssessmentSignals) -> dict:
    explicit = _explicit_dimension(signals, name)
    if explicit:
        return explicit

    if name == "implementation":
        if signals.observed_paths is not None:
            count = len(set(signals.observed_paths))
            return {
                "band": _band_for_count(count, (0, 2, 6, 14)),
                "provenance": "inferred",
                "evidence": [f"{count} observed implementation path(s)"],
                "unknowns": [],
            }
        if signals.planned_surfaces is not None:
            count = len(set(signals.planned_surfaces))
            # A named surface is broader than a path; do not call one surface XS.
            band = "XS" if count == 0 else _band_for_count(count, (0, 1, 3, 6))
            return {
                "band": band, "provenance": "inferred",
                "evidence": [f"{count} planned implementation surface(s)"],
                "unknowns": [],
            }
        missing = "implementation surface is not established"

    elif name == "verification":
        harnesses = signals.verification_harnesses
        checks = signals.acceptance_checks
        harnessed = signals.harnessed_checks
        verified = signals.verified_checks
        if harnesses is not None and harnesses:
            contract_count = len(set(checks or ()))
            harness_count = len(set(harnesses))
            band = _band_for_count(max(contract_count, harness_count), (0, 2, 6, 14))
            evidence = [f"{harness_count} observed verification harness(es)"]
            if verified:
                evidence.append(f"{len(set(verified))} check(s) have execution evidence")
            established = set(harnessed or ()) | set(verified or ())
            missing_checks = sorted(set(checks or ()) - established)
            unknowns = []
            if missing_checks:
                unknowns.append(
                    f"{len(missing_checks)} acceptance check name(s) lack an observed harness: "
                    + ", ".join(missing_checks)
                )
            return {
                "band": band, "provenance": "inferred", "evidence": evidence,
                "unknowns": unknowns,
            }
        if checks:
            # Names in prose are requirements, not proof that a harness exists.
            return {
                "band": None, "provenance": "unknown", "evidence": [],
                "unknowns": [
                    f"{len(set(checks))} acceptance check name(s) lack an observed harness"
                ],
            }
        if harnesses is not None and not harnesses and checks is not None and not checks:
            return {
                "band": "XS", "provenance": "observed",
                "evidence": ["verification contract and harness set are explicitly empty"],
                "unknowns": [],
            }
        missing = "verification harness is not established"

    elif name == "integration":
        if signals.integration_points is not None:
            count = len(set(signals.integration_points))
            return {
                "band": _band_for_count(count, (0, 1, 3, 6)),
                "provenance": "inferred",
                "evidence": [f"{count} integration point(s)"], "unknowns": [],
            }
        missing = "integration boundary count is not established"

    else:  # coordination
        if signals.serial_surfaces:
            return {
                "band": "L", "provenance": "inferred",
                "evidence": [
                    "serial surface(s): " + ", ".join(sorted(set(signals.serial_surfaces)))
                ], "unknowns": [],
            }
        if signals.coordination_parties is not None:
            count = len(set(signals.coordination_parties))
            return {
                "band": _band_for_count(count, (1, 2, 4, 7)),
                "provenance": "inferred",
                "evidence": [f"{count} coordination party/parties"], "unknowns": [],
            }
        missing = "coordination ownership is not established"

    return {"band": None, "provenance": "unknown", "evidence": [], "unknowns": [missing]}


def _canonical_scope(item: Item, signals: AssessmentSignals) -> dict:
    """Return only inputs whose change means the estimate describes old scope."""
    return {
        "item": item.id,
        "appetite": item.appetite,
        "deps": sorted(set(item.deps)),
        "relations": sorted((relation.kind, relation.target) for relation in item.relations),
        "authored_dimensions": dict(sorted(signals.authored_dimensions.items())),
        "observed_size": signals.observed_size,
        "observed_dimensions": dict(sorted(signals.observed_dimensions.items())),
        "observed_paths": sorted(set(signals.observed_paths or ())),
        "planned_surfaces": sorted(set(signals.planned_surfaces or ())),
        "verification_harnesses": sorted(set(signals.verification_harnesses or ())),
        "acceptance_checks": sorted(set(signals.acceptance_checks or ())),
        "harnessed_checks": sorted(set(signals.harnessed_checks or ())),
        "verified_checks": sorted(set(signals.verified_checks or ())),
        "integration_points": sorted(set(signals.integration_points or ())),
        "coordination_parties": sorted(set(signals.coordination_parties or ())),
        "write_surfaces": sorted(set(signals.write_surfaces or ())),
        "serial_surfaces": sorted(set(signals.serial_surfaces)),
        "parallel_evidence": sorted(set(signals.parallel_evidence)),
        "unresolved_gates": sorted(set(signals.unresolved_gates)),
        "unresolved_questions": sorted(set(signals.unresolved_questions)),
        "scope_tokens": sorted(set(signals.scope_tokens)),
        # These are not scope in the narrow product sense, but they do change
        # the assessment output.  Including them makes this an honest cache
        # identity rather than accepting stale confidence under a current scope.
        "evidence": sorted(set(signals.evidence)),
        "unknowns": sorted(set(signals.unknowns)),
    }


def scope_fingerprint(item: Item, signals: AssessmentSignals | Mapping | None = None) -> str:
    """Return a stable SHA-256 identity for the scope described by an estimate."""
    normalized = _coerce_signals(signals)
    payload = json.dumps(
        _canonical_scope(item, normalized), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def assessment_is_current(
    assessment: Mapping, item: Item, signals: AssessmentSignals | Mapping | None = None,
) -> bool:
    """Reject an assessment when its exact scope fingerprint is no longer current."""
    return assessment.get("scope_fingerprint") == scope_fingerprint(item, signals)


def _size_assessment(item: Item, signals: AssessmentSignals) -> dict:
    dimensions = {name: _dimension(name, signals) for name in DIMENSIONS}
    authored = normalize_appetite(item.appetite)
    observed = normalize_appetite(signals.observed_size)
    known = [value["band"] for value in dimensions.values() if value["band"]]

    assessed_candidates = [*known, *([authored] if authored else [])]
    if observed and signals.evidence:
        # A measured override may legitimately be lower than the authored
        # appetite or a dimension forecast, but it needs explicit evidence.
        band, provenance = observed, "observed"
    elif assessed_candidates:
        # Work is constrained by its largest independently assessed burden.
        # Authored appetite remains visible as intent, but cannot launder an L
        # integration burden into an S delivery estimate.
        band = max(assessed_candidates, key=_BAND_INDEX.__getitem__)
        provenance = "authored" if authored == band else "inferred"
    else:
        band, provenance = None, "unknown"

    unknowns = list(signals.unknowns)
    evidence = list(signals.evidence)
    for dimension in dimensions.values():
        evidence.extend(dimension["evidence"])
        unknowns.extend(dimension["unknowns"])
    if item.appetite and not authored:
        unknowns.append(f"unrecognized authored appetite retained verbatim: {item.appetite}")
    if signals.observed_size and not observed:
        unknowns.append(f"unrecognized observed size: {signals.observed_size}")
    elif observed and not signals.evidence:
        unknowns.append("observed size lacks explicit evidence and was not used as an override")

    unknown_count = sum(value["band"] is None for value in dimensions.values())
    gates = sorted(set(signals.unresolved_gates))
    questions = sorted(set(signals.unresolved_questions))
    missing_harness = any(
        "lack an observed harness" in unknown
        for unknown in dimensions["verification"]["unknowns"]
    )
    dimension_scores = [_BAND_INDEX[value] for value in known]
    disagreement = bool(authored and dimension_scores) and (
        max(abs(_BAND_INDEX[authored] - value) for value in dimension_scores) > 1
    )

    if band is None or (unknown_count >= 3 and not (authored or observed)):
        uncertainty = "U3"
    elif gates or questions or missing_harness or unknown_count >= 2 or disagreement:
        uncertainty = "U2"
    elif (provenance == "observed"
          and all(value["provenance"] == "observed" for value in dimensions.values())):
        uncertainty = "U0"
    else:
        uncertainty = "U1"

    if gates:
        unknowns.append("unresolved gate(s): " + ", ".join(gates))
    if questions:
        unknowns.append("unresolved owner question(s): " + ", ".join(questions))
    if disagreement:
        unknowns.append("authored/observed size differs materially from dimension evidence")

    if band is None:
        plausible = {"min": "XS", "max": "XL"}
    else:
        scores = [_BAND_INDEX[band], *dimension_scores]
        low, high = min(scores), max(scores)
        if uncertainty == "U2":
            low, high = max(0, low - 1), min(4, high + 1)
        elif uncertainty == "U3":
            low, high = 0, 4
        plausible = {"min": SIZE_BANDS[low], "max": SIZE_BANDS[high]}

    return {
        "raw_authored_appetite": item.appetite,
        "normalized_appetite": authored,
        "assessed_band": band,
        "plausible_range": plausible,
        "uncertainty": uncertainty,
        "provenance": provenance,
        "dimensions": dimensions,
        "evidence": sorted(set(evidence)),
        "unknowns": sorted(set(unknowns)),
    }


def _target_set(graph: Graph, supplied: Sequence[str] | None) -> tuple[set[str], str]:
    known = set(graph.item_map())
    if supplied is not None:
        resolved = set(supplied).intersection(known)
        return resolved, "authored" if resolved else "unknown"
    raw = graph.priority.get("effective_targets") or graph.priority.get("targets") or []
    if raw and all(isinstance(value, str) for value in raw):
        resolved = set(raw).intersection(known)
        return resolved, "authored" if resolved else "unknown"
    if raw and all(isinstance(value, Mapping) for value in raw):
        resolved = {
            value.get("item") for value in raw if value.get("item") in known
        }
        return resolved, "authored" if resolved else "unknown"
    return set(), "unknown"


def _impact_assessment(
    graph: Graph, item: Item, target_ids: Sequence[str] | None,
    done_statuses: set[str],
) -> dict:
    by_id = graph.item_map()
    reverse: dict[str, list[str]] = {item_id: [] for item_id in by_id}
    for candidate in graph.items:
        for dep in set(candidate.deps):
            if dep in reverse:
                reverse[dep].append(candidate.id)
    for values in reverse.values():
        values.sort()

    targets, provenance = _target_set(graph, target_ids)
    reached = set()
    stack = [item.id]
    visited = {item.id}
    while stack:
        current = stack.pop()
        if current in targets:
            reached.add(current)
        for dependent in reversed(reverse.get(current, ())):
            if dependent not in visited:
                visited.add(dependent)
                stack.append(dependent)

    completed_after = {candidate.id for candidate in graph.items
                       if candidate.status in done_statuses} | {item.id}
    immediate = []
    for dependent_id in reverse.get(item.id, ()):
        dependent = by_id[dependent_id]
        if dependent.status in done_statuses:
            continue
        if all(dep in completed_after for dep in dependent.deps):
            immediate.append(dependent_id)

    # The frontier is the nearest unfinished work on every downstream path,
    # traversing through already-done nodes.  It is structural reach, not value.
    frontier = set()
    pending = list(reverse.get(item.id, ()))
    seen = set()
    while pending:
        candidate_id = pending.pop()
        if candidate_id in seen:
            continue
        seen.add(candidate_id)
        candidate = by_id[candidate_id]
        if candidate.status not in done_statuses:
            frontier.add(candidate_id)
        else:
            pending.extend(reverse.get(candidate_id, ()))

    unknowns = []
    evidence = [
        f"{len(reached)} explicit target(s) in transitive dependency reach",
        f"{len(immediate)} direct item(s) become dependency-ready after completion",
        f"{len(frontier)} nearest unfinished downstream item(s)",
    ]
    if provenance == "unknown":
        unknowns.append("no explicit target set; structural target reach is unknown")
    return {
        "structural_target_reach": len(reached),
        "immediate_unlock": len(immediate),
        "frontier_reach": len(frontier),
        "target_items": sorted(reached),
        "immediate_items": sorted(immediate),
        "frontier_items": sorted(frontier),
        "provenance": provenance,
        "evidence": evidence,
        "unknowns": unknowns,
    }


def _parallel_assessment(
    item: Item, signals: AssessmentSignals, conflicts: Mapping[str, set[str]],
    done_statuses: set[str], graph: Graph,
) -> dict:
    by_id = graph.item_map()
    unresolved_deps = sorted(
        dep for dep in item.deps
        if dep in by_id and by_id[dep].status not in done_statuses
    )
    surface_conflicts = sorted(conflicts.get(item.id, set()))
    evidence = list(signals.parallel_evidence)
    conflict_evidence = []
    if unresolved_deps:
        conflict_evidence.append("unfinished hard dependencies: " + ", ".join(unresolved_deps))
    if signals.serial_surfaces:
        conflict_evidence.append(
            "serial shared surfaces: " + ", ".join(sorted(set(signals.serial_surfaces)))
        )
    if surface_conflicts:
        conflict_evidence.append("write-surface overlap with: " + ", ".join(surface_conflicts))

    if conflict_evidence:
        classification = "serial"
    elif signals.parallel_evidence and signals.write_surfaces is not None:
        classification = "candidate"
    else:
        classification = "unknown"

    unknowns = []
    if signals.write_surfaces is None:
        unknowns.append("write surfaces are not established")
    if classification == "unknown":
        unknowns.append(
            "lack of hard dependencies does not establish file, build, review, or ownership isolation"
        )
    return {
        "classification": classification,
        "write_surfaces": sorted(set(signals.write_surfaces or ())),
        "evidence": sorted(set(evidence)),
        "conflicts": conflict_evidence,
        "unknowns": sorted(set(unknowns)),
    }


def assess_story(
    graph: Graph,
    item_id: str,
    *,
    target_ids: Sequence[str] | None = None,
    signals: AssessmentSignals | Mapping | None = None,
    done_statuses: Sequence[str] = ("shipped", "verified"),
) -> dict:
    """Assess one story without mutating the graph or inventing an AI multiplier."""
    item = graph.item_map().get(item_id)
    if item is None:
        raise KeyError(f"unknown assessment item: {item_id}")
    normalized = _coerce_signals(signals)
    done = set(done_statuses)
    return {
        "schema": 1,
        "item": item.id,
        "scope_fingerprint": scope_fingerprint(item, normalized),
        "size": _size_assessment(item, normalized),
        "impact": _impact_assessment(graph, item, target_ids, done),
        "parallelism": _parallel_assessment(item, normalized, {}, done, graph),
    }


def assess_graph(
    graph: Graph,
    *,
    target_ids: Sequence[str] | None = None,
    signals_by_item: Mapping[str, AssessmentSignals | Mapping] | None = None,
    done_statuses: Sequence[str] = ("shipped", "verified"),
) -> dict[str, dict]:
    """Assess all items and detect overlapping write surfaces across stories."""
    raw_signals = signals_by_item or {}
    unknown_ids = set(raw_signals) - set(graph.item_map())
    if unknown_ids:
        raise KeyError("assessment signals name unknown items: " + ", ".join(sorted(unknown_ids)))
    signals = {
        item.id: _coerce_signals(raw_signals.get(item.id)) for item in graph.items
    }
    owners: dict[str, set[str]] = {}
    for item_id, item_signals in signals.items():
        for surface in set(item_signals.write_surfaces or ()):
            owners.setdefault(surface, set()).add(item_id)
    conflicts: dict[str, set[str]] = {item.id: set() for item in graph.items}
    for item_ids in owners.values():
        if len(item_ids) > 1:
            for item_id in item_ids:
                conflicts[item_id].update(item_ids - {item_id})

    done = set(done_statuses)
    result = {}
    for item in sorted(graph.items, key=lambda value: value.id):
        item_signals = signals[item.id]
        result[item.id] = {
            "schema": 1,
            "item": item.id,
            "scope_fingerprint": scope_fingerprint(item, item_signals),
            "size": _size_assessment(item, item_signals),
            "impact": _impact_assessment(graph, item, target_ids, done),
            "parallelism": _parallel_assessment(
                item, item_signals, conflicts, done, graph,
            ),
        }
    return result


_TEST_SELECTOR_RE = re.compile(r"\btest[A-Za-z0-9_]{2,}\b")
_MAX_SELECTOR_SOURCE_BYTES = 8 * 1024 * 1024
_MAX_TEST_INDEX_BYTES = 64 * 1024 * 1024
_MAX_SIGNALS_FILE_BYTES = 2 * 1024 * 1024


def _source_acceptance_signals(
    graph: Graph, root: Path | None, verification_globs: Sequence[str],
) -> dict[str, AssessmentSignals]:
    """Extract conservative, repository-observed signals for the application seam.

    A selector mentioned by a story is an acceptance contract.  It counts as a
    harness only when the same exact selector is found under a configured test
    glob.  Presence is still not execution evidence, so ``verified_checks`` is
    intentionally left unset.
    """
    if root is None:
        return {}
    project_root = Path(root).resolve()
    # Text presence is only a candidate source. A comment, disabled file, or
    # uncompiled target is not a harness, much less an executed receipt.
    selector_candidates: dict[str, set[str]] = {}
    indexed_bytes = 0
    for pattern in verification_globs:
        try:
            candidates = project_root.glob(pattern)
        except (OSError, ValueError):
            continue
        for path in candidates:
            try:
                if not path.is_file() or path.is_symlink():
                    continue
                size = path.stat().st_size
                if size > _MAX_SELECTOR_SOURCE_BYTES \
                        or indexed_bytes + size > _MAX_TEST_INDEX_BYTES:
                    continue
                relative = path.resolve().relative_to(project_root).as_posix()
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError, ValueError):
                continue
            indexed_bytes += size
            for selector in set(_TEST_SELECTOR_RE.findall(text)):
                selector_candidates.setdefault(selector, set()).add(relative)

    questions_by_story: dict[str, list[str]] = {}
    for question in graph.owner_questions:
        questions_by_story.setdefault(question.story_id, []).append(question.id)

    # A DAG adapter may point thousands of items at the same large source.
    # Cache by resolved path so refresh cost is O(unique sources), not O(items).
    source_cache: dict[Path, tuple[tuple[str, ...] | None, str, str | None]] = {}
    result = {}
    for item in graph.items:
        path_value = item.source.get("path")
        checks: tuple[str, ...] | None = None
        scope_tokens = []
        evidence = []
        unknowns = []
        if isinstance(path_value, str) and path_value:
            try:
                source_path = (project_root / path_value).resolve()
                source_path.relative_to(project_root)
                if source_path.is_file() and not source_path.is_symlink():
                    cached = source_cache.get(source_path)
                    if cached is None:
                        size = source_path.stat().st_size
                        digest = hashlib.sha256()
                        if size <= _MAX_SELECTOR_SOURCE_BYTES:
                            raw = source_path.read_bytes()
                            digest.update(raw)
                            content = raw.decode("utf-8")
                            found = tuple(sorted(set(_TEST_SELECTOR_RE.findall(content))))
                            cached = (found or None, digest.hexdigest(), None)
                        else:
                            with source_path.open("rb") as handle:
                                for block in iter(lambda: handle.read(1024 * 1024), b""):
                                    digest.update(block)
                            cached = (
                                None, digest.hexdigest(),
                                f"source exceeds selector scan cap ({size} bytes)",
                            )
                        source_cache[source_path] = cached
                    checks, digest_value, scan_unknown = cached
                    scope_tokens.append("source-sha256:" + digest_value)
                    evidence.append(f"source scope observed at {path_value}")
                    if scan_unknown:
                        unknowns.append(scan_unknown)
            except (OSError, UnicodeError, ValueError):
                pass

        candidate_sources = tuple(sorted({
            candidate
            for selector in checks or ()
            for candidate in selector_candidates.get(selector, ())
        }))
        if candidate_sources:
            evidence.append(
                "candidate test source(s), execution unobserved: "
                + ", ".join(candidate_sources)
            )
            unknowns.append(
                "test-source text does not establish compilation, discovery, or execution"
            )
        result[item.id] = AssessmentSignals(
            acceptance_checks=checks,
            verification_harnesses=None,
            # Hard prerequisites are not integration boundaries. ``Deps: []``
            # especially proves no such thing; using it as zero integration
            # work would reward empty metadata with fake confidence.
            integration_points=None,
            unresolved_questions=tuple(sorted(questions_by_story.get(item.id, ()))),
            scope_tokens=tuple(scope_tokens),
            evidence=tuple(evidence),
            unknowns=tuple(unknowns),
        )
    return result


def _signals_manifest(
    graph: Graph, cfg, root: Path | None,
    base_signals: Mapping[str, AssessmentSignals],
) -> tuple[dict[str, Mapping], list[str]]:
    """Load bounded schema-1 evidence without making refresh brittle."""
    configured = cfg.get("assessment.signals_path", "")
    if not isinstance(configured, str) or not configured:
        return {}, []
    label = f"assessment signals {configured}"
    if root is None:
        return {}, [f"{label} cannot be read without a project root (ignored)"]
    relative = Path(configured)
    if relative.is_absolute():
        return {}, [f"{label} must be a relative in-project path (ignored)"]
    project_root = Path(root).resolve()
    unresolved = project_root / relative
    try:
        current = project_root
        for part in relative.parts:
            if part in ("", "."):
                continue
            current = current / part
            if current.is_symlink():
                return {}, [f"{label} must not traverse a symlink (ignored)"]
        path = unresolved.resolve()
        path.relative_to(project_root)
    except (OSError, ValueError):
        return {}, [f"{label} escapes the project root (ignored)"]
    try:
        if not path.exists():
            # The configured evidence overlay is optional by contract.
            return {}, []
        if not path.is_file():
            return {}, [f"{label} is not a regular file (ignored)"]
        size = path.stat().st_size
        if size > _MAX_SIGNALS_FILE_BYTES:
            return {}, [f"{label} exceeds {_MAX_SIGNALS_FILE_BYTES} bytes (ignored)"]
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, RecursionError):
        return {}, [f"{label} is unreadable or malformed (ignored)"]
    if not isinstance(data, dict) or set(data) != {"schema", "items"} \
            or data.get("schema") != 1 or not isinstance(data.get("items"), dict):
        return {}, [f"{label} must be a schema-1 object with an items object (ignored)"]

    known = set(graph.item_map())
    warnings = []
    accepted: dict[str, Mapping] = {}
    for item_id, raw in sorted(data["items"].items(), key=lambda value: str(value[0])):
        if not isinstance(item_id, str) or item_id not in known:
            warnings.append(f"{label} names unknown item {item_id!r} (entry ignored)")
            continue
        if not isinstance(raw, Mapping):
            return {}, [f"{label} item {item_id} is not an object (manifest ignored)"]
        if set(raw) != {"scopeFingerprint", "signals"}:
            return {}, [
                f"{label} item {item_id} must contain scopeFingerprint and signals "
                "only (manifest ignored)"
            ]
        expected = raw.get("scopeFingerprint")
        explicit = raw.get("signals")
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            return {}, [
                f"{label} item {item_id} scopeFingerprint must be lowercase SHA-256 "
                "(manifest ignored)"
            ]
        current = scope_fingerprint(graph.item_map()[item_id], base_signals[item_id])
        if expected != current:
            warnings.append(
                f"{label} item {item_id} scope changed (entry ignored; reassess it)"
            )
            continue
        if not isinstance(explicit, Mapping):
            return {}, [f"{label} item {item_id} signals is not an object (manifest ignored)"]
        forbidden = {
            "observed_size", "observed_dimensions", "observed_paths",
            "verification_harnesses", "harnessed_checks", "verified_checks",
        }.intersection(explicit)
        if forbidden:
            return {}, [
                f"{label} item {item_id} cannot self-certify observed fields: "
                + ", ".join(sorted(forbidden)) + " (manifest ignored)"
            ]
        try:
            _coerce_signals(explicit)
        except (TypeError, ValueError) as error:
            return {}, [f"{label} item {item_id} is invalid: {error} (manifest ignored)"]
        accepted[item_id] = dict(explicit)
    return accepted, warnings


def _merge_signals(auto: AssessmentSignals, explicit: Mapping) -> AssessmentSignals:
    """Merge explicit evidence without letting it erase live gates/questions."""
    merged = asdict(auto)
    dimensions = ("observed_dimensions", "authored_dimensions")
    concatenated = (
        "acceptance_checks", "verification_harnesses",
        "scope_tokens", "evidence", "unknowns",
        "unresolved_questions", "unresolved_gates",
    )
    for field_name in dimensions:
        if field_name in explicit:
            combined = dict(merged[field_name])
            combined.update(explicit[field_name])
            merged[field_name] = combined
    for field_name in concatenated:
        if field_name in explicit:
            merged[field_name] = tuple(sorted(set(
                tuple(merged[field_name]) + tuple(explicit[field_name])
            )))
    for field_name, value in explicit.items():
        if field_name not in dimensions and field_name not in concatenated:
            merged[field_name] = value
    return _coerce_signals(merged)


def _portfolio(
    graph: Graph, assessments: Mapping[str, dict], *, small_limit: int,
    anchor_limit: int, question_limit: int, done_statuses: set[str],
    hold_statuses: set[str],
) -> dict:
    """Choose mixed-size lanes without combining size and impact into a score."""
    by_id = graph.item_map()
    question_stories = {question.story_id for question in graph.owner_questions}
    activity_as_of = graph.activity.get("as_of")
    activity_as_of = activity_as_of if isinstance(activity_as_of, str) else None
    latest_work = {}
    for work in graph.active_work:
        previous = latest_work.get(work.story_id)
        if previous is None or work.updated_at > previous.updated_at:
            latest_work[work.story_id] = work
    occupied_stories = {
        work.story_id for work in latest_work.values()
        if work.state in {"active", "blocked", "paused"}
        and activity_as_of is not None
        and work.stale_at >= activity_as_of
    }
    blocked_stories = {
        work.story_id for work in latest_work.values()
        if work.state == "blocked"
        and work.story_id not in occupied_stories
    }
    stale_work_stories = {
        work.story_id for work in latest_work.values()
        if work.state in {"active", "blocked", "paused"}
        and work.story_id not in occupied_stories
    }

    def eligible(item_id: str) -> bool:
        item = by_id[item_id]
        if item.status in done_statuses | hold_statuses:
            return False
        # When priority is enabled its readiness/gate ruling is authoritative.
        return not item.priority or item.priority.get("eligible") is True

    def order(item_id: str):
        result = assessments[item_id]
        impact = result["impact"]
        rank = by_id[item_id].priority.get("rank")
        course_order = by_id[item_id].priority.get("components", {}).get("course_order")
        return (
            course_order is None,
            course_order if course_order is not None else 10 ** 9,
            -impact["structural_target_reach"],
            -impact["immediate_unlock"],
            -impact["frontier_reach"],
            rank is None, rank if rank is not None else 10 ** 9,
            item_id,
        )

    has_target_scope = any(
        result["impact"]["provenance"] != "unknown"
        for result in assessments.values()
    )
    candidates = [
        item_id for item_id in assessments
        if eligible(item_id)
        and by_id[item_id].status != "bug-gap"
        and item_id not in occupied_stories
        and item_id not in blocked_stories
    ]
    question_candidates = [
        item_id for item_id in assessments
        if item_id in question_stories and by_id[item_id].status not in done_statuses
    ]
    questions = sorted(
        question_candidates, key=order,
    )[:question_limit]
    normal = [item_id for item_id in candidates if item_id not in question_stories]
    warnings = []
    anchors = []
    if not has_target_scope:
        small = []
        warnings.append(
            "delivery portfolio withheld: missing explicit target scope"
        )
    else:
        small = sorted((
            item_id for item_id in normal
            if assessments[item_id]["size"]["assessed_band"] in {"XS", "S"}
        ), key=order)[:small_limit]
    anchor_candidates = sorted((
        item_id for item_id in normal
        if assessments[item_id]["size"]["assessed_band"] in {"M", "L"}
        and assessments[item_id]["size"]["uncertainty"] != "U3"
    ), key=order)
    if has_target_scope and anchor_limit and anchor_candidates:
        anchors = anchor_candidates[:1]
        if anchor_limit > 1:
            first = assessments[anchors[0]]
            for candidate_id in anchor_candidates[1:]:
                candidate = assessments[candidate_id]
                dimensions = candidate["size"]["dimensions"]
                first_dimensions = first["size"]["dimensions"]
                independent = (
                    first["parallelism"]["classification"] == "candidate"
                    and candidate["parallelism"]["classification"] == "candidate"
                    and not first["parallelism"]["conflicts"]
                    and not candidate["parallelism"]["conflicts"]
                    and all(dimensions[name]["band"] is not None
                            for name in ("verification", "integration"))
                    and all(first_dimensions[name]["band"] is not None
                            for name in ("verification", "integration"))
                )
                if independent:
                    anchors.append(candidate_id)
                    break
            if len(anchors) == 1 and len(anchor_candidates) > 1:
                warnings.append(
                    "second anchor withheld: independent parallel execution is not established"
                )
    unknown = sorted((
        item_id for item_id in normal
        if assessments[item_id]["size"]["assessed_band"] is None
    ), key=order)
    defect_candidates = [
        item.id for item in graph.items
        if item.status == "bug-gap"
        and item.status not in done_statuses | hold_statuses
        and item.id not in question_stories
        and item.id not in occupied_stories
        and item.id not in blocked_stories
    ]
    ranked_defects = [
        item_id for item_id in defect_candidates
        if by_id[item_id].priority.get("defect", {}).get("rank") is not None
    ]
    defects = sorted(ranked_defects, key=lambda item_id: (
        by_id[item_id].priority["defect"]["rank"],
        item_id,
    ))[:small_limit]
    unranked_defects = len(defect_candidates) - len(ranked_defects)
    if unranked_defects:
        warnings.append(
            f"{unranked_defects} defect(s) withheld: blast-radius rank is not established"
        )
    return {
        "small": small,
        "anchors": anchors,
        "defects": defects,
        "questions": questions,
        "occupied": sorted(
            (item_id for item_id in occupied_stories if item_id in assessments),
            key=order,
        ),
        "blocked": sorted(
            (item_id for item_id in blocked_stories if item_id in assessments),
            key=order,
        ),
        "stale_work": sorted(
            (item_id for item_id in stale_work_stories if item_id in assessments),
            key=order,
        ),
        "unknown_size": unknown,
        "warnings": warnings,
        "policy": {
            "small_limit": small_limit,
            "anchor_limit": anchor_limit,
            "question_limit": question_limit,
            "ordering": [
                "owner_course_order", "structural_target_reach", "immediate_unlock",
                "frontier_reach", "existing_priority_rank", "item_id",
            ],
        },
    }


def apply_assessments(graph: Graph, cfg, root: Path | None = None) -> None:
    """Populate the opt-in top-level assessment contract in-place.

    Disabled means no-op, including preserving an already-loaded assessment.
    This supports old installations and avoids a refresh silently erasing data
    produced by a newer explicitly enabled engine.
    """
    if not bool(cfg.get("assessment.enabled", False)):
        return
    globs = cfg.get("assessment.verification_globs", [
        "tests/**/*", "test/**/*", "tests-ui/**/*",
    ])
    if not isinstance(globs, list) or not all(isinstance(value, str) for value in globs):
        globs = ["tests/**/*", "test/**/*", "tests-ui/**/*"]
    signals = _source_acceptance_signals(graph, root, globs)
    questions_by_story: dict[str, list[str]] = {}
    for question in graph.owner_questions:
        questions_by_story.setdefault(question.story_id, []).append(question.id)
    for item in graph.items:
        signals.setdefault(item.id, AssessmentSignals(
            unresolved_questions=tuple(sorted(questions_by_story.get(item.id, ()))),
        ))

    gates_by_story: dict[str, list[str]] = {}
    for gate in cfg.get("gates", []):
        if not isinstance(gate, Mapping):
            continue
        item_id = gate.get("item")
        if not isinstance(item_id, str):
            continue
        reason = gate.get("reason")
        gates_by_story.setdefault(item_id, []).append(
            reason if isinstance(reason, str) and reason else "configured gate"
        )
    for item_id, gates in gates_by_story.items():
        if item_id in signals:
            data = asdict(signals[item_id])
            data["unresolved_gates"] = tuple(sorted(set(gates)))
            signals[item_id] = AssessmentSignals(**data)

    explicit_signals, signal_warnings = _signals_manifest(graph, cfg, root, signals)
    graph.warnings = sorted(set(graph.warnings).union(signal_warnings))
    for item_id, explicit in explicit_signals.items():
        signals[item_id] = _merge_signals(signals[item_id], explicit)

    statuses = cfg.vocab.get("statuses", [])
    done_statuses = {
        status.get("name") for status in statuses
        if status.get("done") is True or status.get("role") == "done"
    }
    hold_statuses = {
        status.get("name") for status in statuses if status.get("role") == "hold"
    }
    assessments = assess_graph(
        graph, signals_by_item=signals, done_statuses=sorted(done_statuses),
    )
    graph.assessment = {
        "schema": 1,
        "method": "deterministic-delivery-assessment-v1",
        "items": assessments,
        "portfolio": _portfolio(
            graph, assessments,
            small_limit=max(0, cfg.get("assessment.small_limit", 4)),
            anchor_limit=max(0, cfg.get("assessment.anchor_limit", 2)),
            question_limit=max(0, cfg.get("assessment.question_limit", 1)),
            done_statuses=done_statuses,
            hold_statuses=hold_statuses,
        ),
    }
