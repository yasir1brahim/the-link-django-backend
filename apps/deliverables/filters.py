import django_filters
from apps.deliverables.models import ExtractedData, ExtractionItemType, ExtractionSource


class ExtractedDataFilter(django_filters.FilterSet):
    """Advanced filtering for ExtractedData"""

    # Date range filters
    created_after = django_filters.DateTimeFilter(
        field_name='created_at',
        lookup_expr='gte'
    )
    created_before = django_filters.DateTimeFilter(
        field_name='created_at',
        lookup_expr='lte'
    )

    # Text filters
    spec_section_contains = django_filters.CharFilter(
        field_name='spec_section_number',
        lookup_expr='icontains'
    )
    requirement_contains = django_filters.CharFilter(
        field_name='requirement_text',
        lookup_expr='icontains'
    )

    # Source filter
    source = django_filters.ChoiceFilter(
        field_name='source',
        choices=ExtractionSource.choices
    )

    # Created by filter
    created_by = django_filters.NumberFilter(
        field_name='created_by__id'
    )

    class Meta:
        model = ExtractedData
        fields = [
            'source', 'extraction_type', 'item_type',
            'spec_section_number', 'ai_generated_log',
            'project_version', 'created_by', 'responsible_party'
        ]
