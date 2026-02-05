import React from 'react';
import { render, waitFor } from '@testing-library/react';
import SpecViewer from '../SpecViewer';

jest.mock('../../api/SpecCentricView/api', () => ({
  getSpecCentricData: jest.fn(),
  getSpecSectionContent: jest.fn(),
  getCustomItemTypes: jest.fn(),
}));

const mockDocumentHighlighter = jest.fn(() => null);
const mockHighlightLegend = jest.fn(() => null);

jest.mock('../DocumentHighlighter', () => (props) => mockDocumentHighlighter(props));
jest.mock('../HighlightLegend', () => (props) => mockHighlightLegend(props));
jest.mock('../SpecViewerSidebar', () => () => null);
jest.mock('../HighlightTooltip', () => () => null);

describe('SpecViewer custom item types integration', () => {
  const {
    getSpecCentricData,
    getSpecSectionContent,
    getCustomItemTypes,
  } = require('../../api/SpecCentricView/api');

  beforeEach(() => {
    jest.clearAllMocks();

    getSpecCentricData.mockResolvedValue({
      data: {
        spec_sections: [
          {
            id: 1,
            masterformat_number: '01',
            masterformat_title: 'General Requirements',
            document_name: 'Spec.pdf',
            pdf_url: 'https://example.com/spec.pdf',
            document_id: 'doc-1',
          },
        ],
      },
    });

    getSpecSectionContent.mockResolvedValue({
      data: {
        submittal_highlights: [],
        ai_log_highlights: [],
      },
    });

    getCustomItemTypes.mockResolvedValue({
      data: {
        results: [
          { id: 77, name: 'Safety', color: '#FF0000' },
        ],
      },
    });
  });

  it('loads custom item types and passes them to children', async () => {
    render(<SpecViewer projectId={42} projectVersionId={5} />);

    await waitFor(() => {
      expect(getSpecCentricData).toHaveBeenCalledWith(42, 5);
    });

    await waitFor(() => {
      expect(getCustomItemTypes).toHaveBeenCalledWith(42);
    });

    await waitFor(() => {
      expect(mockDocumentHighlighter).toHaveBeenCalled();
    });

    const highlighterProps = mockDocumentHighlighter.mock.calls[mockDocumentHighlighter.mock.calls.length - 1][0];
    expect(highlighterProps.customItemTypes).toEqual([{ id: 77, name: 'Safety', color: '#FF0000' }]);
    expect(typeof highlighterProps.onCustomTypesUpdate).toBe('function');

    const legendProps = mockHighlightLegend.mock.calls[mockHighlightLegend.mock.calls.length - 1][0];
    expect(legendProps.customItemTypes).toEqual([{ id: 77, name: 'Safety', color: '#FF0000' }]);
  });
});
import React from 'react';
import { render, waitFor } from '@testing-library/react';
import SpecViewer from '../SpecViewer';

jest.mock('../../api/SpecCentricView/api', () => ({
  getSpecCentricData: jest.fn(),
  getSpecSectionContent: jest.fn(),
  getCustomItemTypes: jest.fn(),
}));

const mockDocumentHighlighter = jest.fn(() => null);
const mockHighlightLegend = jest.fn(() => null);

jest.mock('../DocumentHighlighter', () => (props) => mockDocumentHighlighter(props));
jest.mock('../HighlightLegend', () => (props) => mockHighlightLegend(props));
jest.mock('../SpecViewerSidebar', () => () => null);
jest.mock('../HighlightTooltip', () => () => null);

describe('SpecViewer custom item types integration', () => {
  const {
    getSpecCentricData,
    getSpecSectionContent,
    getCustomItemTypes,
  } = require('../../api/SpecCentricView/api');

  beforeEach(() => {
    jest.clearAllMocks();

    getSpecCentricData.mockResolvedValue({
      data: {
        spec_sections: [
          {
            id: 1,
            masterformat_number: '01',
            masterformat_title: 'General Requirements',
            document_name: 'Spec.pdf',
            pdf_url: 'https://example.com/spec.pdf',
            document_id: 'doc-1',
          },
        ],
      },
    });

    getSpecSectionContent.mockResolvedValue({
      data: {
        submittal_highlights: [],
        ai_log_highlights: [],
      },
    });

    getCustomItemTypes.mockResolvedValue({
      data: {
        results: [
          { id: 77, name: 'Safety', color: '#FF0000' },
        ],
      },
    });
  });

  it('loads custom item types and passes them to children', async () => {
    render(<SpecViewer projectId={42} projectVersionId={5} />);

    await waitFor(() => {
      expect(getSpecCentricData).toHaveBeenCalledWith(42, 5);
    });

    await waitFor(() => {
      expect(getCustomItemTypes).toHaveBeenCalledWith(42);
    });

    await waitFor(() => {
      expect(mockDocumentHighlighter).toHaveBeenCalled();
    });

    const highlighterProps = mockDocumentHighlighter.mock.calls[mockDocumentHighlighter.mock.calls.length - 1][0];
    expect(highlighterProps.customItemTypes).toEqual([{ id: 77, name: 'Safety', color: '#FF0000' }]);
    expect(typeof highlighterProps.onCustomTypesUpdate).toBe('function');

    const legendProps = mockHighlightLegend.mock.calls[mockHighlightLegend.mock.calls.length - 1][0];
    expect(legendProps.customItemTypes).toEqual([{ id: 77, name: 'Safety', color: '#FF0000' }]);
  });
});

