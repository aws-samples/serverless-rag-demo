import config from '../config.json';

interface Model {
    label: string;
    value: string;
}

export function transformModelValue(value: string): string {
    const region = config.region;
    
    // If region starts with 'ap-', replace 'us.' with 'apac.'
    if (region.startsWith('ap-')) {
        return value.replace('us.', 'apac.');
    }
    
    // If region starts with 'eu-', replace 'us.' with 'eu.'
    if (region.startsWith('eu-')) {
        return value.replace('us.', 'eu.');
    }
    
    // For us- regions, keep the original value
    return value;
}

export function transformModels(models: any[]): Model[] {
    return models.map(model => ({
        label: model.label,
        value: transformModelValue(model.value)
    }));
} 