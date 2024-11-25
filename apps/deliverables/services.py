import logging

from django.db import transaction, models

from .models import (
    Project,
    UploadedFile,
    DocProcessingStatus, SubmittalItem,
)
from ..utils.database import apply_advisory_lock_submittal_number_assignment


logger = logging.getLogger(__name__)


class SubmittalService:

    @classmethod
    def _get_pending_documents(cls, project: Project | int):
        if isinstance(project, Project):
            project = project.pk

        final_document_states = [
            DocProcessingStatus.PROCESSED,
            DocProcessingStatus.FAILED,
        ]

        pending_documents_qs = (
            UploadedFile.objects
            .filter(project=project)
            .exclude(processing_status__in=final_document_states)
        )

        return pending_documents_qs

    # region submittal number handling

    @classmethod
    def _actually_assign_submittal_numbers(
            cls,
            project: int,
            reassign: bool,
    ):
        targets_qs = (
            SubmittalItem.objects
            .filter(project=project)
            .order_by(
                'document__specsection__masterformat_section__masterformat_number',  # NOQA
                'heirarchical_paragraph_number',
            )
        )

        if not reassign:
            targets_qs = targets_qs.filter(submittal_number__isnull=True)

        target_count = targets_qs.count()

        if not target_count:
            logger.info(f'No submittal items to assign for project {project}')
            return

        to_assign = list(targets_qs)

        if reassign:
            # If we're reassigning, all the records will be assigned SNs from
            # the beginning
            current_max_number = 0
        else:
            current_max_number = (
                SubmittalItem.objects
                .filter(project=project)
                .aggregate(models.Max('submittal_number'))
            )['submittal_number__max']

            # If there are no submittal numbers assigned yet, MAX() function
            # will return None, so we're starting from the beginning
            if current_max_number is None:
                current_max_number = 0

        next_number = round(current_max_number, 0) + 1

        for entry in to_assign:
            entry.submittal_number = next_number
            next_number += 1

        SubmittalItem.objects.bulk_update(
            to_assign,
            fields=['submittal_number'],
        )
        logger.info(
            f'Assigned submittal numbers for project {project}, '
            f'count={target_count}'
        )

    @classmethod
    def assign_submittal_numbers(
            cls,
            project: Project | int,
            reassign: bool = False,
            only_if_all_documents_processed: bool = True,
    ) -> None:
        if isinstance(project, Project):
            project = project.pk

        if only_if_all_documents_processed:
            pending_documents_qs = cls._get_pending_documents(project)

            # If there are any documents that are not in a final state, we won't
            # be doing anything here, but it will be doable later when the last
            # one gets finalized and this gets called again
            pending_count = pending_documents_qs.count()
            if pending_count:
                logger.info(
                    f'Not assigning submittal number for project {project}, '
                    f'there are still {pending_count} documents being processed.'
                )
                return

        logging.debug(
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
            )

    # endregion submittal number handling
