# ADR-0003: Money as integer minor units; dimension-safe units

Money is stored as integer øre with explicit currency (`Money`), constructed
from Decimal strings; floats are rejected. Quantities use a `Unit` enum with a
`Dimension` (MASS / VOLUME / COUNT). Conversions are only allowed within a
dimension; mass↔volume requires a documented product-specific density and
otherwise raises `UnitConversionUnknown`. The optimizer works in integer base
units; objective weights are documented øre-equivalents (see ARCHITECTURE.md).
