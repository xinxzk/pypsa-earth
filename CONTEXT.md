# PyPSA-Earth China Planning Context

This context defines project-specific planning language for China-focused PyPSA-Earth transmission and capacity expansion studies.

## Language

**China Backbone Transmission Network**:
The transmission network represented in the main China planning cases, defined as AC and DC transmission assets at 220 kV and above. 110 kV assets are excluded from the main backbone case and reserved for sensitivity analysis or finer provincial-network studies.
_Avoid_: Full grid, all-voltage grid, distribution grid

**Equivalent Load Connection**:
The allocation of electricity demand to the retained backbone bus regions after lower-voltage assets are filtered out. The total load is preserved, but its spatial connection points are represented by the remaining backbone buses.
_Avoid_: Dropped load, ignored 110 kV load

**500 kV Equivalent AC Layer**:
The single AC voltage layer used by `simplify_network` for the main China backbone cases. It is a planning approximation for the multi-voltage AC backbone, not a claim that every retained AC asset is physically 500 kV.
_Avoid_: Physical 500 kV-only grid, UHV-only grid

**Provisional Line Type**:
A configured line type whose values are based on common engineering assumptions or temporary estimates rather than a citable standard, institutional source, DOI, or project document. It may be used to validate the workflow, but must be marked with `!` and `TODO` near the configuration so it is not mistaken for publication-grade data.
_Avoid_: Final line parameter, validated line type

**Traceable Planning Line Type**:
A configured line type whose source notes explain which values are directly sourced and which values are inferred or provisional. It is acceptable for planning workflow validation, but it is not a validated line type unless all key electrical parameters are backed by China-specific standards, publications, or project documents.
_Avoid_: Validated line type, final line parameter
