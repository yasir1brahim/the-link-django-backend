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
    SubmittalItemList, ExcelExportHeader, ProjectVersion, Chat, ChatMessage
)


class ProjectMembershipInlineAdmin(admin.TabularInline):
    model = ProjectMembership
    list_display = ["user", "role"]

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
    correct_classification: bool = Field(description="Whether the parser classification is correct, if true, parser_topic_classification and parser_item_classification should be the same")
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
        # try:
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
            
        # except Exception as e:
        #     return JsonResponse({
        #         'success': False,
        #         'error': str(e)
        #     }, status=500)
    
    def _read_csv(self, csv_file) -> List[Dict[str, Any]]:
        """Read CSV file and return as list of dictionaries."""
        content = csv_file.read().decode('utf-8')
        csv_reader = csv.DictReader(io.StringIO(content))
        return list(csv_reader)
    
    def _validate_with_openai(self, spec_pdf, parser_results: List[Dict], keywords: List[Dict]) -> List[Dict]:
        """Validate parser results using OpenAI."""
        # Read PDF content
        pdf_content = spec_pdf.read()
        pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
        
        print(f"Keywords: {keywords}")
        
        validation_results = []
        
        for result in parser_results:
            # Prepare the prompt for OpenAI
            prompt = self._create_validation_prompt(
                result.get('text', ''),
                result.get('paragraph_number', ''),
                result.get('topic', ''),
                result.get('item', ''),
                str(keywords)
            )
            
            # Call OpenAI
            llm_response = self._call_openai(prompt, spec_pdf.name, pdf_base64)
            
            # Parse the response
            validation_result = self._parse_llm_response(llm_response, result)
            validation_results.append(validation_result)
        
        return validation_results
    
    def _create_validation_prompt(self, text: str, paragraph_number: str, parser_topic_classification: str, parser_item_classification: str, keywords_text: str) -> str:
        """Create the prompt for OpenAI validation."""
        return f"""
You are an expert at analyzing construction specification documents and validating parser classifications.

Context:
- Keywords used by the parser: {keywords_text}

Task:
Analyze the following text from a construction specification document and validate the parser's classification.

Text: "{text}"
Paragraph Number: {paragraph_number}
Parser Topic Classification: {parser_topic_classification}
Parser Item Classification: {parser_item_classification}

Please determine if the parser classification is correct. If not, identify the failure mode and suggest missing keywords.
To help deduce the failure mode, consider the following:
- The parser works by parsing the text into a tree-like hierarchy of sections, keywords, and subkeywords.
- For each node in the hierarchy, the parser looks for keywords in the text. If the item is a non-terminal node, the parser will look for keywords of the "topic" type. If the item is a terminal node, the parser will look for keywords of the "item" type.
- The "item" keywords that are considered are restricted by the topic of the node's parent. For example, if the node's parent is a "Summary" node, the parser will only consider "item" keywords that are relevant to the topic "Summary".
- Unfortunately, the parser does not always get the hierarchy correct, which can lead to incorrect classifications.
- One good way to check for hierarchy parsing errors is to look at the "paragraph number" of the text. If the paragraph number does not match what you see in the PDF file, it is likely due to a hierarchy parsing error.
- If the paragraph and hierarchy parsing looks correct, but the classification is still "UNKNOWN" or seems incorrect, it is likely due to a missing keyword. In this case, you should mark the failure mode as "Missing keyword" and suggest missing keywords.


Be thorough in your analysis and provide specific reasoning for your classification.
"""
    
    def _call_openai(self, prompt: str, pdf_filename: str, pdf_base64: str) -> str:
        """Call OpenAI API with the prompt and PDF context."""
        try:
            print(f"Calling OpenAI with prompt: {prompt}")
            client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
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
                        "name": "ValidationResult",
                        "schema": ValidationResult.model_json_schema()
                    },
                },
                temperature=0.1
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            raise Exception(f"OpenAI API error: {str(e)}")
    
    def _parse_llm_response(self, llm_response: str, original_result: Dict) -> Dict:
        """Parse the LLM response and format it according to the required structure."""
        try:
            parsed_response = json.loads(llm_response)
            
            return {
                "text": original_result.get('text', ''),
                "paragraph_number": original_result.get('paragraph_number', ''),
                "correct_classification": parsed_response.get('correct_classification', False),
                "parser_topic_classification": original_result.get('topic', ''),
                "parser_item_classification": original_result.get('item', ''),
                "llm_topic_classification": parsed_response.get('llm_topic_classification', ''),
                "llm_item_classification": parsed_response.get('llm_item_classification', ''),
                "failure_mode": parsed_response.get('failure_mode'),
                "missing_keywords": parsed_response.get('missing_keywords', []),
                "reasoning_notes": parsed_response.get('reasoning_notes', '')
            }
            
        except json.JSONDecodeError:
            # Fallback if JSON parsing fails
            return {
                "text": original_result.get('text', ''),
                "paragraph_number": original_result.get('paragraph_number', ''),
                "correct_classification": False,
                "parser_topic_classification": original_result.get('topic', ''),
                "parser_item_classification": original_result.get('item', ''),
                "llm_topic_classification": "Error parsing response",
                "llm_item_classification": "Error parsing response",
                "failure_mode": "Unknown",
                "missing_keywords": [],
                "reasoning_notes": "Error parsing response"
            }


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

