import pypsa
from scipy.spatial import cKDTree

print("Loading elec_s.nc ...")
path = "networks/CN_power_2035_ssp226/elec_s.nc"
n = pypsa.Network(path)
n.determine_network_topology()

main_grid_id = n.buses.groupby("sub_network").size().idxmax()
main_buses = n.buses[n.buses.sub_network == main_grid_id]

print(f"Islands before fix: {len(n.buses.sub_network.unique()) - 1}")

# ── 步骤1：修复 DC Link 孤立端 ─────────────────────────────
island_buses = n.buses[n.buses.sub_network != main_grid_id]
tree = cKDTree(main_buses[["x", "y"]].values)
fixed_links = 0

for link_id, link in n.links.iterrows():
    b0_is_island = link.bus0 in island_buses.index
    b1_is_island = link.bus1 in island_buses.index

    if b0_is_island and not b1_is_island:
        iso_bus = n.buses.loc[link.bus0]
        _, idx = tree.query([iso_bus.x, iso_bus.y])
        n.links.loc[link_id, "bus0"] = main_buses.index[idx]
        fixed_links += 1
    elif b1_is_island and not b0_is_island:
        iso_bus = n.buses.loc[link.bus1]
        _, idx = tree.query([iso_bus.x, iso_bus.y])
        n.links.loc[link_id, "bus1"] = main_buses.index[idx]
        fixed_links += 1

print(f"Fixed {fixed_links} DC links.")

# ── 步骤2：重新计算拓扑 ────────────────────────────────────
n.determine_network_topology()
main_grid_id = n.buses.groupby("sub_network").size().idxmax()
main_buses = n.buses[n.buses.sub_network == main_grid_id]
tree = cKDTree(main_buses[["x", "y"]].values)

still_island_buses = n.buses[n.buses.sub_network != main_grid_id]
print(f"Remaining isolated buses: {len(still_island_buses)}")

# ── 步骤3：迁移所有组件到最近主网节点 ─────────────────────
all_bus_cols = ["bus", "bus0", "bus1", "bus2", "bus3", "bus4"]

for iso_id in still_island_buses.index:
    iso_bus = n.buses.loc[iso_id]
    _, idx = tree.query([iso_bus.x, iso_bus.y])
    nearest_main = main_buses.index[idx]

    # 迁移 loads / generators / storage_units
    for comp in [n.loads, n.generators, n.storage_units]:
        if not comp.empty and "bus" in comp.columns:
            comp.loc[comp.bus == iso_id, "bus"] = nearest_main

    # 迁移 links 所有 bus 列
    for col in all_bus_cols:
        if col in n.links.columns:
            n.links.loc[n.links[col] == iso_id, col] = nearest_main

    # 迁移 lines
    for col in ["bus0", "bus1"]:
        if col in n.lines.columns:
            n.lines.loc[n.lines[col] == iso_id, col] = nearest_main

print(f"Migrated {len(still_island_buses)} isolated buses.")

# ── 步骤4：删除引用了不存在 bus 的 Links（悬空 Links）──────
valid_buses = set(n.buses.index)


def find_invalid_links(links, valid_buses):
    invalid = []
    for link_id, link in links.iterrows():
        for col in ["bus0", "bus1"]:
            if link[col] not in valid_buses:
                invalid.append(link_id)
                break
    return invalid


invalid_links = find_invalid_links(n.links, valid_buses)
if invalid_links:
    print(f"Removing {len(invalid_links)} links with undefined buses: {invalid_links[:5]}...")
    n.remove("Link", invalid_links)

# 同样检查 lines
invalid_lines = []
for line_id, line in n.lines.iterrows():
    if line.bus0 not in valid_buses or line.bus1 not in valid_buses:
        invalid_lines.append(line_id)
if invalid_lines:
    print(f"Removing {len(invalid_lines)} lines with undefined buses.")
    n.remove("Line", invalid_lines)

# ── 步骤5：删除孤立节点 ───────────────────────────────────
n.remove("Bus", still_island_buses.index.tolist())
print(f"Removed {len(still_island_buses)} orphan buses.")

# ── 步骤6：最终验证 ───────────────────────────────────────
n.determine_network_topology()
remaining_islands = len(n.buses.sub_network.unique()) - 1
print("\n=== Final Result ===")
print(f"Islands after fix : {remaining_islands}")
print(f"Total buses       : {len(n.buses)}")
print(f"Total lines       : {len(n.lines)}")
print(f"Total links       : {len(n.links)}")

# 一致性检查
all_buses = set(n.buses.index)
broken_links = find_invalid_links(n.links, all_buses)
if broken_links:
    print(f"⚠ Still broken links: {len(broken_links)}")
else:
    print("✓ No broken links.")

n.export_to_netcdf(path)
print("Saved fixed network to elec_s.nc")
