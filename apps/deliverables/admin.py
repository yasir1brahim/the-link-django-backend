from django.contrib import admin
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import path
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import user_passes_test
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from pydantic import BaseModel, Field
from promptlayer.templates import TemplateManager
import traceback
from typing import Literal
import json
import csv
import io
import base64
from typing import List, Dict, Any, Optional
import openai
from django.conf import settings
from .models import (Project, ProjectMembership, Entitlement, SubmittalItem,
    UploadedFile, SpecSection, MasterFormatSection,
    SubmittalItemList, ExcelExportHeader, ProjectVersion, Chat, ChatMessage,
    AiGeneratedLog, ExtractedData, CustomItemType, ExtractionNote
)


class ProjectMembershipInlineAdmin(admin.TabularInline):
    model = ProjectMembership
    list_display = ["user", "role"]
    autocomplete_fields = ["user"]

class ProjectVersionInlineAdmin(admin.TabularInline):
    model = ProjectVersion
    list_display = ["project", "version_name"]

class EntitlementInlineAdmin(admin.TabularInline):
    model = Entitlement
    list_display = ["code_name", "readable_name"]



@admin.register(ProjectMembership)
class ProjectMembershipAdmin(admin.ModelAdmin):
    list_display = ["user", "project", "role"]
    list_filter = ["project", "role"]
    search_fields = ["user__email", "project__name"]


@admin.register(Entitlement)
class EntitlementAdmin(admin.ModelAdmin):
    list_display = ["id", "code_name", "readable_name"]
    search_fields = ["code_name", "readable_name"]
    list_filter = ["code_name", "readable_name"]



@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "team"]
    list_filter = ["name", "team"]
    search_fields = ["name", "team__name"]
    inlines = (ProjectMembershipInlineAdmin, ProjectVersionInlineAdmin)
    filter_horizontal = ("entitlements",)


@admin.register(ProjectVersion)
class ProjectVersionAdmin(admin.ModelAdmin):
    list_display = ["id", "project", "version_name"]
    list_filter = ["project", "version_name"]
    search_fields = ["project__name", "version_name"]


@admin.register(SubmittalItem)
class SubmittalItemAdmin(admin.ModelAdmin):
    list_display = ["id", "project", "document", "masterformat_section", "paragraph_number", "submittal_type", "submittal_description"]
    list_filter = ["project", "document", "masterformat_section", "paragraph_number", "submittal_type", "submittal_description"]
    search_fields = ["project__name", "document__name", "masterformat_section__masterformat_number", "paragraph_number", "submittal_type", "submittal_description"]


class SubmittalItemInlineAdmin(admin.TabularInline):
    model = SubmittalItem
    list_display = ["id", "project", "document", "masterformat_section", "paragraph_number", "submittal_type", "submittal_description"]
    list_filter = ["project", "document", "masterformat_section", "paragraph_number", "submittal_type", "submittal_description"]
    search_fields = ["project__name", "document__name", "masterformat_section__masterformat_number", "paragraph_number", "submittal_type", "submittal_description"]


@admin.register(UploadedFile)
class UploadedFileAdmin(admin.ModelAdmin):
    list_display = ["id", "project", "name", "uploaded_by", "created_at"]
    list_filter = ["project", "uploaded_by"]
    search_fields = ["name", "uploaded_by__email", "project__name"]

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('parser-validation-tool/', self.admin_site.admin_view(ParserValidationToolView.as_view()), name='parser-validation-tool'),
        ]
        return custom_urls + urls


class ValidationResult(BaseModel):
    correct_topic_classification: bool = Field(description="Whether the parser topic classification is correct")
    correct_item_classification: bool = Field(description="Whether the parser item classification is correct")
    parser_topic_classification: str = Field(description="The classification determined by the parser")
    parser_item_classification: str = Field(description="The classification determined by the parser")
    llm_topic_classification: str = Field(description="The classification determined by the LLM")
    llm_item_classification: str = Field(description="The classification determined by the LLM")
    failure_mode: Optional[Literal["Incorrect hierarchy parsing", "Missing keyword", "Unknown"]] = Field(
        default=None, 
        description="Failure mode if classification is incorrect"
    )
    missing_keywords: Optional[List[str]] = Field(
        default=None,
        description="List of suggested keywords to add"
    )
    reasoning_notes: str = Field(description="Reasoning notes for the classification")

class BatchValidationResult(BaseModel):
    results: List[ValidationResult] = Field(description="List of validation results")

class ParserValidationToolView(View):
    """
    Admin tool for validating parser classifications using OpenAI.
    """
    
    def get(self, request):
        """Display the upload form."""
        return render(request, 'admin/deliverables/uploadedfile/parser_validation_tool.html', {
            'title': 'Parser Validation Tool',
            'opts': UploadedFile._meta,
        })
    
    def post(self, request):
        """Process the uploaded files and validate classifications."""
        try:
            # Get uploaded files
            spec_pdf = request.FILES.get('spec_pdf')
            parser_results_csv = request.FILES.get('parser_results_csv')
            keywords_csv = request.FILES.get('keywords_csv')
            
            if not all([spec_pdf, parser_results_csv, keywords_csv]):
                messages.error(request, 'All three files are required: Spec PDF, Parser Results CSV, and Keywords CSV.')
                return redirect(reverse('admin:parser-validation-tool'))
            
            # Read CSV files
            parser_results = self._read_csv(parser_results_csv)
            keywords = self._read_csv(keywords_csv)
            
            # Process with OpenAI
            validation_results = self._validate_with_openai(spec_pdf, parser_results, keywords)
            
            # Return results as JSON
            return JsonResponse({
                'success': True,
                'results': validation_results
            })
                
        except Exception as e:
            print(traceback.format_exc())
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
    
    def _read_csv(self, csv_file) -> List[Dict[str, Any]]:
        """Read CSV file and return as list of dictionaries."""
        content = csv_file.read().decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(content))
        return list(csv_reader)
    
    def _validate_with_openai(self, spec_pdf, parser_results: List[Dict], keywords: List[Dict]) -> List[Dict]:
        """Validate parser results using OpenAI with batching."""
        # Read PDF content
        pdf_content = spec_pdf.read()
        pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
        
        # Prepare keywords context
        keywords_text = str(keywords)
        
        # Process in batches
        batch_size = 20  # Process 20 items per API call
        validation_results = []
        
        for i in range(0, len(parser_results), batch_size):
            batch = parser_results[i:i + batch_size]
            batch_results = self._process_batch(batch, spec_pdf.name, pdf_base64, keywords_text)
            print("Got batch results")
            validation_results.extend(batch_results)
            print(f"Batch {i//batch_size + 1} results: {batch_results}")
        
        return validation_results
    
    def _process_batch(self, batch: List[Dict], pdf_filename: str, pdf_base64: str, keywords_text: str) -> List[Dict]:
        """Process a batch of parser results in a single OpenAI call."""
        # Create batch prompt
        batch_prompt = self._create_batch_prompt(batch, keywords_text)
        model_name = self.get_promptlayer_model_metadata(self.get_promptlayer_template('classification_checker'))['name']
        
        # Call OpenAI
        llm_response = self._call_openai(batch_prompt, pdf_filename, pdf_base64, model_name)
        
        # Parse batch response
        return self._parse_batch_response(llm_response, batch)
    
    def get_promptlayer_template(self, promptlayer_prompt_name):
        template_manager = TemplateManager(api_key=settings.PROMPTLAYER_API_KEY)
        return template_manager.get(promptlayer_prompt_name, {'label': settings.ENVIRONMENT})

    def get_promptlayer_model_metadata(self, promptlayer_template):
        return promptlayer_template['metadata']['model']
    
    def get_promptlayer_system_prompt(self, promptlayer_template):
        prompts = promptlayer_template['prompt_template']['messages']
        system_prompt = [prompt for prompt in prompts if prompt['role'] == 'system']
        return system_prompt[0]['content'][0]['text']
    
    def get_promptlayer_user_prompt(self, promptlayer_template):
        prompts = promptlayer_template['prompt_template']['messages']
        user_prompt = [prompt for prompt in prompts if prompt['role'] == 'user']
        return user_prompt[0]['content'][0]['text']
    
    def _create_batch_prompt(self, batch: List[Dict], keywords_text: str) -> str:
        """Create a prompt for processing multiple classifications at once."""
        batch_items = []
        
        for i, result in enumerate(batch, 1):
            item_text = f"""
Item {i}:
Text: "{result.get('text', '')}"
Paragraph Number: {result.get('paragraph_number', '')}
Parser Topic Classification: {result.get('topic', '')}
Parser Item Classification: {result.get('item', '')}
"""
            batch_items.append(item_text)
        
        batch_text = "\n".join(batch_items)

        promptlayer_template = self.get_promptlayer_template('classification_checker')
        promptlayer_system_prompt = self.get_promptlayer_system_prompt(promptlayer_template)
        promptlayer_user_prompt = self.get_promptlayer_user_prompt(promptlayer_template)

        user_prompt = promptlayer_user_prompt.format(batch_text=batch_text, keywords_text=keywords_text)
        
        return f"{promptlayer_system_prompt}\n\n{user_prompt}"
    
    def _parse_batch_response(self, llm_response: str, batch: List[Dict]) -> List[Dict]:
        """Parse the batch response and format it according to the required structure."""
        try:
            parsed_response = json.loads(llm_response)['results']
            print("Got Parsed response")
            
            # Handle both single object and array responses
            if isinstance(parsed_response, dict):
                # Single object response - convert to array
                parsed_response = [parsed_response]
            elif isinstance(parsed_response, list):
                # Array response - use as is
                pass
            else:
                raise ValueError("Unexpected response format")
            
            results = parsed_response
            for i, original_item in enumerate(batch):
                try:
                    results[i]['text'] = original_item['text']
                    results[i]['paragraph_number'] = original_item['paragraph_number']
                except Exception as e:
                    print(traceback.format_exc())
                    print(f"Error transforming response for item {i}")
                    print(f"Original item: {original_item}")
            print("Transformed response to include text and paragraph number")
            return results
            
        except json.JSONDecodeError:
            # Fallback if JSON parsing fails
            fallback_results = []
            for original_result in batch:
                fallback_result = {
                    "text": original_result.get('text', ''),
                    "paragraph_number": original_result.get('paragraph_number', ''),
                    "correct_classification": False,
                    "parser_topic_classification": original_result.get('topic', ''),
                    "parser_item_classification": original_result.get('item', ''),
                    "llm_topic_classification": "Error parsing batch response",
                    "llm_item_classification": "Error parsing batch response",
                    "failure_mode": "Unknown",
                    "missing_keywords": [],
                    "reasoning_notes": "Error parsing batch response"
                }
                fallback_results.append(fallback_result)
            return fallback_results


    def _call_openai(self, prompt: str, pdf_filename: str, pdf_base64: str, model_name: str) -> str:
        """Call OpenAI API with the prompt and PDF context."""
        try:
            client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
            
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at analyzing construction specification documents. Provide accurate classifications and detailed analysis."
                    },
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            },
                            {
                                "type": "file",
                                "file": {
                                    "filename": pdf_filename,
                                    "file_data": f"data:application/pdf;base64,{pdf_base64}"
                                }
                            }
                        ]
                    }
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "BatchValidationResult",
                        "schema": BatchValidationResult.model_json_schema()
                    },
                },
            )
            print("Batch validation result:")
            print(response.choices[0].message.content)
            return response.choices[0].message.content
            
        except Exception as e:
            raise Exception(f"OpenAI API error: {str(e)}")


@admin.register(SpecSection)
class SpecSectionAdmin(admin.ModelAdmin):
    list_display = ["id", "masterformat_section"]
    list_filter = ["masterformat_section"]
    search_fields = ["masterformat_section__masterformat_number"]

@admin.register(MasterFormatSection)
class MasterFormatSectionAdmin(admin.ModelAdmin):
    list_display = ["id", "masterformat_number", "masterformat_description"]
    search_fields = ["masterformat_number", "masterformat_description"]

@admin.register(SubmittalItemList)
class SubmittalItemListAdmin(admin.ModelAdmin):
    list_display = ["id", "project", "name", "created_by"]
    list_filter = ["project", "created_by"]
    search_fields = ["project__name", "name", "created_by__email"]
    filter_horizontal = ("submittals",)

@admin.register(ExcelExportHeader)
class ExcelExportHeaderAdmin(admin.ModelAdmin):
    list_display = ["user", "updated_at"]
    search_fields = ["user__email", ]

@admin.register(Chat)
class ChatAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "created_at"]
    list_filter = ["user"]
    search_fields = ["user__email"]

@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ["id", "chat", "created_at"]
    list_filter = ["chat"]
    search_fields = ["chat__user__email"]


@admin.register(AiGeneratedLog)
class AiGeneratedLogAdmin(admin.ModelAdmin):
    list_display = ["id", "project", "project_version", "log_type", "log_status", "created_at"]
    list_filter = ["log_type", "log_status", "created_at", "project", "project_version"]
    search_fields = ["project__name", "project_version__version_name", "log_type"]
    readonly_fields = ["created_at"]
    list_per_page = 50
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('project', 'project_version', 'log_type', 'log_status')
        }),
        ('Content', {
            'fields': ('log_table', 'log_data'),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def has_add_permission(self, request):
        """Disable manual creation of AI generated logs."""
        return False
    
    def has_delete_permission(self, request, obj=None):
        """Allow deletion for admin users."""
        return request.user.is_superuser


@admin.register(ExtractedData)
class ExtractedDataAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'spec_section_number', 'spec_section_name',
        'extraction_type', 'source', 'created_by', 'created_at'
    ]
    list_filter = [
        'source', 'extraction_type', 'item_type', 'project'
    ]
    search_fields = [
        'spec_section_number', 'spec_section_name',
        'requirement_text'
    ]
    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Basic Information', {
            'fields': (
                'source', 'created_by', 'ai_generated_log',
                'project', 'project_version', 'spec_section',
                'spec_section_number', 'spec_section_name'
            )
        }),
        ('Extraction Details', {
            'fields': (
                'extraction_type', 'item_type', 'paragraph_number',
                'requirement_text', 'responsible_party', 'metadata'
            )
        }),
        ('PDF Data', {
            'fields': ('pdf_locations',),
            'classes': ('collapse',)
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'ai_generated_log', 'project', 'project_version',
            'spec_section', 'created_by'
        )


@admin.register(CustomItemType)
class CustomItemTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "project", "created_by", "color", "is_active", "created_at")
    list_filter = ("project", "is_active")
    search_fields = ("name", "project__name", "project__project_number")
    autocomplete_fields = ("project", "created_by")
    readonly_fields = ("created_at", "updated_at")


@admin.register(ExtractionNote)
class ExtractionNoteAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'extracted_data', 'text_preview', 'created_by', 'created_at'
    ]
    list_filter = [
        'created_at',
        ('extracted_data__project', admin.RelatedOnlyFieldListFilter)
    ]
    search_fields = [
        'text', 'created_by__email', 'extracted_data__spec_section_number'
    ]
    readonly_fields = ['created_at', 'updated_at']
    raw_id_fields = ['extracted_data', 'created_by']

    fieldsets = (
        ('Note Information', {
            'fields': ('extracted_data', 'text', 'created_by')
        }),
        ('Metadata', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )

    def text_preview(self, obj):
        """Show truncated text in list view"""
        return obj.text[:75] + '...' if len(obj.text) > 75 else obj.text
    text_preview.short_description = 'Text'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'extracted_data', 'created_by'
        )
