#!/usr/bin/env python3
"""Create REAL layout-derived map QA diagrams without launching Unity.

These schematics use native project Docs/MAP_LAYOUT.json coordinates and stored
footprints. They are NOT Unity screenshots and do not validate URP materials,
trees, lighting or exact Unity import. Intended for repeatable, license-free CI.
"""
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "ci-layout-preview"
WORLD = ROOT / "Docs/MAP_LAYOUT.json"
WIDTH, HEIGHT = 1920, 1080

COL = {
    "background": "#0c1927", "map": "#172c38", "shore": "#233b48",
    "grid": "#294653", "water": "#0b435d", "road_edge": "#77828b",
    "road": "#d9c28e", "house": "#d88a6c", "roof": "#ffd7b4",
    "spawn": "#56d4bd", "district": "#e8edf1", "text": "#edf7fc",
    "dim": "#a9c0cb", "accent": "#7ed0ed", "outline": "#0a1d27"
}

def font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for location in candidates:
        if Path(location).is_file():
            return ImageFont.truetype(location, size)
    return ImageFont.load_default()

def snapshot(layout, file_name, heading, bounds, summary):
    image = Image.new("RGB", (WIDTH, HEIGHT), COL["background"])
    draw = ImageDraw.Draw(image)
    draw.text((75, 44), heading, fill=COL["text"], font=font(35, True))
    draw.text((77, 102), "AARIS ISLAND  |  VERIFIED LAYOUT COORDINATES  |  NOT A UNITY RENDER",
              fill=COL["accent"], font=font(18,True))

    # Fit a square geographical viewport, with an uncluttered right-side panel.
    left, top, side = 79, 162, 838
    draw.rounded_rectangle((left-9,top-9,left+side+9,top+side+9),
                           radius=14, fill=COL["shore"])
    draw.rectangle((left,top,left+side,top+side), fill=COL["map"])
    x0,z0,x1,z1=bounds
    scale = side/(x1-x0)
    def pt(x,z):
        return (int(left + (x-x0)*scale),int(top + (z1-z)*scale))

    # 250-meter grid in world space, fixed across all images.
    import math
    for x in range(int(math.ceil(x0/250)*250), int(x1)+1,250):
        a=pt(x,z0);b=pt(x,z1)
        draw.line((a,b),fill=COL["grid"],width=1)
        draw.text((a[0]+3,top+4),str(x),fill=COL["dim"],font=font(12))
    for z in range(int(math.ceil(z0/250)*250),int(z1)+1,250):
        a=pt(x0,z);b=pt(x1,z)
        draw.line((a,b),fill=COL["grid"],width=1)
        draw.text((left+3,a[1]+3),str(z),fill=COL["dim"],font=font(12))

    # Trace source polylines, without inventing segments or changing placement.
    for road in layout["roads"]:
        points=[pt(p[0],p[2]) for p in road["points"]]
        if len(points)<2:continue
        width=max(2,min(13,int(road.get("width",8)*scale)))
        draw.line(points,fill=COL["road_edge"],width=width+3,joint="curve")
        draw.line(points,fill=COL["road"],width=width,joint="curve")

    # Exact X/Z bounding boxes come from layout world_dimensions and source placement.
    for building in layout["buildings"]:
        xlo,zlo,xhi,zhi=building["aabb_xz_m"]
        if xhi<x0 or xlo>x1 or zhi<z0 or zlo>z1:continue
        a=pt(xlo,zhi);b=pt(xhi,zlo)
        draw.rectangle((a[0],a[1],b[0],b[1]),fill=COL["house"],
                       outline=COL["roof"],width=2)

    for spawn in layout["vehicle_spawns"]:
        x,y,z=spawn["position_m"]
        if x0<=x<=x1 and z0<=z<=z1:
            a,b=pt(x,z)
            draw.ellipse((a-4,b-4,a+4,b+4),fill=COL["spawn"],
                         outline=COL["outline"],width=1)

    for district in layout["districts"]:
        x,z=district["x"],district["z"]
        if x0<=x<=x1 and z0<=z<=z1:
            a,b=pt(x,z)
            draw.ellipse((a-3,b-3,a+3,b+3),fill=COL["text"])
            label=district["name"]
            # Labels will overlap at full-world scale, so only show all on tiles.
            if side/(x1-x0) >= .8:
                draw.text((a+8,b-20),label,fill=COL["text"],
                          font=font(15,True),stroke_width=2,
                          stroke_fill=COL["background"])
    # Hard clipping is implicit for the viewport selection; neighboring context
    # is still present if part of a road crosses its boundary.
    panel_x=980
    draw.text((panel_x,165),"MAP REVIEW",font=font(28,True),fill=COL["text"])
    draw.line((panel_x,212,1840,212),fill=COL["grid"],width=2)
    details=[
        ("Area", "2 km x 2 km"),
        ("Districts", str(len(layout["districts"]))),
        ("Saved buildings", str(len(layout["buildings"]))),
        ("Saved roads", str(len(layout["roads"]))),
        ("Vehicle markers", str(len(layout["vehicle_spawns"]))),
        ("Native terrain tiles", str(len(layout["tile_reports"]))),
    ]
    y=238
    for key,value in details:
        draw.text((panel_x,y),key,fill=COL["dim"],font=font(19))
        draw.text((panel_x+495,y),value,fill=COL["text"],font=font(19,True))
        y+=53
    y+=35
    draw.text((panel_x,y),"LEGEND",fill=COL["text"],font=font(22,True))
    y+=50
    for label,key in [("Road centerlines","road"),("Building footprints","house"),
                      ("Vehicle spawn markers","spawn"),("District center","district")]:
        draw.rounded_rectangle((panel_x,y+3,panel_x+28,y+26),radius=4,
                               fill=COL[key])
        draw.text((panel_x+45,y),label,fill=COL["text"],font=font(19))
        y+=49
    y+=24
    for line in summary:
        draw.text((panel_x,y),line,fill=COL["dim"],font=font(17))
        y+=30
    draw.text((panel_x,938),"Data source: Docs/MAP_LAYOUT.json",fill=COL["accent"],
              font=font(17))
    draw.text((panel_x,971),"No synthetic URP/house textures are claimed.",fill=COL["dim"],
              font=font(16))
    draw.text((980,1010),"North (+Z) is at the top",fill=COL["dim"],font=font(16))
    out=OUTPUT/file_name
    image.save(out,optimize=True)
    return {"name":file_name,"size":out.stat().st_size,
            "sha256":hashlib.sha256(out.read_bytes()).hexdigest(),
            "bounds_xz_m":list(bounds)}

def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    layout=json.loads(WORLD.read_text())
    if layout["size_m"]!=[2000,2000] or len(layout["tile_reports"])!=4:
        raise RuntimeError("Unexpected map layout: refusing to publish stale diagrams")
    views=[
        ("01_world_overview.png","ENTIRE 2KM ISLAND",(-1000,-1000,1000,1000),
         ["Complete map overview","Shapes are stored bounding boxes"]),
        ("02_southwest.png","SOUTH-WEST TERRAIN TILE",(-1000,-1000,0,0),
         ["Southern residential/forest area","1 km by 1 km detail"]),
        ("03_southeast.png","SOUTH-EAST TERRAIN TILE",(0,-1000,1000,0),
         ["Airfield, coast and roads","1 km by 1 km detail"]),
        ("04_northwest.png","NORTH-WEST TERRAIN TILE",(-1000,0,0,1000),
         ["Lake and canal districts","1 km by 1 km detail"]),
        ("05_northeast.png","NORTH-EAST TERRAIN TILE",(0,0,1000,1000),
         ["Towns, northern roads and port","1 km by 1 km detail"]),
    ]
    generated=[snapshot(layout,*view) for view in views]
    report={"kind":"LAYOUT_SCHEMATIC_NOT_UNITY_RENDER","source":str(WORLD.relative_to(ROOT)),
            "source_sha256":hashlib.sha256(WORLD.read_bytes()).hexdigest(),
            "views":generated}
    (OUTPUT/"layout-preview-manifest.json").write_text(json.dumps(report,indent=2)+"\n")
    print("Generated layout-derived review files:")
    for g in generated:print(g["name"],g["size"],"bytes")
if __name__=="__main__":
    main()
