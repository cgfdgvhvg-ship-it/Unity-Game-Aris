#!/usr/bin/env python3
"""Parse a strictly bounded owner-only CS PHOTO command into safe decimal args.

Examples:
  CS PHOTO -420 -210
  CS PHOTO 350 220 90 35 85

X and Z are map coordinates in metres, yaw azimuth in degrees,
pitch is degrees above the ground, distance is metres.
The ground Y is read from Unity TerrainData; no fake image or guessed height.
"""
import re
import sys

NUMBER = re.compile(r"-?(?:0|[1-9][0-9]{0,3})(?:\.[0-9]{1,3})?\Z", re.ASCII)

def parse(command):
    values=command.split()
    if len(values) not in (4, 7) or values[:2] != ["CS", "PHOTO"]:
        raise ValueError("PHOTO_EXPECTED_X_Z_OR_X_Z_YAW_PITCH_DISTANCE")
    raw=values[2:]
    if any(not NUMBER.fullmatch(v) for v in raw):
        raise ValueError("PHOTO_INVALID_DECIMAL")
    parsed=[float(v) for v in raw]
    if len(parsed)==2:
        parsed += [35.0, 30.0, 85.0]
    x,z,yaw,pitch,distance=parsed
    if not (-1000<=x<=1000 and -1000<=z<=1000):
        raise ValueError("PHOTO_OUTSIDE_MAP")
    if not (-360<=yaw<=360 and 12<=pitch<=75 and 20<=distance<=450):
        raise ValueError("PHOTO_CAMERA_OUT_OF_BOUNDS")
    return " ".join("%.3f" % x for x in parsed)

def selftest():
    assert parse("CS PHOTO -420 -210") == "-420.000 -210.000 35.000 30.000 85.000"
    assert parse("CS PHOTO 350 220 90 35 85") == "350.000 220.000 90.000 35.000 85.000"
    assert parse("CS PHOTO -1000.0 1000.0 -360 75 450").split()[0] == "-1000.000"
    for cmd in (
        "CS PHOTO 1001 30",
        "CS PHOTO 4 5 35 80 60",
        "CS PHOTO 4 5 nan 30 60",
        "CS PHOTO 3 4 5 6 7;echo owned",
        "CS PHOTO ../../abc 25",
        "CS PHOTO 3 4 $(id)",
        "CS PHOTO 3 4\nCS STOP",
        "CS PHOTO 3",
        "CS PHOTO 3 4 5",
        "CS PHOTO 3 4 5 6",
        "CS PHOTO 3 4 5 6 7 8",
        "CS PHOTO 4 5 90 25 0",
        "CS PHOTO 4 5 90 25 600",
    ):
        try:
            parse(cmd)
        except ValueError:
            continue
        raise AssertionError(cmd)
    print("AARIS_PHOTO_REQUEST_PARSER_PASS")

if __name__=="__main__":
    if len(sys.argv)==2 and sys.argv[1]=="--selftest":
        selftest()
    elif len(sys.argv)==2:
        try:
            print(parse(sys.argv[1]))
        except ValueError as exc:
            # Closed vocabulary; never print the input or GitHub credentials.
            print("AARIS_PHOTO_REJECTED:"+str(exc), file=sys.stderr)
            raise SystemExit(2)
    else:
        raise SystemExit(2)
