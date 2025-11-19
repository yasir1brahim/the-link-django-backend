# apps/deliverables/tests/test_extraction_note_admin.py
from django.test import TestCase
from django.contrib.admin.sites import site
from apps.deliverables.models import ExtractionNote
from apps.deliverables.admin import ExtractionNoteAdmin


class TestExtractionNoteAdmin(TestCase):
    def test_admin_registered(self):
        """Test ExtractionNote is registered in admin"""
        self.assertIn(ExtractionNote, site._registry)
        self.assertIsInstance(site._registry[ExtractionNote], ExtractionNoteAdmin)

    def test_admin_list_display(self):
        """Test admin list display fields"""
        admin = ExtractionNoteAdmin(ExtractionNote, site)
        expected = ['id', 'extracted_data', 'text_preview', 'created_by', 'created_at']
        self.assertEqual(list(admin.list_display), expected)

    def test_admin_list_filter(self):
        """Test admin filter options"""
        admin = ExtractionNoteAdmin(ExtractionNote, site)
        self.assertIn('created_at', admin.list_filter)

    def test_admin_search_fields(self):
        """Test admin search fields"""
        admin = ExtractionNoteAdmin(ExtractionNote, site)
        self.assertIn('text', admin.search_fields)
        self.assertIn('created_by__email', admin.search_fields)
        self.assertIn('extracted_data__spec_section_number', admin.search_fields)
