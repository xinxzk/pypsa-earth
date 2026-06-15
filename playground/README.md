# China Playground

This directory contains China-specific scenario assets and exploratory analysis for the PyPSA-Earth workflow.

## Tracked Inputs

- `config/`: China scenario configurations and scenario-owned assumptions, including `china_line_types.yaml`.
- `workflows/`: optional Snakemake rules included by China scenarios.
- `scripts/`: reusable helpers called by workflow rules or documented run instructions.
- `analysis_scripts/`: exploratory or post-processing scripts. These may contain hard-coded local network paths and are not part of the reproducible workflow unless promoted into `scripts/` and documented.

## Generated Outputs

Generated figures, CSVs, NetCDF files, local resources, and result folders are ignored by `playground/.gitignore`. Keep reusable inputs and workflow helpers outside ignored output directories.

## China Scenarios

- `config/config.cn2030.yaml`: main 2030 China planning case.
- `config/config.cn2035.yaml`: main 2035 China planning case.
- `config/config.cn2035.csg_focus.yaml`: China Southern Grid focused 2035 case with a custom busmap workflow.

The main China planning cases use the China Backbone Transmission Network scope documented in `../CONTEXT.md` and the ADRs in `../doc/adr/`.
