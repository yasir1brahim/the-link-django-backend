from collections import defaultdict

from django.db import transaction
from rest_framework import serializers

from . import EmbedDocumentSerializer
from ..models import (
    UploadedFile,
    NoticeExcerpt,
    NoticeMatch,
)
from ..utils import ANCHOR_REPR_DELIMITER
from ...utils.drf.fields import SplitCharField


class NoticeExcerptSerializer(serializers.ModelSerializer):
    anchor = SplitCharField(delimiter=ANCHOR_REPR_DELIMITER)

    class Meta:
        model = NoticeExcerpt
        fields = [
            'anchor',
            'lines',
        ]


class NoticeMatchSerializer(serializers.ModelSerializer):
    document = EmbedDocumentSerializer()
    excerpt_anchors = NoticeExcerptSerializer(many=True)
    leading_anchor = SplitCharField(delimiter=ANCHOR_REPR_DELIMITER)

    class Meta:
        model = NoticeMatch
        fields = [
            'document',

            'notice_type',
            'notice_type_match',

            'highlight_heuristic_match',
            'highlight_discriminators',

            'excerpt_anchors',
            'leading_anchor',
        ]


# region processing

class NoticeLineProcessingSerializer(serializers.Serializer):
    text = serializers.CharField()
    page_no = serializers.IntegerField()
    x_start = serializers.FloatField()
    x_end = serializers.FloatField()
    y_start = serializers.FloatField()
    y_end = serializers.FloatField()


class NoticeExcerptProcessingSerializer(serializers.ModelSerializer):
    anchor = SplitCharField(delimiter=ANCHOR_REPR_DELIMITER)
    lines = NoticeLineProcessingSerializer(many=True)

    class Meta:
        model = NoticeExcerpt
        fields = [
            'anchor',
            'lines',
        ]


class NoticeMatchProcessingSerializer(serializers.ModelSerializer):
    highlight_discriminators = serializers.ListField(
        child=serializers.CharField(),
    )

    excerpt_anchors = serializers.ListField(
        child=SplitCharField(delimiter=ANCHOR_REPR_DELIMITER),
    )
    leading_anchor = SplitCharField(delimiter=ANCHOR_REPR_DELIMITER)

    class Meta:
        model = NoticeMatch
        fields = [
            'notice_type',
            'notice_type_match',

            'highlight_heuristic_match',
            'highlight_discriminators',

            'excerpt_anchors',
            'leading_anchor',
        ]


class NoticeProcessingCallbackSerializer(serializers.Serializer):
    document = serializers.PrimaryKeyRelatedField(
        queryset=UploadedFile.objects.select_related('project'),
        required=True,
    )
    excerpts = NoticeExcerptProcessingSerializer(many=True, required=True)
    matches = NoticeMatchProcessingSerializer(many=True, required=True)

    def _validate_all_anchors(self, attrs):
        match_anchors = set()
        for match in attrs['matches']:
            for anchor in match['excerpt_anchors']:
                match_anchors.add(anchor)

        excerpt_anchors = set()
        for excerpt in attrs['excerpts']:
            excerpt_anchors.add(excerpt['anchor'])

        leading_anchors = set()
        for match in attrs['matches']:
            leading_anchors.add(match['leading_anchor'])

        if excerpt_anchors != match_anchors:
            raise serializers.ValidationError(
                "Excerpt anchors do not contain all referenced anchors."
            )

        if excerpt_anchors - leading_anchors:
            raise serializers.ValidationError(
                "Excerpt anchors do not contain all leading anchors."
            )

    def validate(self, attrs):
        self._validate_all_anchors(attrs)
        return attrs

    def save(self, **kwargs):
        document = self.validated_data['document']
        excerpts = self.validated_data['excerpts']
        matches = self.validated_data['matches']

        # First, prepare all the objects that'll be created
        anchor2excerpt_map = {}
        anchor2excerpt_assignment = defaultdict(list)

        notice_matches_to_create = []

        for excerpt in excerpts:
            notice_excerpt = NoticeExcerpt(
                document=document,
                **excerpt,
            )
            anchor2excerpt_map[excerpt['anchor']] = notice_excerpt

        for match in matches:
            # pop m2m relationships
            match_data = match.copy()
            match_data.pop('excerpt_anchors')

            notice_match = NoticeMatch(
                document=document,
                project=document.project,
                **match_data,
            )
            notice_matches_to_create.append(notice_match)

            # Prepare m2m relationships
            for anchor in match['excerpt_anchors']:
                anchor = anchor
                anchor2excerpt_assignment[anchor].append(notice_match)

        # Then, create all the objects
        with transaction.atomic():
            # First, create the excerpts so we can get their IDs
            NoticeExcerpt.objects.bulk_create(anchor2excerpt_map.values())
            # Then, create the matches
            NoticeMatch.objects.bulk_create(notice_matches_to_create)

            # Then, assign the matches to the excerpts
            for anchor, excerpts in anchor2excerpt_assignment.items():
                notice_excerpt = anchor2excerpt_map[anchor]
                notice_excerpt.matches.set(excerpts)

# endregion processing
