# Active and recent work keyboard navigation

Owner request: while a Story dossier is open, arrow keys provide a fast,
filter-independent way to traverse work records without returning to the graph
or a routed card view.

## Contract

- Left and Right traverse Stories with a fresh `active` activity record.
- Up and Down traverse Stories represented by any retained activity record,
  newest checkpoint first.
- Right and Down move toward older work; Left and Up move toward newer work.
- Both lanes wrap. If the selected Story is not in the chosen lane, the first
  key press opens that lane's newest Story.
- A Story appears once per lane. Its newest qualifying activity timestamp owns
  its position; serialized record order is not navigation order.
- Navigation ignores current search, lifecycle, release, area, capability, and
  role filters. Those filters describe a view; they do not erase recorded work.
- Navigation is active only while the Story dossier is open. It must not steal
  arrow keys from text fields, radios, selects, editable content, the resizable
  drawer separator, modified key chords, or an already-handled event.
- The dossier exposes the available lane counts and keyboard bindings rather
  than making the shortcut a séance.

## Named acceptance

- `test_constellation_work_keyboard_navigation_executes_recency_and_focus_contract`
- `test_constellation_work_keyboard_navigation_physical_browser_smoke`
- `test_constellation_composes_frontend_sources_into_one_dependency_free_artifact`

The strongest ordering counterexample deliberately serializes work in Story-ID
order that disagrees with timestamp order, includes duplicate records for one
Story, and includes a stale `active` record. A correct implementation must
deduplicate by Story, sort by the newest qualifying timestamp, and exclude the
stale record only from the active lane.
