"""Adapter for hierarchical spec trees and optional legacy DAG imports."""
from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath

from ..model import Group, Item, Milestone, MilestonePhase, Relation
from . import ScanResult


_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_LABEL_RE = re.compile(r"^\w+:\s*")
# codex-sequence-2026-08-08: strict story-header dependency grammar.
_MARKDOWN_LINK_RE = re.compile(r"^\[([^\]\r\n]+)\]\(([^\r\n)]+)\)$")
_CODE_SPAN_RE = re.compile(r"^(`+)(.*?)\1$", re.DOTALL)
_KIND_PREFIX_RE = re.compile(r"^[A-Za-z0-9_-]+:")
_DEP_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_DEP_ATOM_RE = re.compile(
    r"^(?:`(?:(?:story|STR):)?[a-z0-9]+(?:-[a-z0-9]+)*`|"
    r"(?:(?:story|STR):)?[a-z0-9]+(?:-[a-z0-9]+)*)$"
)
_EMPTY_DEPS_RE = re.compile(r"^\[\](?:\s+\([^()\r\n]+\))?$")
_LINEAGE_HEADERS = {"revises": "revises", "bug against": "bug_against"}
_RELATIVE_STORY_PATH_RE = re.compile(
    r"^(?!/)(?![A-Za-z][A-Za-z0-9+.-]*:)(?:\.\./)*"
    r"(?:[a-z0-9._-]+/)*[a-z0-9]+(?:-[a-z0-9]+)*\.md$"
)
_MAX_DAG_JSON_DEPTH = 8
_MAX_DAG_JSON_NODES = 20_000
_WORK_ITEM_KEYS = {"deps", "status", "release", "wave"}
_FOUNDATION_ROW_RE = re.compile(
    r"^\|\s*\[([^\]\r\n]+)\]\(([^)\r\n]+\.md)\)\s*\|\s*(.*?)\s*\|\s*$",
    re.MULTILINE,
)


def _front_matter(text: str) -> tuple[dict, str]:
    """Parse the deliberately small front-matter subset used by adapters."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    try:
        end = next(i for i, line in enumerate(lines[1:], 1)
                   if line.strip() == "---")
    except StopIteration:
        return {}, text

    data: dict = {}
    list_key: str | None = None
    for line in lines[1:end]:
        if not line.strip():
            continue
        if re.match(r"^\s*-\s+", line):
            if list_key is None:
                return {}, text
            data[list_key].append(re.sub(r"^\s*-\s+", "", line).strip())
            continue
        match = re.match(r"^([A-Za-z0-9_-]+):(?:\s*(.*))?$", line)
        if not match:
            return {}, text
        key, raw = match.group(1), (match.group(2) or "").strip()
        if not raw:
            data[key] = []
            list_key = key
        else:
            data[key] = _front_value(raw)
            list_key = None

    return data, "\n".join(lines[end + 1:])


def _front_value(raw: str):
    if raw == "[]":
        return []
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        if not inner:
            return []
        return [_unquote(part.strip()) for part in inner.split(",")]
    return _unquote(raw)


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _first_h1(text: str) -> str | None:
    match = _H1_RE.search(text)
    return match.group(1).strip() if match else None


def _display_title(text: str) -> str | None:
    title = _first_h1(text)
    return _LABEL_RE.sub("", title).strip() if title else None


def _one_liner(body: str, front: dict) -> str | None:
    intent = re.search(r"^##\s+Intent\s*$", body, re.IGNORECASE | re.MULTILINE)
    if intent:
        for line in body[intent.end():].splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                break
            if stripped:
                return _collapse(stripped)[:140]
    summary = front.get("summary")
    if isinstance(summary, str) and summary.strip():
        return _collapse(summary)[:140]
    return None


def _collapse(value: str) -> str:
    return " ".join(value.split())


def _string_list(value) -> list[str]:
    if isinstance(value, list):
        raw = value
    elif isinstance(value, str):
        raw = value.split(",")
    else:
        return []
    return list(dict.fromkeys(
        entry.strip() for entry in map(str, raw) if entry.strip()
    ))


def _authored_list(front: dict, body: str, front_key: str, label: str) -> list[str]:
    value = front.get(front_key)
    if value is not None:
        return _string_list(value)
    match = re.search(
        rf"^>\s*{re.escape(label)}:\s*(.+?)\s*$", body,
        re.IGNORECASE | re.MULTILINE,
    )
    return _string_list(match.group(1)) if match else []


def _match_value(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text, re.MULTILINE)
    return match.group(1) if match else None


def _appetite_value(text: str) -> str | None:
    """Preserve the authored appetite label without swallowing its rationale.

    Appetite is deliberately free-form project metadata.  The old ``[a-z-]+``
    matcher silently turned ``not yet assessable`` into ``not`` and
    ``small/medium`` into ``small``.  That is worse than missing data: it hands
    the assessor a confident lie.  Keep the complete label, stripping only the
    well-established prose separators and Markdown emphasis around it.
    """
    match = re.search(r"\bAppetite:\s*(.+?)\s*$", text, re.IGNORECASE | re.MULTILINE)
    if not match:
        return None
    value = match.group(1).strip()
    # Header fields and rationale use visibly separated delimiters.  An en dash
    # inside ``small–medium`` has no surrounding spaces and remains data.
    value = re.split(r"\s+·\s+|\s+[—–]\s+|\s+\(", value, maxsplit=1)[0].strip()
    if len(value) >= 4 and value.startswith("**") and value.endswith("**"):
        value = value[2:-2].strip()
    if len(value) >= 2 and value[0] == value[-1] == "`":
        value = value[1:-1].strip()
    return value or None


def _dep_ids(value, item_kind: str) -> list[str]:
    if isinstance(value, list):
        slugs = value
    elif isinstance(value, str):
        if value.strip() in {"", "-", "—"} or value.strip().startswith("[]"):
            return []
        slugs = value.split(",")
    else:
        return []

    deps = []
    for raw in slugs:
        entry = str(raw).strip()
        if not entry or entry in {"-", "—"}:
            continue

        link = _MARKDOWN_LINK_RE.fullmatch(entry)
        if link:
            entry = link.group(1)

        entry = entry.strip()
        code_span = _CODE_SPAN_RE.fullmatch(entry)
        if code_span:
            entry = code_span.group(2).strip()
        entry = _KIND_PREFIX_RE.sub("", entry, count=1)

        if _DEP_SLUG_RE.fullmatch(entry):
            deps.append(f"{item_kind}:{entry}")
    return deps


# codex-sequence-2026-08-08: authoritative body dependencies use a strict,
# whole-value grammar. Harvesting valid-looking links from malformed text made
# a damaged header indistinguishable from a deliberate dependency set.
def _strict_body_dep_ids(value: str, item_kind: str) -> tuple[list[str] | None, str | None]:
    raw = value.strip()
    if _EMPTY_DEPS_RE.fullmatch(raw):
        return [], None
    if raw.startswith("[]"):
        return None, "invalid text after []; use [] (note) for an empty-set annotation"

    if " · " in raw:
        core, note = raw.split(" · ", 1)
        if not core.strip() or not note.strip() or " · " in note:
            return None, "invalid dependency annotation; use one non-empty ` · note` suffix"
    else:
        core = raw

    entries = [entry.strip() for entry in core.split(",")]
    if not entries or any(not entry for entry in entries):
        return None, "empty dependency entry"

    link_matches = [_MARKDOWN_LINK_RE.fullmatch(entry) for entry in entries]
    atom_matches = [_DEP_ATOM_RE.fullmatch(entry) for entry in entries]
    if all(link_matches):
        slugs = []
        for match in link_matches:
            label, target = match.groups()
            clean_target = target.split("#", 1)[0].split("?", 1)[0]
            if not clean_target.endswith(".md"):
                return None, f"dependency target is not a Markdown document: {target}"
            ids = _dep_ids([label], item_kind)
            if len(ids) != 1:
                return None, f"invalid dependency label: {label}"
            slugs.extend(ids)
    elif all(atom_matches):
        slugs = _dep_ids(entries, item_kind)
    elif any(link_matches) and any(atom_matches):
        return None, "mixed linked and raw dependencies; use one representation consistently"
    else:
        return None, "malformed dependency entry or unseparated residual text"

    if len(slugs) != len(set(slugs)):
        return None, "duplicate dependency"
    return slugs, None


def _body_deps(body: str, item_kind: str):
    matches = re.findall(r"^>\s*Deps:\s*(.*?)\s*$", body,
                         re.IGNORECASE | re.MULTILINE)
    if not matches:
        return None, None
    if len(matches) != 1:
        return None, f"expected exactly one > Deps: header, found {len(matches)}"
    return _strict_body_dep_ids(matches[0], item_kind)


def _strict_story_relation(value: str, item_kind: str) -> tuple[str | None, str | None]:
    """Parse exactly one relative story document reference.

    Accept the corpus' authored ``story-slug.md`` form and an equivalent
    Markdown link.  We intentionally do not harvest a plausible filename from
    surrounding prose: damaged lineage is worse than a loud dropped edge.
    """
    raw = value.strip()
    link = _MARKDOWN_LINK_RE.fullmatch(raw)
    label = None
    if link:
        label, raw = link.groups()
    if "\\" in raw or not _RELATIVE_STORY_PATH_RE.fullmatch(raw):
        return None, "expected one relative story-slug.md link"
    slug = PurePosixPath(raw).stem
    target = f"{item_kind}:{slug}"
    if label is not None and _dep_ids([label], item_kind) != [target]:
        return None, "Markdown label must name the linked story slug"
    return target, None


def _body_relations(body: str, item_kind: str) -> tuple[list[Relation], list[str]]:
    matches: dict[str, list[str]] = {kind: [] for kind in _LINEAGE_HEADERS.values()}
    for match in re.finditer(
        r"^>\s*(Revises|Bug against):\s*(.*?)\s*$",
        body,
        re.IGNORECASE | re.MULTILINE,
    ):
        kind = _LINEAGE_HEADERS[match.group(1).lower()]
        matches[kind].append(match.group(2))

    relations = []
    errors = []
    for kind in sorted(matches):
        values = matches[kind]
        if not values:
            continue
        if len(values) != 1:
            errors.append(f"expected exactly one > {kind.replace('_', ' ')}: header")
            continue
        target, error = _strict_story_relation(values[0], item_kind)
        if error:
            errors.append(f"invalid > {kind.replace('_', ' ')}: header: {error}")
        else:
            relations.append(Relation(kind=kind, target=target))
    return relations, errors


def _group_chain(root: Path, rel: Path, pattern: str, levels: list[str],
                 groups: dict[str, Group], warnings: list[str]) -> str | None:
    pattern_parts = Path(pattern).as_posix().split("/")
    rel_parts = rel.as_posix().split("/")
    captures = [(index, rel_parts[index])
                for index, part in enumerate(pattern_parts[:-1])
                if part == "*" and index < len(rel_parts) - 1]

    parent = None
    cumulative = []
    for level, (index, slug) in zip(levels, captures):
        cumulative.append(slug)
        group_id = f"{level}:{'/'.join(cumulative)}"
        if group_id not in groups:
            title = slug.replace("-", " ").title()
            meta = {}
            directory = root.joinpath(*rel_parts[:index + 1])
            overview = directory / f"{slug}.md"
            if overview.is_file():
                try:
                    title = _display_title(overview.read_text(encoding="utf-8")) or title
                    meta = {"source": {
                        "adapter": "spec_tree",
                        "path": overview.relative_to(root).as_posix(),
                    }}
                except (OSError, UnicodeError):
                    warnings.append(f"{overview.relative_to(root).as_posix()}: unreadable")
            groups[group_id] = Group(id=group_id, kind=level, title=title,
                                     parent=parent, meta=meta)
        parent = group_id
    return parent


def _foundation_index_groups(root: Path, relpath: str,
                             warnings: list[str]) -> list[Group]:
    """Read an explicit Markdown index of required foundation contracts.

    Foundation membership comes only from the configured index table. A broad
    folder glob would promote migration notes and generated indexes into
    architectural contracts merely because they share a directory.
    """
    path = root / relpath
    normalized = Path(relpath).as_posix()
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        warnings.append(f"{normalized}: unreadable foundation index")
        return []

    marker = "## Required foundation specs"
    if marker not in text:
        warnings.append(f"{normalized}: missing required foundation specs section")
        return []
    section = text.split(marker, 1)[1]
    section = re.split(r"^##\s+", section, maxsplit=1, flags=re.MULTILINE)[0]
    groups = [Group(
        id="subject:foundations",
        kind="subject",
        title="Product Foundations",
        meta={"source": {"adapter": "spec_tree", "path": normalized}},
    )]
    seen = set()
    project_root = root.resolve()
    for match in _FOUNDATION_ROW_RE.finditer(section):
        label, raw_target, purpose = match.groups()
        raw_target = raw_target.split("#", 1)[0]
        try:
            source = (path.parent / raw_target).resolve()
            source.relative_to(project_root)
        except (OSError, ValueError):
            warnings.append(f"{normalized}: foundation link escapes project: {raw_target}")
            continue
        slug = source.stem
        if not _DEP_SLUG_RE.fullmatch(slug):
            warnings.append(f"{normalized}: malformed foundation slug ignored: {slug}")
            continue
        group_id = f"foundation:{slug}"
        if group_id in seen:
            warnings.append(f"{normalized}: duplicate foundation ignored: {slug}")
            continue
        if not source.is_file():
            warnings.append(f"{normalized}: foundation source unavailable: {raw_target}")
            continue
        seen.add(group_id)
        source_relpath = source.relative_to(project_root).as_posix()
        groups.append(Group(
            id=group_id,
            kind="foundation",
            title=label.strip(),
            parent="subject:foundations",
            meta={
                "source": {"adapter": "spec_tree", "path": source_relpath},
                "summary": purpose.strip(),
            },
        ))
    if len(groups) == 1:
        warnings.append(f"{normalized}: no required foundation rows found")
    return groups


def _scan_file(path: Path, root: Path, pattern: str, levels: list[str],
               item_kind: str, groups: dict[str, Group],
               warnings: list[str], product_tags: set[str]) -> Item | None:
    rel = path.relative_to(root)
    relpath = rel.as_posix()
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        warnings.append(f"{relpath}: unreadable")
        return None

    front, body = _front_matter(text)
    stem = path.stem
    title = _display_title(body) or stem
    group = _group_chain(root, rel, pattern, levels, groups, warnings)

    status = front.get("status")
    if not isinstance(status, str) or not status:
        status = _match_value(r"^>\s*Status:\s*([a-zA-Z-]+)", body)
    if not status:
        status = "unknown"
        warnings.append(f"{relpath}: no status")

    release = front.get("release")
    if not isinstance(release, str) or not release:
        release = _match_value(r"Release:\s*([A-Za-z0-9.?]+)", body)
    wave = front.get("wave")
    if not isinstance(wave, str) or not wave:
        wave = _match_value(r"Wave:\s*([A-Za-z0-9]+)", body)
    appetite = _appetite_value(body)
    if "deps" in front:
        deps = _dep_ids(front["deps"], item_kind)
        deps_declared = True
        deps_error = None
    else:
        deps, deps_error = _body_deps(body, item_kind)
        deps_declared = deps is not None or deps_error is not None
        deps = deps or []
    if deps_error:
        warnings.append(f"{relpath}: invalid > Deps: header: {deps_error}")
    relations, relation_errors = _body_relations(body, item_kind)
    warnings.extend(f"{relpath}: {error}" for error in relation_errors)
    tags = _authored_list(front, body, "tags", "Tags")
    product_capabilities = _authored_list(
        front, body, "product_capabilities", "Product capabilities"
    )
    products = list(dict.fromkeys(
        capability.split("/", 1)[0]
        for capability in product_capabilities if "/" in capability
    ))
    products = list(dict.fromkeys(
        products + [tag for tag in tags if tag in product_tags]
    ))
    flags = ["debt"] if re.search(r"^>\s*Debt:", body, re.MULTILINE) else []

    source = {"adapter": "spec_tree", "path": relpath}
    if deps_declared:
        source["deps_declared"] = True

    return Item(
        id=f"{item_kind}:{stem}",
        title=title,
        one_liner=_one_liner(body, front),
        status=status,
        release=release,
        wave=wave,
        group=group,
        deps=deps,
        relations=relations,
        appetite=appetite,
        role="delivery",
        tags=tags,
        facets={
            key: values for key, values in (
                ("product", products),
                ("capability", product_capabilities),
            ) if values
        },
        flags=flags,
        source=source,
    )


# codex-sequence-2026-08-08: contractDeps roots are explicit, nonblocking DAG provenance.
def _dag_capabilities(data: dict, warnings: list[str], relpath: str) -> dict[str, set[str]]:
    """Return the story slugs explicitly nested under each DAG capability.

    This intentionally reads only the top-level ``capabilities`` container and
    its ``stories`` descendants.  A capability's prose ``foundations`` list,
    milestone gates, and arbitrary constraint-shaped JSON are not contract
    roots, so treating them as one would manufacture architectural edges.
    """
    raw_capabilities = data.get("capabilities")
    if raw_capabilities is None:
        return {}
    if isinstance(raw_capabilities, list):
        entries = [(None, entry) for entry in raw_capabilities]
    elif isinstance(raw_capabilities, dict):
        entries = list(raw_capabilities.items())
    else:
        warnings.append(f"{relpath}: malformed capabilities ignored for contract roots")
        return {}

    capabilities: dict[str, set[str]] = {}
    for keyed_slug, capability in entries:
        if not isinstance(capability, dict):
            continue
        candidate = capability.get("slug") or capability.get("id") or keyed_slug
        if isinstance(candidate, str) and candidate.startswith("CAP-"):
            candidate = candidate[4:]
        if not isinstance(candidate, str) or not _DEP_SLUG_RE.fullmatch(candidate):
            continue

        stories: set[str] = set()
        visited = 0

        def walk(node, depth: int, inside_stories: bool = False) -> None:
            nonlocal visited
            if visited >= _MAX_DAG_JSON_NODES:
                return
            visited += 1
            if isinstance(node, dict):
                slug = node.get("slug")
                if inside_stories and isinstance(slug, str) and _DEP_SLUG_RE.fullmatch(slug):
                    stories.add(slug)
                children = [
                    (child, inside_stories or key == "stories")
                    for key, child in node.items()
                ]
            elif isinstance(node, list):
                children = [(child, inside_stories) for child in node]
            else:
                return
            if depth < _MAX_DAG_JSON_DEPTH:
                for child, child_inside_stories in children:
                    walk(child, depth + 1, child_inside_stories)
                    if visited >= _MAX_DAG_JSON_NODES:
                        break

        walk(capability, 0)
        capabilities[candidate] = stories
    return capabilities


def _foundation_roots(data: dict, warnings: list[str], relpath: str) -> tuple[
        dict[str, set[str]], list[Group]]:
    """Parse the explicit ``contractDeps.roots`` seam, if present.

    The return value maps story slug to root slugs.  Relations remain
    nonblocking provenance: no dependency or priority input is modified here.
    """
    contract_deps = data.get("contractDeps")
    if contract_deps is None:
        return {}, []
    if not isinstance(contract_deps, dict) or not isinstance(contract_deps.get("roots"), dict):
        warnings.append(f"{relpath}: malformed contractDeps.roots ignored")
        return {}, []

    capabilities = _dag_capabilities(data, warnings, relpath)
    story_roots: dict[str, set[str]] = {}
    groups = []
    for root_slug, raw_capabilities in sorted(contract_deps["roots"].items()):
        if not isinstance(root_slug, str) or not _DEP_SLUG_RE.fullmatch(root_slug):
            warnings.append(f"{relpath}: malformed contract root ignored")
            continue
        if not isinstance(raw_capabilities, list):
            warnings.append(f"{relpath}: contract root {root_slug} must map to a list of capabilities")
            continue

        matched_capabilities = set()
        for capability_slug in raw_capabilities:
            if not isinstance(capability_slug, str) or not _DEP_SLUG_RE.fullmatch(capability_slug):
                warnings.append(f"{relpath}: contract root {root_slug} has malformed capability")
                continue
            if capability_slug not in capabilities:
                warnings.append(
                    f"{relpath}: contract root {root_slug} references unknown capability "
                    f"{capability_slug}"
                )
                continue
            matched_capabilities.add(capability_slug)

        # Do not add a decorative orphan node for a root that has no valid
        # capability relationship.  It would claim graph evidence we do not have.
        if not matched_capabilities:
            continue
        groups.append(Group(
            id=f"foundation:{root_slug}",
            kind="foundation",
            title=root_slug.replace("-", " ").title(),
        ))
        for capability_slug in matched_capabilities:
            for story_slug in capabilities[capability_slug]:
                story_roots.setdefault(story_slug, set()).add(root_slug)
    return story_roots, groups


def _dag_items(root: Path, dag_relpath: str, item_kind: str,
               warnings: list[str]) -> tuple[list[Item], list[Milestone], list[Group]]:
    path = root / dag_relpath
    relpath = Path(dag_relpath).as_posix()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError, RecursionError):
        warnings.append(f"{relpath}: unreadable or malformed DAG")
        return [], [], []

    story_roots, foundation_groups = (
        _foundation_roots(data, warnings, relpath)
        if isinstance(data, dict) else ({}, [])
    )

    work_records = []
    story_records = []
    visited = 0
    found_stories_container = False

    def walk(node, depth: int, inside_stories: bool = False) -> None:
        nonlocal visited, found_stories_container
        if visited >= _MAX_DAG_JSON_NODES:
            return
        visited += 1

        if isinstance(node, dict):
            slug = node.get("slug")
            if (isinstance(slug, str) and slug.strip()
                    and _WORK_ITEM_KEYS.intersection(node)):
                work_records.append(node)
                if inside_stories:
                    story_records.append(node)
            children = []
            for key, child in node.items():
                is_stories_container = (
                    key == "stories" and isinstance(child, (dict, list))
                )
                if is_stories_container:
                    found_stories_container = True
                children.append((child, inside_stories or is_stories_container))
        elif isinstance(node, list):
            children = [(child, inside_stories) for child in node]
        else:
            return

        if depth < _MAX_DAG_JSON_DEPTH:
            for child, child_inside_stories in children:
                walk(child, depth + 1, child_inside_stories)
                if visited >= _MAX_DAG_JSON_NODES:
                    break

    walk(data, 0)

    items = []
    seen_slugs = set()
    records = story_records if found_stories_container else work_records
    for node in records:
        slug = node["slug"]
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        items.append(Item(
            id=f"{item_kind}:{slug}",
            title=str(node.get("title") or slug),
            one_liner=(str(node["oneLiner"])
                       if node.get("oneLiner") is not None else None),
            status=str(node.get("status") or "unknown"),
            release=(str(node["release"])
                     if node.get("release") is not None else None),
            wave=(str(node["wave"])
                  if node.get("wave") is not None else None),
            deps=_dep_ids(node.get("deps", []), item_kind),
            role="delivery",
            tags=_string_list(node.get("tags", [])),
            facets={key: values for key, values in (
                ("product", _string_list(node.get("products", []))),
                ("capability", _string_list(node.get("productCapabilities", []))),
            ) if values},
            relations=[
                Relation(kind="foundation_root", target=f"foundation:{root_slug}")
                for root_slug in sorted(story_roots.get(slug, set()))
            ],
            source={"adapter": "dag_import", "path": relpath},
        ))

    if not items:
        warnings.append(f"{relpath}: malformed DAG entries ignored")

    # codex-sequence-2026-08-08: preserve optional DAG milestones without
    # promoting the derived graph to a new source of truth.
    milestones = []
    raw_milestones = data.get("milestones", []) if isinstance(data, dict) else []
    if raw_milestones is not None and not isinstance(raw_milestones, list):
        warnings.append(f"{relpath}: malformed milestones ignored")
        raw_milestones = []
    for raw in raw_milestones:
        if not isinstance(raw, dict):
            warnings.append(f"{relpath}: malformed milestone ignored")
            continue
        milestone_id = raw.get("id")
        title = raw.get("title")
        phases = raw.get("phases", [])
        if not isinstance(milestone_id, str) or not isinstance(title, str) \
                or not isinstance(phases, list):
            warnings.append(f"{relpath}: malformed milestone ignored")
            continue
        parsed_phases = []
        for phase in phases:
            if not isinstance(phase, dict) or not isinstance(phase.get("name"), str):
                warnings.append(f"{relpath}: malformed milestone phase ignored")
                continue
            parsed_phases.append(MilestonePhase(
                name=phase["name"],
                items=_dep_ids(phase.get("stories", []), item_kind),
            ))
        milestones.append(Milestone(
            id=milestone_id,
            title=title,
            goal=str(raw.get("goal") or ""),
            phases=parsed_phases,
        ))
    return (sorted(items, key=lambda item: item.id),
            sorted(milestones, key=lambda milestone: milestone.id),
            sorted(foundation_groups, key=lambda group: group.id))


def scan(cfg, root: Path) -> ScanResult:
    """Scan configured spec-tree files and an optional legacy DAG."""
    root = Path(root)
    pattern = cfg.get("sources.spec_tree.glob", "")
    levels = list(cfg.get("sources.spec_tree.levels", []))
    item_kind = cfg.get("sources.spec_tree.item_kind", "story")
    product_tags = set(cfg.get("sources.spec_tree.product_tags", []))
    warnings = []
    groups: dict[str, Group] = {}
    items = []
    milestones = []

    foundation_index = cfg.get("sources.spec_tree.foundation_index", "")
    if foundation_index:
        for group in _foundation_index_groups(root, foundation_index, warnings):
            groups[group.id] = group

    if pattern:
        try:
            paths = sorted(root.glob(pattern), key=lambda path: path.as_posix())
        except (NotImplementedError, ValueError, OSError):
            warnings.append(f"spec tree glob unusable: {pattern}")
            paths = []
        for path in paths:
            if path.name.startswith("_") or not path.is_file():
                continue
            item = _scan_file(path, root, pattern, levels, item_kind,
                              groups, warnings, product_tags)
            if item is not None:
                items.append(item)

    dag_relpath = cfg.get("sources.spec_tree.dag_import", "")
    if dag_relpath:
        dag_items, dag_milestones, dag_groups = _dag_items(
            root, dag_relpath, item_kind, warnings
        )
        items.extend(dag_items)
        milestones.extend(dag_milestones)
        for group in dag_groups:
            if group.id in groups:
                existing = groups[group.id]
                if existing.kind != "foundation" or group.kind != "foundation":
                    warnings.append(
                        f"{dag_relpath}: foundation group {group.id} collides with scanned group"
                    )
            else:
                groups[group.id] = group

    return ScanResult(
        groups=list(groups.values()),
        items=items,
        milestones=milestones,
        warnings=warnings,
    )
