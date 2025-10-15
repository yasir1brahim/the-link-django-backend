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
        project_id = self.request.query_params.get("project")
        spec_section_id = self.request.query_params.get("spec_section")
        

        queryset = PDFAnnotation.objects.all()

        if project_id:
            queryset = queryset.filter(project_id=project_id)
        if spec_section_id:
            queryset = queryset.filter(spec_section_id=spec_section_id)
        if user:
            queryset = queryset.filter(user=user)

        return queryset.order_by("-created_at")

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
