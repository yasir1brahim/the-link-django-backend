import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import CustomItemTypesManager from '../CustomItemTypesManager';

jest.mock('../../../../api/SpecCentricView/api', () => ({
  getCustomItemTypes: jest.fn(),
  createCustomItemType: jest.fn(),
  updateCustomItemType: jest.fn(),
  deleteCustomItemType: jest.fn(),
  getCustomTypeColorPalette: jest.fn(),
}));

jest.mock('react-toastify', () => ({
  toast: {
    success: jest.fn(),
    error: jest.fn(),
    warning: jest.fn(),
  },
}));

const {
  getCustomItemTypes,
  createCustomItemType,
  updateCustomItemType,
  deleteCustomItemType,
  getCustomTypeColorPalette,
} = require('../../../../api/SpecCentricView/api');

const { toast } = require('react-toastify');

const PROJECT_ID = 55;

const renderManager = (props = {}) =>
  render(
    <CustomItemTypesManager
      projectId={PROJECT_ID}
      isOpen={true}
      onClose={jest.fn()}
      onRefresh={jest.fn()}
      initialTypes={[]}
      {...props}
    />
  );

describe('CustomItemTypesManager', () => {
  beforeEach(() => {
    jest.clearAllMocks();

    getCustomItemTypes.mockResolvedValue({
      data: {
        results: [
          { id: 77, name: 'Safety', color: '#FF0000' },
        ],
      },
    });

    getCustomTypeColorPalette.mockResolvedValue({
      data: {
        colors: ['#FF0000', '#00FF00'],
      },
    });

    createCustomItemType.mockResolvedValue({
      data: { id: 88, name: 'Commissioning', color: '#00FF00' },
    });

    updateCustomItemType.mockResolvedValue({
      data: { id: 77, name: 'Safety Updated', color: '#00FF00' },
    });

    deleteCustomItemType.mockResolvedValue({});
  });

  it('fetches custom types and color palette when opened', async () => {
    renderManager();

    await waitFor(() => {
      expect(getCustomItemTypes).toHaveBeenCalledWith(PROJECT_ID);
      expect(getCustomTypeColorPalette).toHaveBeenCalledWith(PROJECT_ID);
    });

    expect(await screen.findByDisplayValue('Safety')).toBeInTheDocument();
  });

  it('allows creating a new custom type', async () => {
    const onRefresh = jest.fn();
    renderManager({ onRefresh });

    fireEvent.change(await screen.findByLabelText(/new type name/i), {
      target: { value: 'Commissioning' },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Select color #00FF00' }));

    fireEvent.click(screen.getByRole('button', { name: /add type/i }));

    await waitFor(() => {
      expect(createCustomItemType).toHaveBeenCalledWith(PROJECT_ID, {
        name: 'Commissioning',
        color: '#00FF00',
      });
    });

    expect(onRefresh).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalled();
  });

  it('allows updating an existing custom type', async () => {
    const onRefresh = jest.fn();
    renderManager({ onRefresh });

    const nameInput = await screen.findByLabelText(/name for Safety/i);
    fireEvent.change(nameInput, { target: { value: 'Safety Updated' } });

    fireEvent.click(screen.getAllByRole('button', { name: /select color/i })[1]);

    fireEvent.click(screen.getByRole('button', { name: /save safety/i }));

    await waitFor(() => {
      expect(updateCustomItemType).toHaveBeenCalledWith(PROJECT_ID, 77, {
        name: 'Safety Updated',
        color: '#00FF00',
      });
    });

    expect(onRefresh).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalled();
  });

  it('allows deleting an existing custom type', async () => {
    const onRefresh = jest.fn();
    renderManager({ onRefresh });

    fireEvent.click(await screen.findByRole('button', { name: /delete safety/i }));

    await waitFor(() => {
      expect(deleteCustomItemType).toHaveBeenCalledWith(PROJECT_ID, 77);
    });

    expect(onRefresh).toHaveBeenCalled();
    expect(toast.success).toHaveBeenCalled();
  });
});

