"""Conservative orientation-candidate tests; no native assets modified."""
import sys
from pathlib import Path
import unittest
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "MapBuild"))
from lod_winding import candidate_winding, face_normal_counts


def triangle():
    vertices = np.zeros((3, 12), dtype=np.float32)
    vertices[:, :3] = [[0, 0, 0], [1, 0, 0], [0, 0, 1]]
    vertices[:, 3:6] = [0, 1, 0]
    return vertices


class WindingTests(unittest.TestCase):
    def test_opposing_face_is_only_reordered_not_removed(self):
        v = triangle()
        original = np.asarray([[0, 1, 2]], dtype=np.uint32)
        v_before, t_before = v.tobytes(), original.tobytes()
        candidate, r = candidate_winding(v, original)
        self.assertEqual(candidate.tolist(), [[0, 2, 1]])
        self.assertEqual(r["flipped"], 1)
        self.assertEqual((r["opposing_before"], r["opposing_after"]), (1, 0))
        self.assertEqual(v.tobytes(), v_before)
        self.assertEqual(original.tobytes(), t_before)
        self.assertEqual(np.sort(candidate[0]).tolist(), np.sort(original[0]).tolist())

    def test_already_agreeing_faces_are_preserved(self):
        v = triangle()
        original = np.asarray([[0, 2, 1]], dtype=np.uint32)
        candidate, r = candidate_winding(v, original)
        self.assertEqual(candidate.tolist(), original.tolist())
        self.assertEqual(r["flipped"], 0)
        self.assertEqual(r["opposing_after"], 0)

    def test_degenerate_face_is_not_made_up(self):
        v = triangle()
        original = np.asarray([[0, 0, 1]], dtype=np.uint32)
        candidate, r = candidate_winding(v, original)
        self.assertEqual(candidate.tolist(), original.tolist())
        self.assertEqual(r["flipped"], 0)
        self.assertEqual(r["unreliable_faces"], 1)

    def test_incompatible_shape_and_bad_indices_are_refused(self):
        v = triangle()
        with self.assertRaisesRegex(ValueError, "beyond vertex"):
            candidate_winding(v, [[0, 1, 999]])
        with self.assertRaisesRegex(ValueError, "Expected vertex"):
            candidate_winding(v, [[0, 1]])

    def test_perpendicular_face_not_guessed(self):
        v = triangle()
        v[:, 3:6] = [0, 0, 1]
        original = np.asarray([[0, 1, 2]], dtype=np.uint32)
        candidate, r = candidate_winding(v, original)
        self.assertEqual(candidate.tolist(), original.tolist())
        self.assertEqual(r["flipped"], 0)


if __name__ == "__main__":
    unittest.main()
