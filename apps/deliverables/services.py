import logging
from difflib import SequenceMatcher

from django.db import transaction, models

from .models import (
    Project,
    UploadedFile,
    DocProcessingStatus, SubmittalItem, SpecSection,
    ProjectVersion
)
from .types import SubmittalItemDifference, DifferenceSummary, TextDiff, List
from ..utils.database import apply_advisory_lock_submittal_number_assignment


logger = logging.getLogger(__name__)

class SubmittalService:

    @classmethod
    def _get_pending_documents(cls, project: Project | int, project_version_id: int):
        if isinstance(project, Project):
            project = project.pk

        final_document_states = [
            DocProcessingStatus.PROCESSED,
        ]

        pending_documents_qs = (
            UploadedFile.objects
            .filter(project=project, project_version=project_version_id)
            .exclude(processing_status__in=final_document_states)
        )

        return pending_documents_qs

    # region submittal number handling

    @classmethod
    def _actually_assign_submittal_numbers(
            cls,
            project: int,
            reassign: bool,
            project_version_id: int,
    ):
        targets_qs = (
            SubmittalItem.objects
            .filter(project=project, project_version=project_version_id)
            .exclude(spec_section__processing_method=SpecSection.ProcessingMethod.REGEX_UNABLE_TO_DETECT)
            .order_by(
                'masterformat_section__masterformat_number', 
                'heirarchical_paragraph_number',
            )
        )

        if not reassign:
            targets_qs = targets_qs.filter(submittal_number__isnull=True)

        target_count = targets_qs.count()

        if not target_count:
            print(f'No submittal items to assign for project {project}')
            return

        to_assign = list(targets_qs)

        if reassign:
            # If we're reassigning, all the records will be assigned SNs from
            # the beginning
            current_max_number = 0
        else:
            current_max_number = (
                SubmittalItem.objects
                .filter(project=project, project_version=project_version_id)
                .aggregate(models.Max('submittal_number'))
            )['submittal_number__max']

            # If there are no submittal numbers assigned yet, MAX() function
            # will return None, so we're starting from the beginning
            if current_max_number is None:
                current_max_number = 0

        next_number = round(current_max_number, 0) + 1

        print("submittals in order:", targets_qs.values_list('masterformat_section__masterformat_number', 'paragraph_number', 'submittal_type'))

        for entry in to_assign:
            entry.submittal_number = next_number
            next_number += 1

        SubmittalItem.objects.bulk_update(
            to_assign,
            fields=['submittal_number'],
        )
        print(
            f'Assigned submittal numbers for project {project}, '
            f'count={target_count}'
        )

    @classmethod
    def assign_submittal_numbers(
            cls,
            project: Project | int,
            project_version_id: int,
            reassign: bool = False,
            only_if_all_documents_processed: bool = True,
    ) -> None:
        if isinstance(project, Project):
            project = project.pk

        if only_if_all_documents_processed:
            pending_documents_qs = cls._get_pending_documents(project, project_version_id)

            # If there are any documents that are not in a final state, we won't
            # be doing anything here, but it will be doable later when the last
            # one gets finalized and this gets called again
            pending_count = pending_documents_qs.count()
            if pending_count:
                print(
                    f'Not assigning submittal number for project {project}, '
                    f'there are still {pending_count} documents being processed.'
                )
                return

        print(
            f'Assigning submittal numbers for project {project}, '
            f'reassign={reassign}',
        )

        # Apply advisory lock right away, on project level, to prevent any
        # race conditions in case of multiple documents being processed at the
        # same time
        with (
            transaction.atomic(),
            apply_advisory_lock_submittal_number_assignment(project),
        ):
            cls._actually_assign_submittal_numbers(
                project=project,
                reassign=reassign,
                project_version_id=project_version_id,
            )

    # endregion submittal number handling


def generate_text_diff(old_semantic_chunks: List[str], new_semantic_chunks: List[str], rejoin_with: str = ' ') -> List[TextDiff]:
    """
    Generate a semantic-chunk-level diff between two strings.
    E.g. For normal text, this will be a word-level diff.
    E.g. For submittal numbers, this could be a number-level diff.
    
    Args:
        old_text: The original text
        new_text: The modified text
        
    Returns:
        List of diffs where each diff is a dict with:
        - type: 'equal', 'delete', or 'insert'
        - value: The text content
    """
    

    matcher = SequenceMatcher(None, old_semantic_chunks, new_semantic_chunks)
    diffs: List[TextDiff] = []
    
    for op, start_index_old_string, end_index_old_string, start_index_new_string, end_index_new_string in matcher.get_opcodes():
        if op == 'equal':
            diffs.append({
                'type': 'equal',
                'value': rejoin_with.join(old_semantic_chunks[start_index_old_string:end_index_old_string])
            })
        elif op == 'delete':
            diffs.append({
                'type': 'delete',
                'value': rejoin_with.join(old_semantic_chunks[start_index_old_string:end_index_old_string])
            })
        elif op == 'insert':
            diffs.append({
                'type': 'insert',
                'value': rejoin_with.join(new_semantic_chunks[start_index_new_string:end_index_new_string])
            })
        elif op == 'replace':
            diffs.append({
                'type': 'delete',
                'value': rejoin_with.join(old_semantic_chunks[start_index_old_string:end_index_old_string])
            })
            diffs.append({
                'type': 'insert',
                'value': rejoin_with.join(new_semantic_chunks[start_index_new_string:end_index_new_string])
            })
            
    return diffs


class VersionComparisonService:

    @classmethod
    def compare_versions(
        cls,
        older_version_id: int,
        newer_version_id: int,
        master_format_number: str,
    ) -> DifferenceSummary:
        older_submittal_items = cls.get_submittal_items_for_version(older_version_id, master_format_number)
        newer_submittal_items = cls.get_submittal_items_for_version(newer_version_id, master_format_number)

        return cls._compare_submittal_sets(older_submittal_items, newer_submittal_items)
    
    @classmethod
    def _texts_are_equal(cls, text_differences: List[TextDiff]) -> bool:
        return len(text_differences) == 1 and text_differences[0]['type'] == 'equal'
    
    @classmethod
    def get_similarity_score(cls, older_submittal_item: SubmittalItem, newer_submittal_item: SubmittalItem) -> float:
        content_similarity_score = SequenceMatcher(None, older_submittal_item.submittal_content, newer_submittal_item.submittal_content).ratio()
        paragraph_number_similarity_score = SequenceMatcher(None, older_submittal_item.paragraph_number, newer_submittal_item.paragraph_number).ratio()
        return (content_similarity_score * 0.9 + paragraph_number_similarity_score * 0.1)
    
    @classmethod
    def get_best_match(cls, older_submittal_item: SubmittalItem, equivalent_submittals: List[SubmittalItem]) -> SubmittalItem:
        best_match = None
        best_similarity_score = 0
        for submittal in equivalent_submittals:
            similarity_score = cls.get_similarity_score(older_submittal_item, submittal)
            if similarity_score > best_similarity_score:
                best_similarity_score = similarity_score
                best_match = submittal
        print(f"Best match for {older_submittal_item} is {best_match} with a similarity score of {best_similarity_score}")
        return best_match
    
    @classmethod
    def _compare_submittal_sets(cls, older_submittal_items: List[SubmittalItem], newer_submittal_items: List[SubmittalItem]):
        # Track which items have been matched to avoid double-counting
        matched_newer_items = set()
        differences = []
        deleted_items = []
        added_items = []
        unchanged_items = []
        # Find modified and deleted items
        for older_submittal_item in older_submittal_items:
            print(f"Comparing {older_submittal_item} to {newer_submittal_items}")
            print("matched_newer_items", matched_newer_items)
            equivalent_submittals = []
            for i, newer_submittal_item in enumerate(newer_submittal_items):
                if newer_submittal_item.id in matched_newer_items:
                    continue
                
                if cls.are_submittals_equivalent(older_submittal_item, newer_submittal_item):
                    equivalent_submittals.append(newer_submittal_item)
            
            if equivalent_submittals:
                if len(equivalent_submittals) == 1:
                    best_match = equivalent_submittals[0]
                else:
                    best_match = cls.get_best_match(older_submittal_item, equivalent_submittals)
                difference = cls.compare_equivalent_submittals(older_submittal_item, best_match)
                if cls._texts_are_equal(difference['content_differences']) and cls._texts_are_equal(difference['paragraph_number_differences']):
                    unchanged_items.append(best_match)
                else:
                    differences.append(difference)
                print("best_match", best_match)
                print("best_match id", best_match.pk)
                matched_newer_items.add(best_match.id)
            
            else:
                deleted_items.append(older_submittal_item)

        # Find added items (any unmatched items in newer version)
        for i, newer_submittal_item in enumerate(newer_submittal_items):
            if newer_submittal_item.id not in matched_newer_items:
                added_items.append(newer_submittal_item)

        return DifferenceSummary(
            modifications=differences,
            deletions=deleted_items,
            additions=added_items,
            unchanged=unchanged_items
        )

    @classmethod
    def get_submittal_items_for_version(cls, project_version_id: int, master_format_number: str):
        return SubmittalItem.objects.filter(project_version=project_version_id, masterformat_section__masterformat_number=master_format_number)

    @classmethod
    def are_submittals_equivalent(cls, submittal_1: SubmittalItem, submittal_2: SubmittalItem):
        """
        Determine if two submittals are equivalent using business logic of submittals and specs.
        Both submittals are assumed to be from the same master format section
        """
        return (
            submittal_1.masterformat_section.masterformat_number == submittal_2.masterformat_section.masterformat_number
            and submittal_1.submittal_description == submittal_2.submittal_description
        )

    @classmethod
    def compare_equivalent_submittals(cls, old_submittal: SubmittalItem, new_submittal: SubmittalItem) -> SubmittalItemDifference:
        """
        Compare the content of two submittals that are deemed equivalent by the
        .are_submittals_equivalent() method.
        """
        def split_into_words(text: str) -> List[str]:
            return text.split()
        
        def split_into_hierarchical_chunks(text: str) -> List[str]:
            return text.split('.')
    
        old_submittal_content = split_into_words(old_submittal.submittal_content)
        new_submittal_content = split_into_words(new_submittal.submittal_content)

        old_submittal_paragraph_number = split_into_hierarchical_chunks(old_submittal.paragraph_number)
        new_submittal_paragraph_number = split_into_hierarchical_chunks(new_submittal.paragraph_number)

        content_diffs = generate_text_diff(old_submittal_content, new_submittal_content)
        paragraph_number_diffs = generate_text_diff(old_submittal_paragraph_number, new_submittal_paragraph_number, rejoin_with='.')

        return SubmittalItemDifference(
            old_submittal=old_submittal,
            new_submittal=new_submittal,
            content_differences=content_diffs,
            paragraph_number_differences=paragraph_number_diffs
        )
