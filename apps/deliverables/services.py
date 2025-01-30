import logging

from django.db import transaction, models

from .models import (
    Project,
    UploadedFile,
    DocProcessingStatus, SubmittalItem, SpecSection,
    ProjectVersion
)
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
