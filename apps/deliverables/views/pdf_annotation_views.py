# apps/specs/views.py
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from apps.deliverables.models import PDFAnnotation
from apps.deliverables.serializers.pdf_annotation_serializer import PDFAnnotationSerializer

class PDFAnnotationViewSet(viewsets.ModelViewSet):
    serializer_class = PDFAnnotationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        project_id = self.kwargs.get("project_id")
        project_version_id = self.request.query_params.get("project_version")
        spec_section_id = self.request.query_params.get("spec_section")
        

        queryset = PDFAnnotation.objects.all()

        if project_version_id:
            queryset =  queryset.filter(project_version_id=project_version_id)
        if project_id:
            queryset = queryset.filter(project_id=project_id)
        if spec_section_id:
            queryset = queryset.filter(spec_section_id=spec_section_id)
        if self.action != "destroy":
            queryset = queryset.filter(user=user)

        return queryset.order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    def destroy(self, request, *args, **kwargs):
        """Override destroy to verify the annotation exists and belongs to the user"""
        try:
            annotation = self.get_object()  # Retrieves the annotation by URL pk
        except PDFAnnotation.DoesNotExist:
            return Response(
                {"detail": "Annotation not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        
        # Optional: verify ownership or other conditions
        if annotation.user != request.user:
            return Response(
                {"detail": "You do not have permission to delete this annotation."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # If verification passes, proceed with deletion
        self.perform_destroy(annotation)
        return Response(status=status.HTTP_204_NO_CONTENT)
