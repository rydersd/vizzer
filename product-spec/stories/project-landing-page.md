# Show the product library on the project landing page

> Status: shipped
> Deps: []
> Release: R1
> Tags: dashboard, documentation

## Intent

The self-host dashboard showed only two intake recommendations while product
contracts and documentation were buried behind role filters. Expose the project
library and work register directly, and open references as readable documents.

## Acceptance criteria

- Six configured project documents appear on the default dashboard.
- Document shortcuts remain available independently of delivery filters.
- The work register includes shipped and pending work under active filters.
- References open their Markdown body rather than empty delivery review fields.
- Unconfigured projects retain their existing candidate dashboard.

## Verification — 2026-09-05

74 focused renderer tests passed (physical-browser selector excluded); the
additional project-document resolution test passed. It excludes unconfigured,
missing and delivery sources from the reference shortcuts. Live landing-page
inspection verified all six shortcuts and the work register.

Live document opening initially stalled alongside other server requests. The
local LaunchAgent was changed from Background to Interactive scheduling and
reloaded; the document endpoint then returned HTTP 200 and the browser displayed
the actual capability table. This establishes recovery, not a complete diagnosis
of macOS scheduling. The full document reader was verified after that change.
