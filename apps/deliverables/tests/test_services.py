from unittest import TestCase

from apps.deliverables.services import VersionComparisonService, generate_text_diff
from apps.deliverables.models import Project, ProjectVersion, SubmittalItem, MasterFormatSection
from apps.deliverables.types import SubmittalItemDifference, TextDiff, DifferenceSummary

class VersionComparisonServiceTests(TestCase):
    def setUp(self):
        self.project = Project(name="Test Project")
        self.project_version_1 = ProjectVersion(
            project=self.project,
            version_number=1,
            version_name="Test Version 1"
        )
        self.project_version_2 = ProjectVersion(
            project=self.project,
            version_number=2,
            version_name="Test Version 2"
        )

        self.master_format_section_1 = MasterFormatSection(masterformat_number="330001")
        self.master_format_section_2 = MasterFormatSection(masterformat_number="330002")

        self.submittal_item_1 = SubmittalItem(
            project_version=self.project_version_1,
            masterformat_section=self.master_format_section_1,
            paragraph_number="1.1.1",
            submittal_type = "Action/Information Submittals",
            submittal_description = "Administrative Requirements",
            submittal_content = "Test Content 1"
        )
        self.submittal_item_2 = SubmittalItem(
            project_version=self.project_version_2,
            masterformat_section=self.master_format_section_1,
            paragraph_number="1.1.2",
            submittal_type = "Action/Information Submittals",
            submittal_description = "Administrative Requirements",
            submittal_content = "Test Content 2"
        )

    def test_submittals_with_same_mf_number_and_description_are_equivalent(self):
        self.assertTrue(VersionComparisonService.are_submittals_equivalent(self.submittal_item_1, self.submittal_item_2))

    def test_submittals_with_same_mf_number_and_different_description_are_not_equivalent(self):
        self.submittal_item_2.submittal_description = "Different Description"
        self.assertFalse(VersionComparisonService.are_submittals_equivalent(self.submittal_item_1, self.submittal_item_2))

    def test_submittals_with_other_submittal_description_can_be_equivalent(self):
        pass

    def test_compare_versions_detects_additions_and_deletions(self):
        self.submittal_item_2.submittal_description = "Different Description"
        response = VersionComparisonService._compare_submittal_sets([self.submittal_item_1], [self.submittal_item_2])

        expected_response = DifferenceSummary(
            additions=[self.submittal_item_2],
            deletions=[self.submittal_item_1],
            modifications=[],
            unchanged=[]
        )
        self.assertEqual(response, expected_response)

    

    def test_compare_versions_detects_unchanged_submittals(self):
        response = VersionComparisonService._compare_submittal_sets([self.submittal_item_1], [self.submittal_item_1])

        expected_response = DifferenceSummary(
            additions=[],
            deletions=[],
            modifications=[],
            unchanged=[self.submittal_item_1]
        )
        self.assertEqual(response, expected_response)

    def test_compare_versions_detects_modifications(self):
        response = VersionComparisonService._compare_submittal_sets([self.submittal_item_1], [self.submittal_item_2])

        expected_response = DifferenceSummary(
            additions=[],
            deletions=[],
            modifications=[
                SubmittalItemDifference(
                    old_submittal=self.submittal_item_1,
                    new_submittal=self.submittal_item_2,
                    content_differences=[
                        TextDiff(
                            type='equal',
                            value='Test Content'
                        ),
                        TextDiff(
                            type='delete',
                            value='1'
                        ),
                        TextDiff(
                            type='insert',
                            value='2'
                        )
                    ],
                    paragraph_number_differences=[
                        TextDiff(
                            type='equal',
                            value='1.1'
                        ),
                        TextDiff(
                            type='delete',
                            value='1'
                        ),
                        TextDiff(
                            type='insert',
                            value='2'
                        )
                    ]
                )
            ],
            unchanged=[]
        )
        self.assertEqual(response, expected_response)

    def test_more_complex_situation(self):
        submittal_item_3 = SubmittalItem(
            project_version=self.project_version_1,
            masterformat_section=self.master_format_section_1,
            paragraph_number="1.1.3",
            submittal_type = "Action/Information Submittals",
            submittal_description = "Different Description 2",
            submittal_content = "Test Content 3"
        )
        submittal_item_4 = SubmittalItem(
            project_version=self.project_version_1,
            masterformat_section=self.master_format_section_1,
            paragraph_number="1.1.4",
            submittal_type = "Action/Information Submittals",
            submittal_description = "Different Description 3",
            submittal_content = "Test Content 4"
        )
        response = VersionComparisonService._compare_submittal_sets([self.submittal_item_1, submittal_item_3], [self.submittal_item_2, submittal_item_4])

        expected_response = DifferenceSummary(
            additions=[submittal_item_4],
            deletions=[submittal_item_3],
            modifications=[
                SubmittalItemDifference(
                    old_submittal=self.submittal_item_1,
                    new_submittal=self.submittal_item_2,
                    content_differences=[
                        TextDiff(
                            type='equal',
                            value='Test Content'
                        ),
                        TextDiff(
                            type='delete',
                            value='1'
                        ),
                        TextDiff(
                            type='insert',
                            value='2'
                        )
                    ],
                    paragraph_number_differences=[
                        TextDiff(
                            type='equal',
                            value='1.1'
                        ),
                        TextDiff(
                            type='delete',
                            value='1'
                        ),
                        TextDiff(
                            type='insert',
                            value='2'
                        )
                    ]
                )
            ],
            unchanged=[]
        )
        self.assertEqual(response, expected_response)

    def test_handling_when_multiple_submittals_are_equivalent(self):
        pass


    def test_compare_equivalent_submittals(self):
        response = VersionComparisonService.compare_equivalent_submittals(self.submittal_item_1, self.submittal_item_2)

        expected_response = SubmittalItemDifference(
            old_submittal=self.submittal_item_1,
            new_submittal=self.submittal_item_2,
            content_differences=[
                TextDiff(
                    type='equal',
                    value='Test Content'
                ),
                TextDiff(
                    type='delete',
                    value='1'
                ),
                TextDiff(
                    type='insert',
                    value='2'
                )
            ],
            paragraph_number_differences=[
                TextDiff(
                    type='equal',
                    value='1.1'
                ),
                TextDiff(
                    type='delete',
                    value='1'
                ),
                TextDiff(
                    type='insert',
                    value='2'
                )
            ]
        )
        self.assertEqual(response, expected_response)

    def test_compare_equivalent_submittals_with_identical_submittals_returns_no_differences(self):
        response = VersionComparisonService.compare_equivalent_submittals(self.submittal_item_1, self.submittal_item_1)

        expected_response = SubmittalItemDifference(
            old_submittal=self.submittal_item_1,
            new_submittal=self.submittal_item_1,
            content_differences=[],
            paragraph_number_differences=[]
        )
        self.assertEqual(response, expected_response)


class TextDiffTests(TestCase):
    def test_generate_word_diff_with_no_changes(self):
        text = "The quick brown fox"
        diffs = generate_text_diff(text.split(), text.split())
        
        assert len(diffs) == 1
        assert diffs[0] == {
            'type': 'equal',
            'value': text
        }

    def test_generate_word_diff_with_deletion(self):
        old_text = "The quick brown fox"
        new_text = "The quick fox"
        diffs = generate_text_diff(old_text.split(), new_text.split())
        
        assert len(diffs) == 3
        assert diffs == [
            {
                'type': 'equal',
                'value': 'The quick'
            },
            {
                'type': 'delete',
                'value': 'brown'
            },
            {
                'type': 'equal',
                'value': 'fox'
            }
        ]

    def test_generate_word_diff_with_insertion(self):
        old_text = "The quick fox"
        new_text = "The quick brown fox"
        diffs = generate_text_diff(old_text.split(), new_text.split())
        
        assert len(diffs) == 3
        assert diffs == [
            {
                'type': 'equal',
                'value': 'The quick'
            },
            {
                'type': 'insert',
                'value': 'brown'
            },
            {
                'type': 'equal',
                'value': 'fox'
            }
        ]

    def test_generate_word_diff_with_replacement(self):
        old_text = "The quick brown fox"
        new_text = "The quick red fox"
        diffs = generate_text_diff(old_text.split(), new_text.split())
        
        assert len(diffs) == 4
        assert diffs == [
            {
                'type': 'equal',
                'value': 'The quick'
            },
            {
                'type': 'delete',
                'value': 'brown'
            },
            {
                'type': 'insert',
                'value': 'red'
            },
            {
                'type': 'equal',
                'value': 'fox'
            }
        ]

    def test_generate_word_diff_with_empty_strings(self):
        diffs = generate_text_diff("".split(), "".split())
        assert len(diffs) == 0

    def test_generate_word_diff_with_completely_different_texts(self):
        old_text = "The quick brown fox"
        new_text = "jumps over the lazy dog"
        diffs = generate_text_diff(old_text.split(), new_text.split())
        
        assert len(diffs) == 2
        assert diffs == [
            {
                'type': 'delete',
                'value': 'The quick brown fox'
            },
            {
                'type': 'insert',
                'value': 'jumps over the lazy dog'
            }
        ]
    
    def test_generate_text_diff_with_extra_whitespace(self):
        old_text = "The quick brown fox"
        new_text = "The  \nbrown fox"
        diffs = generate_text_diff(old_text.split(), new_text.split())
        
        assert len(diffs) == 3
        assert diffs == [
            {
                'type': 'equal',
                'value': 'The'
            },
            {
                'type': 'delete',
                'value': 'quick'
            },
            {
                'type': 'equal',
                'value': 'brown fox'
            }
        ]

    def test_generate_text_diff_with_hierarchical_chunks(self):
        old_text = "1.1.1"
        new_text = "1.1.2"
        diffs = generate_text_diff(old_text.split('.'), new_text.split('.'), rejoin_with='.')
        
        assert len(diffs) == 3
        assert diffs == [
            {
                'type': 'equal',
                'value': '1.1'
            },
            {
                'type': 'delete',
                'value': '1'
            },
            {
                'type': 'insert',
                'value': '2'
            }
        ]