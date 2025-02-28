from typing import TypedDict, List

from .models import SubmittalItem


class TextDiff(TypedDict):
    type: str  # 'equal', 'delete', or 'insert'
    value: str

class SubmittalItemDifference(TypedDict):
    old_submittal: SubmittalItem
    new_submittal: SubmittalItem
    content_differences: List[TextDiff]
    paragraph_number_differences: List[TextDiff]
    
class DifferenceSummary(TypedDict):
    additions: List[SubmittalItem]
    deletions: List[SubmittalItem]
    modifications: List[SubmittalItemDifference]
    unchanged: List[SubmittalItem]
