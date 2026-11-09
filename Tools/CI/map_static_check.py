#!/usr/bin/env python3
"""License-independent, read-only, deterministic checks for the actual map layout.

This is a blueprint/data QA; it does not claim to render or edit Unity's native
binary TerrainData/scene. The native asset writers live in Tools/MapBuild.
"""
import argparse
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAYOUT = ROOT / "Docs/MAP_LAYOUT.json"

def distance_to_segment(px, pz, ax, az, bx, bz):
    dx, dz = bx - ax, bz - az
    t = max(0.0, min(1.0, ((px - ax)*dx + (pz - az)*dz) /
                        (dx*dx + dz*dz))) if dx*dx + dz*dz > 1e-12 else 0.0
    return math.hypot(px - ax - t*dx, pz - az - t*dz)

def segment_intersects_aabb_xz(a, b, box, margin=0.0):
    """Conservative 2D swept-segment/AABB clearance for map blueprint QA.

    The road polyline is padded by half its authored width + 1 m.
    A positive result is a review blocker; it does not prove 3D collision.
    """
    x0, z0, x1, z1 = box
    x0 -= margin
    z0 -= margin
    x1 += margin
    z1 += margin
    ax, az = a[0], a[2]
    dx, dz = b[0]-ax, b[2]-az
    enter, leave = 0.0, 1.0
    for p, q in ((-dx, ax-x0), (dx, x1-ax),
                 (-dz, az-z0), (dz, z1-az)):
        if abs(p) <= 1e-12:
            if q < 0.0:
                return False
            continue
        bound = q/p
        if p < 0.0:
            enter = max(enter, bound)
        else:
            leave = min(leave, bound)
        if enter > leave:
            return False
    return True


def road_distance(road, x, z):
    points = road["points"]
    if len(points) == 1:
        return math.hypot(x - points[0][0], z - points[0][2])
    return min(distance_to_segment(x,z,a[0],a[2],b[0],b[2])
               for a,b in zip(points,points[1:]))

def inspect(layout, x, z):
    def dpos(item):
        a,b,c = item["position_m"]
        return math.hypot(x-a,z-c)
    nearest_buildings = sorted(layout["buildings"],key=dpos)[:5]
    nearest_spawns = sorted(layout["vehicle_spawns"],key=dpos)[:5]
    nearest_roads = sorted(layout["roads"],
                           key=lambda road:road_distance(road,x,z))[:3]
    return {
        "requested_xz_m":[x,z],
        "buildings":[{"name":b["name"],"model":b["model"],
                      "height_m":b["world_dimensions_m"][1],
                      "distance_m":round(dpos(b),2)}
                     for b in nearest_buildings],
        "vehicle_spawns":[{"name":s["name"],"distance_m":round(dpos(s),2)}
                          for s in nearest_spawns],
        "roads":[{"name":road["name"],
                  "distance_m":round(road_distance(road,x,z),2)}
                 for road in nearest_roads],
        "note":"Blueprint only; native terrain elevation, imported meshes and real rendered appearance are not tested."
    }

def check(layout):
    checks = {}
    def assert_check(name, condition, detail):
        checks[name] = {"passed":bool(condition), "detail":detail}
        if not condition:
            raise AssertionError(name + ": " + str(detail))
    assert_check("metres_and_2km", layout.get("world_units")=="metres" and
                 layout.get("size_m")==[2000,2000],layout.get("size_m"))
    x0,z0,x1,z1 = layout["terrain_bounds_xz_m"]
    assert_check("bounds", [x0,z0,x1,z1]==[-1000,-1000,1000,1000],
                 [x0,z0,x1,z1])
    districts,buildings,roads,spawns = [layout[key] for key in
        ("districts","buildings","roads","vehicle_spawns")]
    assert_check("districts_13", len(districts)==13,len(districts))
    assert_check("buildings_59", len(buildings)==59,len(buildings))
    assert_check("roads_39",len(roads)==39,len(roads))
    assert_check("vehicle_spawns_45",len(spawns)==45,len(spawns))
    assert_check("terrain_tiles_4",len(layout["tile_reports"])==4,
                 len(layout["tile_reports"]))
    district_names={d["name"] for d in districts}
    names=[b["name"] for b in buildings]+[s["name"] for s in spawns]
    assert_check("unique_object_names",len(names)==len(set(names)),len(names))
    assert_check("building_district_references",
                 all(b["district"] in district_names for b in buildings),
                 len(buildings))
    assert_check("spawn_district_references",
                 all(s["district"] in district_names for s in spawns),
                 len(spawns))
    def point_in_bounds(x,z):
        return x0<=x<=x1 and z0<=z<=z1
    assert_check("building_centers_in_bounds",
                 all(point_in_bounds(b["position_m"][0],b["position_m"][2])
                     for b in buildings),len(buildings))
    assert_check("spawn_centers_in_bounds",
                 all(point_in_bounds(s["position_m"][0],s["position_m"][2])
                     for s in spawns),len(spawns))
    assert_check("road_lines_in_bounds",
                 all(point_in_bounds(p[0],p[2]) and all(math.isfinite(a) for a in p)
                     for road in roads for p in road["points"]),
                 len(roads))
    overlap=[]
    for i,a in enumerate(buildings):
        q=a["aabb_xz_m"]
        for b in buildings[i+1:]:
            t=b["aabb_xz_m"]
            if q[0]<t[2] and q[2]>t[0] and q[1]<t[3] and q[3]>t[1]:
                overlap.append([a["name"],b["name"]])
    assert_check("building_bounding_boxes_do_not_overlap",
                 not overlap,overlap[:10])
    colliding_spawns=[]
    for s in spawns:
        sx,_,sz=s["position_m"]
        for b in buildings:
            x0b,z0b,x1b,z1b=b["aabb_xz_m"]
            if x0b-2 < sx < x1b+2 and z0b-2 < sz < z1b+2:
                colliding_spawns.append([s["name"],b["name"]])
    assert_check("vehicle_spawns_clear_from_buildings",
                 not colliding_spawns,colliding_spawns[:10])
    # Do not let an expanded house block an authored road. The 1 m guard
    # is intentionally conservative around the road's rendered half-width.
    # This checks blueprint XY projections only, not native physics colliders.
    road_conflicts=[]
    for road in roads:
        points=road["points"]
        width=road["width"]
        if not (isinstance(width,(int,float)) and math.isfinite(width)
                and 1.0 <= width <= 24.0 and len(points) >= 2):
            road_conflicts.append([road["name"],"INVALID_ROAD"])
            continue
        padding=width*0.5+1.0
        for building in buildings:
            if any(segment_intersects_aabb_xz(a,b,building["aabb_xz_m"],padding)
                   for a,b in zip(points,points[1:])):
                road_conflicts.append([road["name"],building["name"]])
    assert_check("roads_clear_of_buildings_with_one_metre_edge_guard",
                 not road_conflicts,road_conflicts[:12])

    # A garage/vehicle marker's reserved exit must not cross a building.
    # Collision after spawning cannot be solved by moving its icon alone.
    exit_conflicts=[]
    for spawn in spawns:
        start=spawn["position_m"]
        end=[spawn["exit_world_xz_m"][0], start[1],
             spawn["exit_world_xz_m"][1]]
        for building in buildings:
            if segment_intersects_aabb_xz(start,end,building["aabb_xz_m"],1.0):
                exit_conflicts.append([spawn["name"],building["name"]])
    assert_check("garage_vehicle_exit_routes_clear_of_buildings",
                 not exit_conflicts,exit_conflicts[:12])
    return {"result":"passed","source":"Docs/MAP_LAYOUT.json",
            "checks":checks,"measures":{"districts":len(districts),
            "buildings":len(buildings),"roads":len(roads),
            "vehicle_spawns":len(spawns)}}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("command",choices=["audit","inspect"])
    parser.add_argument("--x",type=float,default=0)
    parser.add_argument("--z",type=float,default=0)
    parser.add_argument("--out",default="ci-map-report.json")
    args=parser.parse_args()
    layout=json.loads(LAYOUT.read_text())
    result=check(layout)
    if args.command=="inspect":
        if not (-1000<=args.x<=1000 and -1000<=args.z<=1000):
            parser.error("coordinates must stay inside the saved 2km terrain")
        result["inspection"]=inspect(layout,args.x,args.z)
    path=Path(args.out)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))

if __name__=="__main__":
    main()
