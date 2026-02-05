import React, { useEffect, useMemo, useState, useCallback } from 'react';
import {
  getCustomItemTypes,
  createCustomItemType,
  updateCustomItemType,
  deleteCustomItemType,
  getCustomTypeColorPalette,
} from '../../../api/SpecCentricView/api';
import { toast } from 'react-toastify';
import './CustomItemTypesManager.css';

const DEFAULT_PALETTE = [
  '#FF6B6B',
  '#FF922B',
  '#F7B801',
  '#6BCB77',
  '#4D96FF',
  '#9C89B8',
  '#4ECDC4',
  '#F38BA0',
];

const derivePalette = (serverPalette) => {
  if (!Array.isArray(serverPalette) || serverPalette.length === 0) {
    return DEFAULT_PALETTE;
  }

  return serverPalette;
};

const buildInitialTypeState = (types) =>
  (types || []).map((item) => ({
    id: item.id,
    name: item.name || '',
    color: item.color || DEFAULT_PALETTE[0],
    isPersisted: true,
  }));

const CustomItemTypesManager = ({
  projectId,
  isOpen,
  onClose,
  onRefresh,
  initialTypes = [],
}) => {
  const [isLoading, setIsLoading] = useState(false);
  const [types, setTypes] = useState(() => buildInitialTypeState(initialTypes));
  const [palette, setPalette] = useState(DEFAULT_PALETTE);
  const [newTypeName, setNewTypeName] = useState('');
  const [newTypeColor, setNewTypeColor] = useState(DEFAULT_PALETTE[0]);
  const [savingTypeId, setSavingTypeId] = useState(null);
  const [isCreating, setIsCreating] = useState(false);

  useEffect(() => {
    setTypes(buildInitialTypeState(initialTypes));
  }, [initialTypes]);

  const loadManagerData = useCallback(async () => {
    if (!projectId) {
      return;
    }

    setIsLoading(true);
    try {
      const [typesResponse, paletteResponse] = await Promise.all([
        getCustomItemTypes(projectId),
        getCustomTypeColorPalette(projectId),
      ]);

      setTypes(buildInitialTypeState(typesResponse?.data?.results || []));
      setPalette(derivePalette(paletteResponse?.data?.colors));
      setNewTypeColor((paletteResponse?.data?.colors && paletteResponse.data.colors[0]) || DEFAULT_PALETTE[0]);
    } catch (error) {
      console.error('Failed to load custom item types', error);
      toast.error('Unable to load custom highlight types. Please try again.');
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    if (isOpen) {
      loadManagerData();
    }
  }, [isOpen, loadManagerData]);

  const sortedTypes = useMemo(
    () => [...types].sort((a, b) => a.name.localeCompare(b.name)),
    [types]
  );

  const handleCreate = async (event) => {
    event.preventDefault();

    if (!newTypeName.trim()) {
      toast.warning('Please provide a name for the custom type.');
      return;
    }

    if (!newTypeColor) {
      toast.warning('Please select a color for the custom type.');
      return;
    }

    try {
      setIsCreating(true);
      const payload = {
        name: newTypeName.trim(),
        color: newTypeColor,
      };
      const response = await createCustomItemType(projectId, payload);
      const created = response?.data || payload;

      setTypes((previous) => [
        ...previous,
        {
          id: created.id,
          name: created.name,
          color: created.color,
          isPersisted: true,
        },
      ]);
      setNewTypeName('');
      toast.success('Custom highlight type created.');
      onRefresh?.();
    } catch (error) {
      console.error('Failed to create custom type', error);
      toast.error('Unable to create custom highlight type.');
    } finally {
      setIsCreating(false);
    }
  };

  const handleTypeNameChange = (id, name) => {
    setTypes((previous) =>
      previous.map((item) =>
        item.id === id
          ? {
              ...item,
              name,
            }
          : item
      )
    );
  };

  const handleTypeColorChange = (id, color) => {
    setTypes((previous) =>
      previous.map((item) =>
        item.id === id
          ? {
              ...item,
              color,
            }
          : item
      )
    );
  };

  const handleSaveType = async (type) => {
    if (!projectId || !type?.id) {
      return;
    }

    try {
      setSavingTypeId(type.id);
      const payload = {
        name: type.name.trim(),
        color: type.color,
      };
      await updateCustomItemType(projectId, type.id, payload);
      toast.success('Custom highlight type updated.');
      onRefresh?.();
    } catch (error) {
      console.error('Failed to update custom type', error);
      toast.error('Unable to update custom highlight type.');
    } finally {
      setSavingTypeId(null);
    }
  };

  const handleDeleteType = async (typeId) => {
    if (!projectId || !typeId) {
      return;
    }

    try {
      setSavingTypeId(typeId);
      await deleteCustomItemType(projectId, typeId);
      setTypes((previous) => previous.filter((item) => item.id !== typeId));
      toast.success('Custom highlight type removed.');
      onRefresh?.();
    } catch (error) {
      console.error('Failed to delete custom type', error);
      toast.error('Unable to delete custom highlight type.');
    } finally {
      setSavingTypeId(null);
    }
  };

  if (!isOpen) {
    return null;
  }

  return (
    <div className="highlight-picker-overlay custom-types-manager-overlay">
      <div className="highlight-picker-modal custom-types-manager-modal">
        <div className="custom-types-manager-header">
          <h3>Manage Custom Highlight Types</h3>
          <button type="button" className="custom-types-close" onClick={onClose}>
            ✕
          </button>
        </div>

        {isLoading ? (
          <div className="custom-types-loading">Loading custom types…</div>
        ) : (
          <>
            <form className="custom-types-create-form" onSubmit={handleCreate}>
              <label className="custom-types-label" htmlFor="custom-type-name">
                New Type Name
              </label>
              <input
                id="custom-type-name"
                aria-label="New type name"
                className="custom-types-input"
                type="text"
                value={newTypeName}
                onChange={(event) => setNewTypeName(event.target.value)}
                placeholder="Enter a label"
              />

              <div className="custom-types-palette">
                {palette.map((color) => (
                  <button
                    key={color}
                    type="button"
                    className={`custom-types-color ${newTypeColor === color ? 'selected' : ''}`}
                    style={{ backgroundColor: color }}
                    onClick={() => setNewTypeColor(color)}
                    aria-label={`Select color ${color}`}
                  />
                ))}
              </div>

              <button
                type="submit"
                className="custom-types-primary"
                disabled={isCreating}
              >
                Add Type
              </button>
            </form>

            <div className="custom-types-list">
              {sortedTypes.length === 0 ? (
                <p className="custom-types-empty">No custom types have been created yet.</p>
              ) : (
                sortedTypes.map((type) => (
                  <div key={type.id} className="custom-types-row">
                    <div className="custom-types-row-main">
                      <label
                        className="custom-types-label"
                        htmlFor={`custom-type-name-${type.id}`}
                      >
                        Name for {type.name || 'custom type'}
                      </label>
                      <input
                        id={`custom-type-name-${type.id}`}
                        aria-label={`Name for ${type.name || 'custom type'}`}
                        className="custom-types-input"
                        type="text"
                        value={type.name}
                        onChange={(event) =>
                          handleTypeNameChange(type.id, event.target.value)
                        }
                      />
                    </div>

                    <div className="custom-types-row-controls">
                      <div className="custom-types-palette">
                        {palette.map((color) => (
                          <button
                            key={`${type.id}-${color}`}
                            type="button"
                            className={`custom-types-color ${type.color === color ? 'selected' : ''}`}
                            style={{ backgroundColor: color }}
                            onClick={() => handleTypeColorChange(type.id, color)}
                            aria-label={`Select color ${color}`}
                          />
                        ))}
                      </div>

                      <div className="custom-types-actions">
                        <button
                          type="button"
                          className="custom-types-secondary"
                          onClick={() => handleSaveType(type)}
                          disabled={savingTypeId === type.id}
                        >
                          Save {type.name || 'type'}
                        </button>
                        <button
                          type="button"
                          className="custom-types-danger"
                          onClick={() => handleDeleteType(type.id)}
                          disabled={savingTypeId === type.id}
                          aria-label={`Delete ${type.name || 'custom type'}`}
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
};

export default CustomItemTypesManager;

