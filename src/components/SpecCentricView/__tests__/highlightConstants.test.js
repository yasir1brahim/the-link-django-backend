import { HIGHLIGHT_TYPES, formatCustomTypes, isCustomHighlight, getHighlightColor } from '../highlightConstants';

describe('highlightConstants helpers for custom types', () => {
  const customTypes = [
    { id: 1, name: 'Safety', color: '#FF0000' },
    { id: 2, name: 'Commissioning', color: '#00FF00' },
  ];

  it('formats custom types into highlight options', () => {
    expect(formatCustomTypes(customTypes)).toEqual([
      {
        key: 'custom_1',
        type: 'Safety',
        color: '#FF0000A6',
        isCustom: true,
        customTypeId: 1,
      },
      {
        key: 'custom_2',
        type: 'Commissioning',
        color: '#00FF00A6',
        isCustom: true,
        customTypeId: 2,
      },
    ]);
  });

  it('identifies when a highlight is custom', () => {
    expect(
      isCustomHighlight({
        extraction_type: 'custom_highlights',
        custom_item_type: { id: 2 },
      })
    ).toBe(true);

    expect(
      isCustomHighlight({
        extraction_type: 'qa_planner',
        custom_item_type: { id: 2 },
      })
    ).toBe(false);
  });

  it('chooses the correct color for custom highlights', () => {
    const highlight = {
      extraction_type: 'custom_highlights',
      custom_item_type: { id: 1 },
    };

    expect(getHighlightColor(highlight, customTypes)).toBe('#FF0000A6');
  });

  it('falls back to grey when custom type is missing', () => {
    const highlight = {
      extraction_type: 'custom_highlights',
      custom_item_type: { id: 999 },
    };

    expect(getHighlightColor(highlight, customTypes)).toBe('rgba(128, 128, 128, 0.6)');
  });

  it('uses standard highlight colors when not custom', () => {
    const highlight = {
      extraction_type: 'qa_planner',
      item_type: HIGHLIGHT_TYPES[0].key,
    };

    expect(getHighlightColor(highlight, customTypes)).toBe(HIGHLIGHT_TYPES[0].color);
  });
});
import { HIGHLIGHT_TYPES } from '../highlightConstants';
import {
  formatCustomTypes,
  isCustomHighlight,
  getHighlightColor,
} from '../highlightConstants';

describe('highlightConstants helpers for custom types', () => {
  const customTypes = [
    { id: 1, name: 'Safety', color: '#FF0000' },
    { id: 2, name: 'Commissioning', color: '#00FF00' },
  ];

  it('formats custom types into highlight options', () => {
    expect(formatCustomTypes(customTypes)).toEqual([
      {
        key: 'custom_1',
        type: 'Safety',
        color: '#FF0000A6',
        isCustom: true,
        customTypeId: 1,
      },
      {
        key: 'custom_2',
        type: 'Commissioning',
        color: '#00FF00A6',
        isCustom: true,
        customTypeId: 2,
      },
    ]);
  });

  it('identifies when a highlight is custom', () => {
    expect(
      isCustomHighlight({
        extraction_type: 'custom_highlights',
        custom_item_type: { id: 2 },
      })
    ).toBe(true);

    expect(
      isCustomHighlight({
        extraction_type: 'qa_planner',
        custom_item_type: { id: 2 },
      })
    ).toBe(false);
  });

  it('chooses the correct color for custom highlights', () => {
    const highlight = {
      extraction_type: 'custom_highlights',
      custom_item_type: { id: 1 },
    };

    expect(getHighlightColor(highlight, customTypes)).toBe('#FF0000A6');
  });

  it('falls back to grey when custom type is missing', () => {
    const highlight = {
      extraction_type: 'custom_highlights',
      custom_item_type: { id: 999 },
    };

    expect(getHighlightColor(highlight, customTypes)).toBe('rgba(128, 128, 128, 0.6)');
  });

  it('uses standard highlight colors when not custom', () => {
    const highlight = {
      extraction_type: 'qa_planner',
      item_type: HIGHLIGHT_TYPES[0].key,
    };

    expect(getHighlightColor(highlight, customTypes)).toBe(HIGHLIGHT_TYPES[0].color);
  });
});

