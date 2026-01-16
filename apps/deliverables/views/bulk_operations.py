import logging
from datetime import datetime

from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiTypes

from ..models import UploadedFile, SpecSection, SubmittalItem, NoticeMatch, NoticeExcerpt, SemanticallyProcessedSpecItem
from .main_views import (
    delete_submittals_for_document,
    is_notices_feature_flag_active,
    is_v2_process_deliverables_feature_flag_active,
    is_full_spec_processing_feature_flag_active,
    is_specgpt_feature_flag_active,
    call_extract_notices_lambda,
    call_full_spec_processing_lambda,
    parse_spec,
    s3
)


@extend_schema(
    parameters=[
        OpenApiParameter(
            name='document_ids',
            description='Comma-separated list of document IDs to reprocess',
            required=True,
            type=OpenApiTypes.STR
        )
    ],
    responses={
        200: OpenApiTypes.OBJECT,
        400: OpenApiTypes.OBJECT
    },
    description="Reprocess multiple documents."
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_reprocess_documents(request):
    try:
        document_ids_param = request.data.get('document_ids')
        if not document_ids_param:
            return Response({"error": "document_ids parameter is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Parse document IDs
        try:
            if isinstance(document_ids_param, str):
                document_ids = [int(id.strip()) for id in document_ids_param.split(',')]
            else:
                document_ids = document_ids_param
        except ValueError:
            return Response({"error": "Invalid document_ids format"}, status=status.HTTP_400_BAD_REQUEST)
        
        if not document_ids:
            return Response({"error": "No document IDs provided"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Get documents
        documents = UploadedFile.objects.filter(id__in=document_ids)
        
        if not documents.exists():
            return Response({"error": "No documents found"}, status=status.HTTP_404_NOT_FOUND)
        
        # Check permissions for all documents
        for document in documents:
            if not request.user.is_member_of_project(document.project):
                return Response({"error": f"User is not a member of project for document {document.id}"}, status=status.HTTP_403_FORBIDDEN)
        
        # Process each document
        processed_count = 0
        errors = []
        
        for document in documents:
            try:
                # Remove all existing submittals tied to this document before reprocessing
                delete_submittals_for_document(document.id)
                
                # Get feature flags for the project
                is_notices_flag_active = is_notices_feature_flag_active(request.user, document.project.team)
                is_v2_process_deliverables_flag_active = is_v2_process_deliverables_feature_flag_active(request.user, document.project.team, document.project)
                is_full_spec_processing_flag_active = is_full_spec_processing_feature_flag_active(request.user, document.project.team, document.project)
                is_specgpt_flag_active = is_specgpt_feature_flag_active(request.user, document.project.team, document.project)
                
                def _to_bool(val, default=False):
                    if val is None:
                        return default
                    if isinstance(val, bool):
                        return val
                    if isinstance(val, (int, float)):
                        return bool(val)
                    if isinstance(val, str):
                        return val.strip().lower() in ['1', 'true', 't', 'yes', 'y', 'on']
                    return default

                extract_notices = _to_bool(request.data.get('extract_notices'), False)
                full_spec_processing = _to_bool(request.data.get('full_spec_processing'), False)
                
                if is_notices_flag_active and extract_notices:
                    call_extract_notices_lambda(
                        callback_url=settings.BACKEND_NOTICES_CALLBACK_URL,
                        document_id=str(document.id),
                        object_key=document.document_path,
                        project_version_id=str(document.project_version.id),
                    )
                elif is_full_spec_processing_flag_active and full_spec_processing:
                    call_full_spec_processing_lambda(
                        callback_url=settings.BACKEND_FULL_SPEC_PROCESSING_CALLBACK_URL,
                        document_id=str(document.id),
                        project_id=str(document.project.id),
                        project_version_id=str(document.project_version.id),
                        object_key=document.document_path,
                        filename=document.name,
                        user_id=str(request.user.id),
                    )
                else:
                    parse_spec(
                        callback_url=settings.BACKEND_CALLBACK_URL,
                        document_id=str(document.id),
                        project_id=str(document.project.id),
                        project_version_id=str(document.project_version.id),
                        object_key=document.document_path,
                        filename=document.name,
                        user_id=str(request.user.id),
                        is_v2_process_deliverables_flag_active=is_v2_process_deliverables_flag_active,
                        is_specgpt_flag_active=is_specgpt_flag_active,
                        specgpt_callback_url=settings.BACKEND_SPECGPT_CALLBACK_URL
                    )
                
                document.processing_status = 'PENDING_PROCESSING'
                document.last_retry = datetime.now()
                document.save()
                
                processed_count += 1
                
            except Exception as e:
                errors.append(f"Document {document.id} ({document.name}): {str(e)}")
                logging.error(f"Error reprocessing document {document.name}: {e}")
                continue
        
        if processed_count == 0:
            return Response({
                "error": "No documents were successfully reprocessed",
                "errors": errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        response_data = {
            "message": f"Successfully started reprocessing {processed_count} document(s)",
            "processed_count": processed_count,
            "total_count": len(documents)
        }
        
        if errors:
            response_data["errors"] = errors
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@extend_schema(
    parameters=[
        OpenApiParameter(
            name='document_ids',
            description='Comma-separated list of document IDs to delete',
            required=True,
            type=OpenApiTypes.STR
        )
    ],
    responses={
        200: OpenApiTypes.OBJECT,
        400: OpenApiTypes.OBJECT
    },
    description="Delete multiple documents."
)
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_delete_documents(request):
    try:
        document_ids_param = request.data.get('document_ids')
        if not document_ids_param:
            return Response({"error": "document_ids parameter is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Parse document IDs
        try:
            if isinstance(document_ids_param, str):
                document_ids = [int(id.strip()) for id in document_ids_param.split(',')]
            else:
                document_ids = document_ids_param
        except ValueError:
            return Response({"error": "Invalid document_ids format"}, status=status.HTTP_400_BAD_REQUEST)
        
        if not document_ids:
            return Response({"error": "No document IDs provided"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Get documents
        documents = UploadedFile.objects.filter(id__in=document_ids)
        
        if not documents.exists():
            return Response({"error": "No documents found"}, status=status.HTTP_404_NOT_FOUND)
        
        # Check permissions for all documents
        for document in documents:
            if not request.user.is_member_of_project(document.project):
                return Response({"error": f"User is not a member of project for document {document.id}"}, status=status.HTTP_403_FORBIDDEN)
        
        # Delete each document
        deleted_count = 0
        errors = []
        
        for document in documents:
            try:
                # Get all spec sections related to this document for logging purposes
                spec_sections = SpecSection.objects.filter(document=document)

                # Cascade delete all related submittal items
                SubmittalItem.objects.filter(document=document).delete()

                # Set document field to null for all related notice matches instead of deleting them
                NoticeMatch.objects.filter(document=document).update(document=None)

                # Set spec_section to null for semantically processed items that reference spec sections from this document
                # Note: submittal items that reference these spec sections were already deleted above
                SemanticallyProcessedSpecItem.objects.filter(spec_section__in=spec_sections).update(spec_section=None)
                
                # Set document field to null for all related semantically processed spec items instead of deleting them
                SemanticallyProcessedSpecItem.objects.filter(document=document).update(document=None)
                
                # Delete notice excerpts since they are directly tied to documents
                NoticeExcerpt.objects.filter(document=document).delete()
                
                # Delete the document file from S3 if it exists
                if document.document_path:
                    try:
                        s3.delete_object(Bucket=settings.S3_BUCKET, Key=document.document_path)
                    except Exception as s3_error:
                        logging.warning(f"Failed to delete S3 object {document.document_path}: {s3_error}")
                
                # Delete the document record
                document.delete()
                deleted_count += 1
                
            except Exception as e:
                errors.append(f"Document {document.id} ({document.name}): {str(e)}")
                logging.error(f"Error deleting document {document.name}: {e}")
                continue
        
        if deleted_count == 0:
            return Response({
                "error": "No documents were successfully deleted",
                "errors": errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        response_data = {
            "message": f"Successfully deleted {deleted_count} document(s)",
            "deleted_count": deleted_count,
            "total_count": len(documents)
        }
        
        if errors:
            response_data["errors"] = errors
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

