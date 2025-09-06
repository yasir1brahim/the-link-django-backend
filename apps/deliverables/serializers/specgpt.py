from rest_framework import serializers
from apps.deliverables.models import Chat, ChatMessage, AiGeneratedLog
from apps.utils.feature_flags import is_inspection_log_use_data_tables_feature_flag_active


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
            
            # Return structured format if flag is active and structured data is available
            if use_data_tables and obj.log_data:
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
        """
        data = super().to_representation(instance)
        
        # Apply filtering, search, sorting and pagination to log_data if it exists
        request = self.context.get('request')
        if data.get('log_data') and request:
            # Get filter parameters if available
            filter_params = {}
            if hasattr(request, 'query_params'):
                print(f"DEBUG: All query params: {dict(request.query_params)}")
                for param_name, param_value in request.query_params.items():
                    if param_name.startswith('filter_'):
                        print(f"DEBUG: Processing filter param: {param_name} = {param_value}")
                        # Extract column name from parameter name and handle multiple underscores
                        raw_key = param_name.replace('filter_', '')
                        # Replace underscores with spaces, but handle multiple consecutive underscores
                        column_key = ' '.join(part for part in raw_key.split('_') if part).title()
                        print(f"DEBUG: Column key after processing: '{column_key}'")
                        
                        # Map specific parameter names to correct column keys
                        if column_key == 'Spec Section':  # This covers both single and double underscore cases
                            column_key = 'Spec Section #'
                            print(f"DEBUG: Mapped to: '{column_key}'")
                        elif column_key == 'Item Type':
                            column_key = 'item_type'
                            print(f"DEBUG: Mapped to: '{column_key}'")
                        elif column_key == 'Responsible Party':
                            column_key = 'Responsible Party'
                            print(f"DEBUG: Mapped to: '{column_key}'")
                        
                        filter_params[column_key] = param_value.split(',') if param_value else []
            
            # Apply column-based filtering if filter parameters are provided
            if filter_params:
                print(f"DEBUG: Applying filters: {filter_params}")
                print(f"DEBUG: Original data count: {len(data['log_data'])}")
                filtered_data = self.filter_structured_data(data['log_data'], filter_params)
                print(f"DEBUG: Filtered data count: {len(filtered_data)}")
            else:
                filtered_data = data['log_data']
            
            # Get search parameter if available
            search_term = getattr(request, 'search_term', None)
            if not search_term and hasattr(request, 'query_params'):
                search_term = request.query_params.get('search', '')
            
            # Apply search filtering if search term is provided
            if search_term:
                filtered_data = self.search_structured_data(filtered_data, search_term)
            else:
                filtered_data = filtered_data
            
            # Get sorting parameters if available
            sort_field = getattr(request, 'sort_field', None)
            sort_direction = getattr(request, 'sort_direction', 'desc')
            
            # Apply sorting if sorting parameters are provided
            if sort_field and sort_field != 'created_at':
                sorted_data = self.sort_structured_data(filtered_data, sort_field, sort_direction)
            else:
                # No sorting - use filtered data order
                sorted_data = filtered_data
            
            # Check if pagination parameters are present
            page = None
            page_size = None
            if hasattr(request, 'query_params') and request.query_params:
                page = request.query_params.get('page')
                page_size = request.query_params.get('page_size')
            
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
            # Get pagination parameters, use defaults if not provided
            page = int(request.query_params.get('page', default_page))
            page_size = int(request.query_params.get('page_size', default_page_size))
            
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
            print(f"DEBUG: filter_structured_data called with {len(log_data)} items")
            print(f"DEBUG: filter_params: {filter_params}")
            
            if not filter_params or not log_data:
                return log_data
            
            # Debug: Show a sample of the data structure
            if log_data:
                print(f"DEBUG: Sample data item: {log_data[0]}")
                print(f"DEBUG: Available keys in data: {list(log_data[0].keys())}")
            
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




