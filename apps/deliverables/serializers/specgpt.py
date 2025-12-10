from collections.abc import Mapping
import logging

from rest_framework import serializers
from django.db.models import Q
from apps.deliverables.models import (
    Chat,
    ChatMessage,
    AiGeneratedLog,
    ExtractedData,
    ExtractionSource,
)
from apps.utils.feature_flags import is_inspection_log_use_data_tables_feature_flag_active

logger = logging.getLogger(__name__)


class ChatMessageSerializer(serializers.ModelSerializer):
    sources = serializers.JSONField()

    class Meta:
        model = ChatMessage
        fields = ['id', 'message', 'created_at', 'type', 'sources']


class ChatDetailSerializer(serializers.ModelSerializer):
    messages = serializers.SerializerMethodField()

    class Meta:
        model = Chat
        fields = ['id', 'project', 'project_version', 'user', 'created_at', 'messages']

    def get_messages(self, obj):
        messages = obj.messages.all().order_by('created_at')
        return ChatMessageSerializer(messages, many=True).data


class AiGeneratedLogSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)
    project_version_number = serializers.CharField(source='project_version.version_number', read_only=True)
    log_data = serializers.JSONField(required=False, allow_null=True)
    data_format = serializers.SerializerMethodField()
    
    class Meta:
        model = AiGeneratedLog
        fields = [
            'id', 'project', 'project_version', 'log_type', 'log_status', 
            'log_table', 'log_data', 'data_format', 'created_at', 'project_name', 'project_version_number'
        ]
        read_only_fields = ['id', 'created_at', 'project_name', 'project_version_number', 'data_format']
    
    def _coerce_query_params(self, request):
        query_params = getattr(request, 'query_params', None)
        if isinstance(query_params, Mapping):
            return query_params
        return {}

    def build_structured_rows(self, instance):
        """Return structured rows for the given log using ExtractedData when available."""
        extracted_items = list(instance.extracted_items.all()) if hasattr(instance, 'extracted_items') else []

        # Always include human-created highlights that match the same context
        human_items_qs = ExtractedData.objects.filter(
            ai_generated_log__isnull=True,
            project=instance.project,
            project_version=instance.project_version,
            extraction_type=instance.log_type,
            source=ExtractionSource.HUMAN,
        ).select_related('created_by', 'spec_section__masterformat_section')

        human_items = list(human_items_qs)

        if extracted_items or human_items:
            # Merge and remove duplicates while preserving consistent ordering
            combined_items = []
            seen_ids = set()

            for item in extracted_items + human_items:
                if item.id in seen_ids:
                    continue
                seen_ids.add(item.id)
                combined_items.append(item)

            list_to_return = [self._format_extracted_item(item) for item in combined_items]
            return list_to_return

        original_data = instance.log_data
        if isinstance(original_data, list):
            return [dict(row) for row in original_data]

        return original_data

    def query_extracted_data_with_filters(self, instance, filter_params=None, search_term=None, sort_field='spec_section_number', sort_direction='asc', page=1, page_size=50):
        """
        Query ExtractedData at DB level with filtering, searching, sorting, and pagination.
        This replaces the Python-level data processing for better performance.

        Args:
            instance: AiGeneratedLog instance
            filter_params: Dict of column names to lists of filter values
            search_term: String to search across text fields
            sort_field: Field name to sort by
            sort_direction: 'asc' or 'desc'
            page: Page number (1-indexed)
            page_size: Number of items per page

        Returns:
            Dict with 'data' (list of formatted items) and 'pagination' (metadata)
        """
        logger.info(f"Starting DB-level query for log {instance.id} (type: {instance.log_type})")
        logger.debug(f"Filter params: {filter_params}, Search: {search_term}, Sort: {sort_field} {sort_direction}")

        # Combine AI-generated items for this log with human-created highlights
        # Using Q objects with | operator instead of union() to avoid intermediate query evaluation
        queryset = ExtractedData.objects.filter(
            Q(ai_generated_log=instance) |
            Q(
                ai_generated_log__isnull=True,
                project=instance.project,
                project_version=instance.project_version,
                extraction_type=instance.log_type,
                source=ExtractionSource.HUMAN,
            )
        ).select_related('created_by', 'spec_section__masterformat_section')

        logger.debug(f"Base queryset count (before filters): {queryset.count()}")

        # Apply filters
        if filter_params:
            filter_q = Q()
            for column_key, values in filter_params.items():
                if not values:
                    continue

                # Map UI column names to database field names
                if column_key == 'Spec Section #':
                    # OR logic within the same column
                    column_q = Q(spec_section_number__in=values)
                elif column_key == 'item_type':
                    column_q = Q(item_type__in=values)
                elif column_key == 'Responsible Party':
                    column_q = Q(responsible_party__in=values)
                elif column_key == 'Deliverable Type':
                    # For owner_deliverables_log
                    column_q = Q(metadata__deliverable_type__in=values)
                else:
                    # Skip unknown columns
                    logger.warning(f"Unknown filter column: {column_key}")
                    continue

                # AND logic across different columns
                filter_q &= column_q

            if filter_q:
                queryset = queryset.filter(filter_q)
                logger.debug(f"Queryset count after filtering: {queryset.count()}")

        # Apply search
        if search_term:
            search_q = Q(
                Q(spec_section_number__icontains=search_term) |
                Q(spec_section_name__icontains=search_term) |
                Q(requirement_text__icontains=search_term) |
                Q(responsible_party__icontains=search_term) |
                Q(paragraph_number__icontains=search_term) |
                Q(item_type__icontains=search_term)
            )
            queryset = queryset.filter(search_q)
            logger.debug(f"Queryset count after search: {queryset.count()}")

        # Apply sorting
        # Map UI sort field names to database field names
        sort_field_mapping = {
            'spec_section_number': 'spec_section_number',
            'spec_section_name': 'spec_section_name',
            'paragraph_number': 'paragraph_number',
            'item_type': 'item_type',
            'requirement_text': 'requirement_text',
            'responsible_party': 'responsible_party',
            'when_due': 'metadata__when_due',
            'created_at': 'created_at',
            'inspection_type_and_requirements': 'requirement_text',
            'inspection_frequency': 'metadata__inspection_frequency',
            'deliverable_type': 'metadata__deliverable_type',
        }

        db_sort_field = sort_field_mapping.get(sort_field, 'spec_section_number')
        sort_prefix = '-' if sort_direction == 'desc' else ''

        # Handle None values in sorting by using multiple order_by clauses
        # Always add 'id' as final sort to ensure consistent ordering
        queryset = queryset.order_by(f'{sort_prefix}{db_sort_field}', 'id')
        logger.debug(f"Sorting by: {sort_prefix}{db_sort_field}")

        # Get total count before pagination
        total_items = queryset.count()
        logger.info(f"Total items after all filters: {total_items}")

        # Apply pagination
        page = max(1, page)
        page_size = max(1, min(page_size, 100))  # Limit page size to 100

        start_index = (page - 1) * page_size
        end_index = start_index + page_size

        # Get paginated items
        paginated_items = queryset[start_index:end_index]
        logger.debug(f"Fetching items {start_index} to {end_index}")

        # Format items using existing format method
        formatted_data = [self._format_extracted_item(item) for item in paginated_items]

        # Calculate pagination metadata
        total_pages = (total_items + page_size - 1) // page_size
        has_next = page < total_pages
        has_previous = page > 1

        pagination_info = {
            'current_page': page,
            'page_size': page_size,
            'total_items': total_items,
            'total_pages': total_pages,
            'has_next': has_next,
            'has_previous': has_previous,
            'next_page': page + 1 if has_next else None,
            'previous_page': page - 1 if has_previous else None,
        }

        logger.info(f"Returning {len(formatted_data)} items (page {page}/{total_pages})")

        return {
            'data': formatted_data,
            'pagination': pagination_info
        }

    def _format_extracted_item(self, item: ExtractedData):
        """Convert an ExtractedData instance into the legacy structured row format."""
        metadata = item.metadata or {}
        row = dict(metadata.get('raw_item', {}))
        row['extracted_item_id'] = item.id
        row['source'] = item.source
        # Determine spec section details with fallbacks
        spec_section_number = row.get('Spec Section #') or item.spec_section_number
        spec_section_name = row.get('Spec Section Name') or item.spec_section_name

        spec_section = getattr(item, 'spec_section', None)
        if spec_section:
            masterformat_section = getattr(spec_section, 'masterformat_section', None)
            if masterformat_section and getattr(masterformat_section, 'masterformat_number', None):
                spec_section_number = masterformat_section.masterformat_number

            if getattr(spec_section, 'custom_section_title', None):
                spec_section_name = spec_section.custom_section_title
            elif masterformat_section and getattr(masterformat_section, 'masterformat_description', None):
                spec_section_name = masterformat_section.masterformat_description

        row['Spec Section #'] = spec_section_number
        row['Spec Section Name'] = spec_section_name

        if item.responsible_party is not None or 'Responsible Party' in row:
            row['Responsible Party'] = item.responsible_party

        if item.pdf_locations is not None or 'pdf_locations' in row:
            row['pdf_locations'] = item.pdf_locations

        if item.extraction_type == 'inspection_log':
            row['Inspection Type And Requirements'] = item.requirement_text
            if metadata.get('inspection_frequency') is not None or 'Inspection Frequency' in row:
                row['Inspection Frequency'] = metadata.get('inspection_frequency')
        elif item.extraction_type == 'owner_deliverables_log':
            row['Exact Requirement Text'] = item.requirement_text
            if metadata.get('deliverable_type') is not None or 'Deliverable Type' in row:
                row['Deliverable Type'] = metadata.get('deliverable_type')
            if metadata.get('when_due') is not None or 'When Due' in row:
                row['When Due'] = metadata.get('when_due')
        elif item.extraction_type == 'qa_planner':
            row['Requirement Text'] = item.requirement_text
            row['item_type'] = item.item_type
            row['Paragraph Number'] = item.paragraph_number
            if metadata.get('when_due') is not None or 'When Due' in row:
                row['When Due'] = metadata.get('when_due')
        else:
            # Generic fallback for other extraction types
            row.setdefault('Requirement Text', item.requirement_text)

        return row

    def get_data_format(self, obj):
        """Return appropriate data format based on feature flag status."""
        request = self.context.get('request')
        if not request or not hasattr(request, 'user'):
            return 'markdown'  # Default to markdown if no request context
        
        try:
            # Get user, team, and project from request context
            user = request.user
            team = getattr(request, 'team', None)
            project = obj.project
            
            # Check if feature flag is active
            use_data_tables = is_inspection_log_use_data_tables_feature_flag_active(user, team, project)
            
            structured_rows = self.build_structured_rows(obj)
            has_structured_data = bool(structured_rows)

            # Return structured format if flag is active and structured data is available
            if use_data_tables and has_structured_data:
                return 'structured'
            else:
                return 'markdown'
        except Exception as e:
            # Log error and default to markdown for safety
            print(f"Error determining data format for log {obj.id}: {str(e)}")
            return 'markdown'
    
    def to_representation(self, instance):
        """
        Override to_representation to apply sorting and pagination to structured data.
        Now using DB-level queries for better performance.
        """
        data = super().to_representation(instance)

        request = self.context.get('request')

        # Check if we have ExtractedData records available
        has_extracted_data = hasattr(instance, 'extracted_items') and instance.extracted_items.exists()

        # Also check for human-created highlights
        has_human_highlights = ExtractedData.objects.filter(
            ai_generated_log__isnull=True,
            project=instance.project,
            project_version=instance.project_version,
            extraction_type=instance.log_type,
            source=ExtractionSource.HUMAN,
        ).exists()

        # Use DB-level query if we have ExtractedData records
        if (has_extracted_data or has_human_highlights) and request:
            logger.info(f"Using DB-level query for log {instance.id}")

            query_params = self._coerce_query_params(request)

            # Get filter parameters if available
            filter_params = {}
            for param_name, param_value in query_params.items():
                if not isinstance(param_name, str) or not param_name.startswith('filter_'):
                    continue

                # Extract column name from parameter name and handle multiple underscores
                raw_key = param_name.replace('filter_', '')
                column_key = ' '.join(part for part in raw_key.split('_') if part).title()

                # Map specific parameter names to correct column keys
                if column_key == 'Spec Section':  # This covers both single and double underscore cases
                    column_key = 'Spec Section #'
                elif column_key == 'Item Type':
                    column_key = 'item_type'
                elif column_key == 'Responsible Party':
                    column_key = 'Responsible Party'
                elif column_key == 'Deliverable Type':
                    column_key = 'Deliverable Type'

                if isinstance(param_value, str):
                    values = [value for value in param_value.split(',') if value]
                elif isinstance(param_value, (list, tuple, set)):
                    values = [str(value) for value in param_value if value is not None]
                else:
                    values = []

                filter_params[column_key] = values

            # Get search parameter if available
            search_term = getattr(request, 'search_term', None)
            if not search_term and query_params:
                search_term = query_params.get('search', '')

            # Get sorting parameters if available
            sort_field = getattr(request, 'sort_field', 'spec_section_number')
            sort_direction = getattr(request, 'sort_direction', 'asc')

            # Get pagination parameters
            page = query_params.get('page', 1)
            page_size = query_params.get('page_size', 50)

            try:
                page = int(page)
            except (TypeError, ValueError):
                page = 1

            try:
                page_size = int(page_size)
            except (TypeError, ValueError):
                page_size = 50

            # Use the new DB-level query method
            result = self.query_extracted_data_with_filters(
                instance,
                filter_params=filter_params if filter_params else None,
                search_term=search_term if search_term else None,
                sort_field=sort_field,
                sort_direction=sort_direction,
                page=page,
                page_size=page_size
            )

            data['log_data'] = result['data']
            data['pagination'] = result['pagination']
        else:
            # Fallback to old method for logs without ExtractedData records
            logger.info(f"Falling back to Python-level processing for log {instance.id} (no ExtractedData records)")

            structured_rows = self.build_structured_rows(instance)
            data['log_data'] = structured_rows

            # Apply filtering, search, sorting and pagination to structured rows if they exist
            if structured_rows and request:
                query_params = self._coerce_query_params(request)

                # Get filter parameters if available
                filter_params = {}
                for param_name, param_value in query_params.items():
                    if not isinstance(param_name, str) or not param_name.startswith('filter_'):
                        continue

                    # Extract column name from parameter name and handle multiple underscores
                    raw_key = param_name.replace('filter_', '')
                    column_key = ' '.join(part for part in raw_key.split('_') if part).title()

                    # Map specific parameter names to correct column keys
                    if column_key == 'Spec Section':  # This covers both single and double underscore cases
                        column_key = 'Spec Section #'
                    elif column_key == 'Item Type':
                        column_key = 'item_type'
                    elif column_key == 'Responsible Party':
                        column_key = 'Responsible Party'

                    if isinstance(param_value, str):
                        values = [value for value in param_value.split(',') if value]
                    elif isinstance(param_value, (list, tuple, set)):
                        values = [str(value) for value in param_value if value is not None]
                    else:
                        values = []

                    filter_params[column_key] = values

                # Apply column-based filtering if filter parameters are provided
                if filter_params:
                    filtered_data = self.filter_structured_data(structured_rows, filter_params)
                else:
                    filtered_data = structured_rows

                # Get search parameter if available
                search_term = getattr(request, 'search_term', None)
                if not search_term and query_params:
                    search_term = query_params.get('search', '')

                # Apply search filtering if search term is provided
                if search_term:
                    filtered_data = self.search_structured_data(filtered_data, search_term)
                else:
                    filtered_data = filtered_data

                # Get sorting parameters if available
                sort_field = getattr(request, 'sort_field', 'spec_section_number')
                sort_direction = getattr(request, 'sort_direction', 'asc')

                # Apply sorting if sorting parameters are provided
                sorted_data = self.sort_structured_data(filtered_data, sort_field, sort_direction)

                # Check if pagination parameters are present
                page = None
                page_size = None
                if query_params:
                    page = query_params.get('page')
                    page_size = query_params.get('page_size')

                # Always apply pagination for structured data to provide pagination info
                # Use default page=1 and page_size=50 if not specified
                if not page:
                    page = 1
                if not page_size:
                    page_size = 50

                # Apply pagination to sorted data
                paginated_data = self.paginate_structured_data(sorted_data, request, default_page=page, default_page_size=page_size)
                data['log_data'] = paginated_data['data']
                data['pagination'] = paginated_data['pagination']

        return data
    
    def paginate_structured_data(self, log_data, request, default_page=1, default_page_size=50):
        """
        Apply pagination to structured data.
        """
        try:
            query_params = self._coerce_query_params(request)

            # Get pagination parameters, use defaults if not provided
            raw_page = query_params.get('page', default_page)
            raw_page_size = query_params.get('page_size', default_page_size)

            try:
                page = int(raw_page)
            except (TypeError, ValueError):
                page = int(default_page)

            try:
                page_size = int(raw_page_size)
            except (TypeError, ValueError):
                page_size = int(default_page_size)
            
            # Validate parameters
            page = max(1, page)
            page_size = max(1, min(page_size, 100))  # Limit page size to 100
            
            # Calculate pagination
            total_items = len(log_data)
            start_index = (page - 1) * page_size
            end_index = start_index + page_size
            
            # Get paginated data
            paginated_data = log_data[start_index:end_index]
            
            # Calculate pagination metadata
            total_pages = (total_items + page_size - 1) // page_size
            has_next = page < total_pages
            has_previous = page > 1
            
            pagination_info = {
                'current_page': page,
                'page_size': page_size,
                'total_items': total_items,
                'total_pages': total_pages,
                'has_next': has_next,
                'has_previous': has_previous,
                'next_page': page + 1 if has_next else None,
                'previous_page': page - 1 if has_previous else None,
            }
            
            return {
                'data': paginated_data,
                'pagination': pagination_info
            }
            
        except (ValueError, TypeError) as e:
            # Return all data if pagination fails
            return {
                'data': log_data,
                'pagination': {
                    'current_page': 1,
                    'page_size': len(log_data),
                    'total_items': len(log_data),
                    'total_pages': 1,
                    'has_next': False,
                    'has_previous': False,
                    'next_page': None,
                    'previous_page': None,
                }
            }
    
    def sort_structured_data(self, log_data, sort_field, sort_direction):
        """
        Sort structured data by the specified field and direction.
        """
        print("sort_structured_data", sort_field, sort_direction)
        try:
            # Map field names to the actual keys in the structured data
            field_mapping = {
                'spec_section_number': 'Spec Section #',
                'spec_section_name': 'Spec Section Name',
                'inspection_type_and_requirements': 'Inspection Type And Requirements',
                'inspection_frequency': 'Inspection Frequency',
                'responsible_party': 'Responsible Party',
                'deliverable_type': 'Deliverable Type',
                'when_due': 'When Due',
                'exact_requirement_text': 'Exact Requirement Text',
                # QA Planner fields
                'paragraph_number': 'Paragraph Number',
                'item_type': 'item_type',
                'requirement_text': 'Requirement Text'
            }
            
            # Get the actual field key
            field_key = field_mapping.get(sort_field, sort_field)
            
            # Sort the data
            reverse = sort_direction == 'desc'
            
            # Handle None values by placing them at the end
            def sort_key(item):
                value = item.get(field_key, '')
                if value is None:
                    return '' if reverse else 'zzz'  # Place None at end for desc, beginning for asc
                return str(value).lower()
            
            sorted_data = sorted(log_data, key=sort_key, reverse=reverse)
            
            return sorted_data
            
        except Exception as e:
            # Log error and return original data
            print(f"Error sorting structured data: {str(e)}")
            return log_data

    def search_structured_data(self, log_data, search_term):
        """
        Search structured data across all fields for the given search term (case-insensitive).
        """
        try:
            if not search_term or not log_data:
                return log_data
            
            search_term_lower = str(search_term).lower()
            filtered_data = []
            
            for item in log_data:
                # Search across all fields in the item
                match_found = False
                for key, value in item.items():
                    if value is not None:
                        # Convert value to string and search case-insensitively
                        value_str = str(value).lower()
                        if search_term_lower in value_str:
                            match_found = True
                            break
                
                if match_found:
                    filtered_data.append(item)
            
            return filtered_data
            
        except Exception as e:
            # Log error and return original data
            print(f"Error searching structured data: {str(e)}")
            return log_data

    def filter_structured_data(self, log_data, filter_params):
        """
        Filter structured data based on column-specific filter values.
        Uses OR logic within each column and AND logic across columns.
        
        @param log_data: List of data items to filter
        @param filter_params: Dict with column names as keys and lists of allowed values as values
                            e.g., {'Spec Section #': ['01 5000', '02 3000'], 'item_type': ['Product']}
        
        Logic:
        - Within a column: OR logic (item matches ANY of the selected values)
        - Across columns: AND logic (item must match at least one value from EVERY filtered column)
        """
        try:
            if not filter_params or not log_data:
                return log_data
            
            filtered_data = []
            
            for item in log_data:
                # Check if item passes all active filters (AND logic across columns)
                passes_all_filters = True
                
                for column_key, allowed_values in filter_params.items():
                    if not allowed_values:  # Skip empty filter arrays
                        continue
                        
                    item_value = item.get(column_key)
                    if item_value is None:
                        # Item has no value for this column, fails the filter
                        passes_all_filters = False
                        break
                    
                    # Convert to string for comparison
                    item_value_str = str(item_value)
                    
                    # OR logic within column: check if item value matches ANY of the allowed values
                    column_match = False
                    for allowed_value in allowed_values:
                        if item_value_str == str(allowed_value):
                            column_match = True
                            break
                    
                    # If no match found for this column, item fails the filter
                    if not column_match:
                        passes_all_filters = False
                        break
                
                # Add item only if it passes ALL column filters
                if passes_all_filters:
                    filtered_data.append(item)
            
            return filtered_data
            
        except Exception as e:
            # Log error and return original data
            print(f"Error filtering structured data: {str(e)}")
            return log_data




