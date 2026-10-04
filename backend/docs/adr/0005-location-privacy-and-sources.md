# ADR-0005: Location minimisation and data-source compliance

Households are located by postal code (centroid lookup); coordinates are
optional. Distances are haversine × a documented detour factor and are labelled
`STRAIGHT_LINE_APPROX`; a routing provider can replace `DistanceProvider`.
Location is stored on the household document only; it is never logged.

Each source adapter declares a `ComplianceClass` (OFFICIAL_API, LICENSED_FEED,
PUBLIC_PAGE, USER_SUPPLIED, OTHER) and freshness SLA before use. Sources that
cannot be automated lawfully/stably are served through the manual/import adapter.
No adapter circumvents access controls.

Retention (initial policy): raw offers and price observations are kept for
historical reference pricing; plans are immutable snapshots owned by the
household and deleted with it; feedback is kept per household.
