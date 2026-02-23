import { type PresetConfig, PresetConfigSchema } from '../types/index.js';
import { BranchNexusError, ExitCode } from '../types/errors.js';
import { loadConfig, saveConfig } from './config.js';

export const TERMINAL_TEMPLATE_CATALOG = [2, 4, 6, 8, 12, 16] as const;
export const TERMINAL_TEMPLATE_MIN = 2;
export const TERMINAL_TEMPLATE_MAX = 16;
export const TERMINAL_TEMPLATE_CUSTOM = 'custom';

export function terminalTemplateChoices(): string[] {
  return [...TERMINAL_TEMPLATE_CATALOG.map(String), TERMINAL_TEMPLATE_CUSTOM];
}

export function validateTerminalCount(value: number): number {
  if (value < TERMINAL_TEMPLATE_MIN || value > TERMINAL_TEMPLATE_MAX) {
    throw new BranchNexusError(
      `Invalid terminal count: ${value}`,
      ExitCode.VALIDATION_ERROR,
      `Use a value between ${TERMINAL_TEMPLATE_MIN} and ${TERMINAL_TEMPLATE_MAX}.`
    );
  }
  return value;
}

export function resolveTerminalTemplate(template: string | number, customValue?: number): number {
  if (typeof template === 'number') {
    return validateTerminalCount(template);
  }

  const normalized = template.trim().toLowerCase();

  if (normalized === TERMINAL_TEMPLATE_CUSTOM) {
    if (customValue === undefined) {
      throw new BranchNexusError(
        'Custom template requires an explicit terminal count.',
        ExitCode.VALIDATION_ERROR,
        `Provide --max-terminals between ${TERMINAL_TEMPLATE_MIN} and ${TERMINAL_TEMPLATE_MAX}.`
      );
    }
    return validateTerminalCount(customValue);
  }

  if (/^\d+$/.test(normalized)) {
    return validateTerminalCount(parseInt(normalized, 10));
  }

  throw new BranchNexusError(
    `Invalid terminal template: ${template}`,
    ExitCode.VALIDATION_ERROR,
    `Use one of: ${terminalTemplateChoices().join(', ')}.`
  );
}

export function savePreset(name: string, preset: PresetConfig): void {
  const validated = PresetConfigSchema.parse(preset);
  const config = loadConfig();
  config.presets[name] = validated;
  saveConfig(config);
}

export function loadPresets(): Record<string, PresetConfig> {
  const config = loadConfig();
  return { ...config.presets };
}

export function applyPreset(name: string): PresetConfig {
  const presets = loadPresets();
  const preset = presets[name] as PresetConfig | undefined;
  if (preset === undefined) {
    throw new BranchNexusError(
      `Preset not found: ${name}`,
      ExitCode.VALIDATION_ERROR,
      'Select an existing preset or create a new one.'
    );
  }
  return preset;
}

export function deletePreset(name: string): void {
  const config = loadConfig();
  delete config.presets[name];
  saveConfig(config);
}

export function renamePreset(oldName: string, newName: string): void {
  const config = loadConfig();
  const preset = config.presets[oldName] as PresetConfig | undefined;
  if (preset === undefined) {
    throw new BranchNexusError(
      `Preset not found: ${oldName}`,
      ExitCode.VALIDATION_ERROR,
      'Choose an existing preset to rename.'
    );
  }
  config.presets[newName] = preset;
  delete config.presets[oldName];
  saveConfig(config);
}

export function presetExists(name: string): boolean {
  const config = loadConfig();
  return name in config.presets;
}

export function createPresetFromCurrentConfig(name: string): PresetConfig {
  const config = loadConfig();
  const preset: PresetConfig = {
    layout: config.defaultLayout,
    panes: config.defaultPanes,
    cleanup: config.cleanupPolicy,
  };
  savePreset(name, preset);
  return preset;
}
