import axiosInstance from '../../../config/axios';
import handleError from '../../../config/errorHandler';
import {
  getCustomItemTypes,
  createCustomItemType,
  updateCustomItemType,
  deleteCustomItemType,
  getCustomTypeColorPalette,
} from '../api';

jest.mock('../../../config/axios', () => jest.fn());
jest.mock('../../../config/errorHandler', () => jest.fn());

const PROJECT_ID = 42;
const TYPE_ID = 7;
const PAYLOAD = { name: 'Custom Type', color: '#123456' };

describe('SpecCentricView custom item type API helpers', () => {
  beforeEach(() => {
    axiosInstance.mockReset();
    handleError.mockReset();
  });

  it.each([
    [
      'getCustomItemTypes',
      () => getCustomItemTypes(PROJECT_ID),
      {
        method: 'get',
        url: `/api/deliverables/projects/${PROJECT_ID}/custom-item-types/`,
      },
    ],
    [
      'createCustomItemType',
      () => createCustomItemType(PROJECT_ID, PAYLOAD),
      {
        method: 'post',
        url: `/api/deliverables/projects/${PROJECT_ID}/custom-item-types/`,
        data: PAYLOAD,
      },
    ],
    [
      'updateCustomItemType',
      () => updateCustomItemType(PROJECT_ID, TYPE_ID, PAYLOAD),
      {
        method: 'patch',
        url: `/api/deliverables/projects/${PROJECT_ID}/custom-item-types/${TYPE_ID}/`,
        data: PAYLOAD,
      },
    ],
    [
      'deleteCustomItemType',
      () => deleteCustomItemType(PROJECT_ID, TYPE_ID),
      {
        method: 'delete',
        url: `/api/deliverables/projects/${PROJECT_ID}/custom-item-types/${TYPE_ID}/`,
      },
    ],
    [
      'getCustomTypeColorPalette',
      () => getCustomTypeColorPalette(PROJECT_ID),
      {
        method: 'get',
        url: `/api/deliverables/projects/${PROJECT_ID}/custom-item-types/color-palette/`,
      },
    ],
  ])('%s delegates to axiosInstance with the expected configuration', async (_, invoke, expectedConfig) => {
    const mockedResponse = { data: { results: [] } };
    axiosInstance.mockResolvedValue(mockedResponse);

    await expect(invoke()).resolves.toBe(mockedResponse);

    expect(axiosInstance).toHaveBeenCalledTimes(1);
    expect(axiosInstance).toHaveBeenCalledWith(expectedConfig);
    expect(handleError).not.toHaveBeenCalled();
  });

  it('routes errors through handleError and rethrows', async () => {
    const error = new Error('network down');
    axiosInstance.mockRejectedValue(error);

    await expect(getCustomItemTypes(PROJECT_ID)).rejects.toThrow(error);
    expect(handleError).toHaveBeenCalledWith(error);
  });
});
import axiosInstance from '../../../config/axios';
import handleError from '../../../config/errorHandler';
import {
  getCustomItemTypes,
  createCustomItemType,
  updateCustomItemType,
  deleteCustomItemType,
  getCustomTypeColorPalette,
} from '../api';

jest.mock('../../../config/axios', () => jest.fn());
jest.mock('../../../config/errorHandler', () => jest.fn());

const PROJECT_ID = 42;
const TYPE_ID = 7;
const PAYLOAD = { name: 'Custom Type', color: '#123456' };

describe('SpecCentricView custom item type API helpers', () => {
  beforeEach(() => {
    axiosInstance.mockReset();
    handleError.mockReset();
  });

  it.each([
    [
      'getCustomItemTypes',
      () => getCustomItemTypes(PROJECT_ID),
      {
        method: 'get',
        url: `/api/deliverables/projects/${PROJECT_ID}/custom-item-types/`,
      },
    ],
    [
      'createCustomItemType',
      () => createCustomItemType(PROJECT_ID, PAYLOAD),
      {
        method: 'post',
        url: `/api/deliverables/projects/${PROJECT_ID}/custom-item-types/`,
        data: PAYLOAD,
      },
    ],
    [
      'updateCustomItemType',
      () => updateCustomItemType(PROJECT_ID, TYPE_ID, PAYLOAD),
      {
        method: 'patch',
        url: `/api/deliverables/projects/${PROJECT_ID}/custom-item-types/${TYPE_ID}/`,
        data: PAYLOAD,
      },
    ],
    [
      'deleteCustomItemType',
      () => deleteCustomItemType(PROJECT_ID, TYPE_ID),
      {
        method: 'delete',
        url: `/api/deliverables/projects/${PROJECT_ID}/custom-item-types/${TYPE_ID}/`,
      },
    ],
    [
      'getCustomTypeColorPalette',
      () => getCustomTypeColorPalette(PROJECT_ID),
      {
        method: 'get',
        url: `/api/deliverables/projects/${PROJECT_ID}/custom-item-types/color-palette/`,
      },
    ],
  ])('%s delegates to axiosInstance with the expected configuration', async (_, invoke, expectedConfig) => {
    const mockedResponse = { data: { results: [] } };
    axiosInstance.mockResolvedValue(mockedResponse);

    await expect(invoke()).resolves.toBe(mockedResponse);

    expect(axiosInstance).toHaveBeenCalledTimes(1);
    expect(axiosInstance).toHaveBeenCalledWith(expectedConfig);
    expect(handleError).not.toHaveBeenCalled();
  });

  it('routes errors through handleError and rethrows', async () => {
    const error = new Error('network down');
    axiosInstance.mockRejectedValue(error);

    await expect(getCustomItemTypes(PROJECT_ID)).rejects.toThrow(error);
    expect(handleError).toHaveBeenCalledWith(error);
  });
});

