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

    def update(self, request, *args, **kwargs):
        """
        Update an existing PDF annotation
        """
        try:
            # Get the annotation using annotation_id from URL
            annotation_id = self.kwargs.get("pk")
            annotation = PDFAnnotation.objects.filter(annotation_id=annotation_id).first()
            
            if not annotation:
                return Response(
                    {"detail": "Annotation not found."}, 
                    status=status.HTTP_404_NOT_FOUND
                )

            # Check permission - user can only update their own annotations
            if annotation.user != request.user:
                return Response(
                    {"detail": "You do not have permission to update this annotation."},
                    status=status.HTTP_403_FORBIDDEN,
                )

            # Partial update allowed (PATCH method)
            partial = kwargs.pop('partial', False)
            serializer = self.get_serializer(annotation, data=request.data, partial=partial)
            serializer.is_valid(raise_exception=True)
            serializer.save()

            return Response(serializer.data)

        except Exception as e:
            return Response(
                {"detail": f"Error updating annotation: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

    def partial_update(self, request, *args, **kwargs):
        """
        Handle PATCH requests for partial updates
        """
        kwargs['partial'] = True
        return self.update(request, *args, **kwargs)


    def destroy(self, request, *args, **kwargs):
        annotation_id = self.kwargs.get("pk")  # This will still capture the value from the URL

        annotation = PDFAnnotation.objects.filter(annotation_id=annotation_id).first()
        if not annotation:
            return Response({"detail": "Annotation not found."}, status=status.HTTP_404_NOT_FOUND)

        if annotation.user != request.user:
            return Response(
                {"detail": "You do not have permission to delete this annotation."},
                status=status.HTTP_403_FORBIDDEN,
            )

        print("Deleting Annotation: ",annotation)
        annotation.delete()
        print("Total Annotations: ", PDFAnnotation.objects.all())
        return Response(status=status.HTTP_204_NO_CONTENT)

