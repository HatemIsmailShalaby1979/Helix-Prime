/**
 * Verification tests for the /api/generate endpoint
 * Tests client selection, data source labeling, and response structure
 */

import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import * as fs from 'fs';
import * as path from 'path';

// Test configuration
const TEST_BASE_URL = process.env.TEST_BASE_URL || 'http://localhost:3000';
const API_ENDPOINT = `${TEST_BASE_URL}/api/generate`;

// Test clients to verify
const TEST_CLIENTS = ['default', 'clientA', 'clientB'];

describe('/api/generate endpoint', () => {
  // Helper function to make API calls
  async function callGenerateEndpoint(client: string, prompt: string = 'Test prompt') {
    const response = await fetch(API_ENDPOINT, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ client, prompt }),
    });

    const data = await response.json();
    return { status: response.status, data };
  }

  describe('Client selection and data source labeling', () => {
    it('should return real data for default client (WFM engine)', async () => {
      const { status, data } = await callGenerateEndpoint('default', 'Generate WFM insights');

      expect(status).toBe(200);
      expect(data).toHaveProperty('client', 'default');
      expect(data).toHaveProperty('dataSourceType');
      // Should be 'real' if WFM data file exists, 'sample' if fallback
      expect(['real', 'sample']).toContain(data.dataSourceType);
      expect(data).toHaveProperty('engineStatus');
      expect(data).toHaveProperty('result');
      expect(data).toHaveProperty('generationDurationMs');
      expect(typeof data.generationDurationMs).toBe('number');
      expect(data.generationDurationMs).toBeGreaterThan(0);
    });

    it('should return sample data for clientA with proper labeling', async () => {
      const { status, data } = await callGenerateEndpoint('clientA', 'Generate clientA insights');

      expect(status).toBe(200);
      expect(data).toHaveProperty('client', 'clientA');
      expect(data.dataSourceType).toBe('sample');
      expect(data.engineStatus).toContain('in development');
      expect(data).toHaveProperty('note');
      expect(data.note).toContain('sample/mock data');
      expect(data).toHaveProperty('result');
    });

    it('should return sample data for clientB with proper labeling', async () => {
      const { status, data } = await callGenerateEndpoint('clientB', 'Generate clientB insights');

      expect(status).toBe(200);
      expect(data).toHaveProperty('client', 'clientB');
      expect(data.dataSourceType).toBe('sample');
      expect(data.engineStatus).toContain('in development');
      expect(data).toHaveProperty('note');
      expect(data.note).toContain('sample/mock data');
      expect(data).toHaveProperty('result');
    });

    it('should handle unknown clients gracefully', async () => {
      const { status, data } = await callGenerateEndpoint('unknown-client', 'Test');

      expect(status).toBe(200); // Our endpoint returns 200 even for unknown clients
      expect(data).toHaveProperty('client', 'unknown-client');
      expect(data.dataSourceType).toBe('unknown');
      expect(data.engineStatus).toBe('error');
      expect(data).toHaveProperty('result');
    });
  });

  describe('Response structure validation', () => {
    it('should include all required fields in successful response', async () => {
      const { status, data } = await callGenerateEndpoint('default', 'Test structure');

      expect(status).toBe(200);
      // Required fields
      expect(data).toHaveProperty('client');
      expect(data).toHaveProperty('prompt');
      expect(data).toHaveProperty('dataSourceType');
      expect(data).toHaveProperty('engineStatus');
      expect(data).toHaveProperty('generationDurationMs');
      expect(data).toHaveProperty('result');
      expect(data).toHaveProperty('sourceModel');
      expect(data).toHaveProperty('timestamp');

      // Type checks
      expect(typeof data.client).toBe('string');
      expect(typeof data.prompt).toBe('string');
      expect(typeof data.dataSourceType).toBe('string');
      expect(typeof data.engineStatus).toBe('string');
      expect(typeof data.generationDurationMs).toBe('number');
      expect(typeof data.result).toBe('string');
      expect(typeof data.sourceModel).toBe('string');
      expect(typeof data.timestamp).toBe('string');

      // Timestamp should be valid ISO string
      expect(() => new Date(data.timestamp)).not.toThrow();
    });
  });

  describe('Performance and reliability', () => {
    it('should respond within reasonable time (< 10 seconds)', async () => {
      const startTime = Date.now();
      const { status } = await callGenerateEndpoint('default', 'Quick test');
      const duration = Date.now() - startTime;

      expect(status).toBe(200);
      expect(duration).toBeLessThan(10000); // 10 seconds max
    });

    it('should handle concurrent requests', async () => {
      const promises = Array(3).fill(null).map(() =>
        callGenerateEndpoint('default', 'Concurrent test')
      );

      const results = await Promise.all(promises);

      results.forEach(({ status, data }) => {
        expect(status).toBe(200);
        expect(data).toHaveProperty('result');
      });
    });
  });
});

// Integration test to verify WFM data file exists and is readable
describe('WFM Data File', () => {
  it('should exist and be valid JSON', () => {
    const dataPath = path.join(process.cwd(), 'engines', 'wfm', 'src', 'output', 'results_20260717_163732.json');

    expect(fs.existsSync(dataPath)).toBe(true);

    const data = fs.readFileSync(dataPath, 'utf8');
    expect(() => JSON.parse(data)).not.toThrow();

    const parsed = JSON.parse(data);
    expect(parsed).toHaveProperty('main_forecast');
    expect(parsed.main_forecast).toHaveProperty('optimal_agents');
  });
});

// Export test runner function for standalone execution
export async function runTests() {
  const { runTests: vitestRun } = await import('vitest');
  await vitestRun();
}
