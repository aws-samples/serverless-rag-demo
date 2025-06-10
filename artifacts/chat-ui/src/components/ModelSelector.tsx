import React from 'react';
import { Select } from '@cloudscape-design/components';
import { transformModels } from '../utils/modelRegionTransformer';
import defaultConfig from '../default-properties.json';

interface Model {
    label: string;
    value: string;
}

interface ModelSelectorProps {
    onModelSelect: (model: Model) => void;
    selectedModel?: Model;
}

export const ModelSelector: React.FC<ModelSelectorProps> = ({ onModelSelect, selectedModel }) => {
    const models = transformModels(defaultConfig["document-chat"]["config"]["models"]);

    return (
        <Select
            selectedOption={selectedModel}
            onChange={({ detail }) => onModelSelect(detail.selectedOption as Model)}
            options={models}
            expandToViewport
            triggerVariant="option"
        />
    );
}; 