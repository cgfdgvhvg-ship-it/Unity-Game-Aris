"""Compatibility command: author a saved grounded player, never a flying camera."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'MapBuild'))
from ground_review import upgrade
from ground_native import materialize
if __name__=='__main__':
    upgrade(Path.cwd())
    materialize(Path.cwd())
