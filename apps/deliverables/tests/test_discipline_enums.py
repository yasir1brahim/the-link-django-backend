# apps/deliverables/tests/test_discipline_enums.py
from django.test import TestCase
from apps.deliverables.models import Discipline, DisciplineConfidence


class TestDisciplineEnum(TestCase):
    def test_discipline_enum_has_all_ncs_codes(self):
        """Test Discipline enum contains all 21 NCS discipline codes"""
        expected_values = {
            "general", "hazardous_materials", "survey_mapping", "geotechnical",
            "civil", "landscape", "structural", "architectural", "interiors",
            "equipment", "fire_protection", "plumbing", "process", "mechanical",
            "electrical", "distributed_energy", "telecommunications", "resource",
            "other", "contractor_shop", "operations"
        }
        actual_values = {choice.value for choice in Discipline}
        self.assertEqual(actual_values, expected_values)

    def test_discipline_confidence_enum_has_levels(self):
        """Test DisciplineConfidence enum has high/medium/low"""
        expected_values = {"high", "medium", "low"}
        actual_values = {choice.value for choice in DisciplineConfidence}
        self.assertEqual(actual_values, expected_values)
