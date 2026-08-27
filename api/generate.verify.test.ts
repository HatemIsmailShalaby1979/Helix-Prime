// Verification script for /api/generate endpoint
// Tests the core logic without requiring a running server

import { loadWFMData, generateSampleClientData } from './generate';
import * as fs from 'fs';
import * as path from 'path';

// Mock the file system for testing
jest.mock('fs');

describe('Data loading functions', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('loadWFMData', () => {
    it('should return parsed JSON when file exists', async () => {
      const mockData = { test: 'data' };
      (fs.readFileSync as jest.Mock).mockReturnValue(JSON.stringify(mockData));

      const result = await loadWFMData();
      expect(result).toEqual(mockData);
      expect(fs.readFileSync).toHaveBeenCalledWith(
        expect.stringContaining('results_20260717_163732.json'),
        'utf8'
      );
    });

    it('should return null when file read fails', async () => {
      (fs.readFileSync as jest.Mock).mockImplementation(() => {
        throw new Error('File not found');
      });

      const result = await loadWFMData();
      expect(result).toBeNull();
    });
  });

  describe('generateSampleClientData', () => {
    it('should generate correct structure for clientA', () => {
      const data = generateSampleClientData('clientA');
      expect(data).toHaveProperty('clientId', 'clientA');
      expect(data).toHaveProperty('dataType', 'sample');
      expect(data.main_forecast.optimal_agents).toBe(2);
      expect(data.main_forecast.service_level_achieved).toBe(0.85);
      expect(data._metadata.note).toContain('sample/mock data');
    });

    it('should generate correct structure for clientB', () => {
      const data = generateSampleClientData('clientB');
      expect(data).toHaveProperty('clientId', 'clientB');
      expect(data).toHaveProperty('dataType', 'sample');
      expect(data.main_forecast.optimal_agents).toBe(5);
      expect(data.main_forecast.service_level_achieved).toBe(0.92);
      expect(data._metadata.note).toContain('sample/mock data');
    });

    it('should generate base structure for default/unknown client', () => {
      const data = generateSampleClientData('default');
      expect(data).toHaveProperty('clientId', 'default');
      expect(data).toHaveProperty('dataType', 'sample');
      expect(data.main_forecast.optimal_agents).toBe(0); // base value
      expect(data._metadata.note).toContain('sample/mock data');
    });
  });
});

// Integration test to check if WFM data file exists
describe('WFM Data File Integration', () => {
  it('should exist and be valid JSON', () => {
    const dataPath = path.join(process.cwd(), 'engines', 'wfm', 'src', 'output', 'results_20260717_163732.json');

    // Skip if file doesn't exist in test environment
    if (!fs.existsSync(dataPath)) {
      console.warn('WFM data file not found - skipping integration test');
      return;
    }

    expect(fs.existsSync(dataPath)).toBe(true);

    let data;
    expect(() => {
      data = fs.readFileSync(dataPath, 'utf8');
    }).not.toThrow();

    expect(() => {
      JSON.parse(data);
    }).not.toThrow();

    const parsed = JSON.parse(data);
    expect(parsed).toHaveProperty('main_forecast');
    expect(parsed.main_forecast).toHaveProperty('optimal_agents');
    expect(typeof parsed.main_forecast.optimal_agents).toBe('number');
  });
});

console.log('Verification script loaded - run with: npx vitest api/generate.verify.test.ts');
// Export functions for potential use in other tests
export { loadWFMData, generateSampleClientData };
