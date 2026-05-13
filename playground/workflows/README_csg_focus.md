# CSG-Focused China Workflow

This workflow keeps the existing China setup but changes the clustering to 51
nodes:

- CSG: 40
- Northeast: 1
- North China: 2
- East China: 2
- Central China outside CSG: 2
- Northwest: 2
- Tibet/Xinjiang: 2

The original regional design summed to 50 nodes, but Tibet/Xinjiang contains
both AC and DC buses. PyPSA does not allow AC and DC buses to be aggregated into
the same bus cluster, so this workflow uses 51 clusters to keep bus carriers
consistent.

## Files

- `playground/config/config.cn2035.csg_focus.yaml`
- `playground/workflows/csg_focus.smk`
- `playground/scripts/generate_custom_busmap_csg_focus.py`
- `data/custom_busmap_elec_s_51.csv`

## Run

Dry-run the custom busmap step:

```bash
snakemake -j 1 data/custom_busmap_elec_s_51.csv \
  --configfile playground/config/config.cn2035.csg_focus.yaml \
  --rerun-triggers mtime -n -r
```

Dry-run through the clustered network:

```bash
snakemake -j 1 csg_focus_clustered \
  --configfile playground/config/config.cn2035.csg_focus.yaml \
  --rerun-triggers mtime -n -r
```

Dry-run the full power-system workflow:

```bash
snakemake -j 1 csg_focus_workflow \
  --configfile playground/config/config.cn2035.csg_focus.yaml \
  --rerun-triggers mtime -n -r
```

The run name is `CN_power_2035_ssp226_CSG50`, so outputs are written under:

```text
networks/CN_power_2035_ssp226_CSG50/
resources/CN_power_2035_ssp226_CSG50/
results/CN_power_2035_ssp226_CSG50/
```
