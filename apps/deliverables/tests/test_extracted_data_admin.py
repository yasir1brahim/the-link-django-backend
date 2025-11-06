from django.test import TestCase
from django.contrib.admin.sites import site
from apps.deliverables.models import ExtractedData
from apps.deliverables.admin import ExtractedDataAdmin

class TestExtractedDataAdmin(TestCase):
    def test_admin_registered(self):
        """Test ExtractedData is registered in admin"""
        self.assertIn(ExtractedData, site._registry)

    def test_admin_list_display(self):
        """Test admin list display fields"""
        admin = ExtractedDataAdmin(ExtractedData, site)
        expected = [
            'id', 'spec_section_number', 'spec_section_name',
            'extraction_type', 'source', 'created_by', 'created_at'
        ]
        self.assertEqual(list(admin.list_display), expected)

    def test_admin_list_filter(self):
        """Test admin filter options"""
        admin = ExtractedDataAdmin(ExtractedData, site)
        expected = [
            'source', 'extraction_type', 'item_type', 'project'
        ]
        self.assertEqual(list(admin.list_filter), expected)
