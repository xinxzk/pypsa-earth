# Custom workflow targets for CSG-focused China clustering.
#
# This file is included from playground/config/config.cn2035.csg_focus.yaml.


rule csg_focus_workflow:
    input:
        expand(
            "results/"
            + RDIR
            + "networks/elec_s{simpl}_{clusters}_ec_l{ll}_{opts}.nc",
            **config["scenario"],
        )


rule csg_focus_clustered:
    input:
        expand(
            "networks/" + RDIR + "elec_s{simpl}_{clusters}.nc",
            **config["scenario"],
        )


rule csg_focus_busmap:
    input:
        network="networks/" + RDIR + "elec_s.nc",
        provinces="playground/res/china_map/\u7701\u7ea7\u884c\u653f\u533a.shp",
        script="playground/scripts/generate_custom_busmap_csg_focus.py",
    output:
        "data/custom_busmap_elec_s_51.csv"
    log:
        "logs/" + RDIR + "custom_busmap/csg_focus_busmap.log"
    benchmark:
        "benchmarks/" + RDIR + "custom_busmap/csg_focus_busmap"
    shell:
        "python {input.script} "
        "--network {input.network} "
        "--provinces {input.provinces} "
        "--output {output} "
        "> {log} 2>&1"
