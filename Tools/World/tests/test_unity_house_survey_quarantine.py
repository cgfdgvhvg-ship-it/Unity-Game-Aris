"""Protect all original Unity data when quarantining a crashing house photo helper."""
import importlib.util
from pathlib import Path
import unittest

SCRIPT=Path(__file__).resolve().parents[1]/"ai_codespace_executor.py"
spec=importlib.util.spec_from_file_location("ai_codespace_executor",SCRIPT)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SurveyRequestSafetyTests(unittest.TestCase):
    def test_verified_request(self):
        self.assertTrue(module._valid_house_survey_request(
            "unity-black-sky-houses-survey-20261106-g4.json",
            '{"id":"unity-black-sky-houses-survey-20261106-g4"}'))

    def test_id_mismatch_and_extra_operations_rejected(self):
        self.assertFalse(module._valid_house_survey_request(
            "foo-house-20261106.json", '{"id":"other-house-20261106"}'))
        self.assertFalse(module._valid_house_survey_request(
            "foo-house-20261106.json",
            '{"id":"foo-house-20261106","action":"exec"}'))

    def test_unsafe_names_and_contents_rejected(self):
        for name, data in [
            ("../../foo.json",'{"id":"foo"}'),
            ("photo.png",'{"id":"photo"}'),
            ("a.json",'{"id":"a"}'),
            ("foo-house-20261106.json",'not json'),
        ]:
            self.assertFalse(module._valid_house_survey_request(name,data))


if __name__ == "__main__":
    unittest.main()
