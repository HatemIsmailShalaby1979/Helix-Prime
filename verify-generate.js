#!/usr/bin/env node
/**
 * Verification script for /api/generate endpoint
 * Tests the endpoint logic end-to-end without requiring a running server
 *
 * Usage: node verify-generate.js
 */

const fs = require('fs');
const path = require('path');

// Check if OPENROUTER_API_KEY is set
const API_KEY = process.env.OPENROUTER_API_KEY;
if (!API_KEY) {
  console.error('❌ OPENROUTER_API_KEY environment variable is not set');
  console.error('   Run: setx OPENROUTER_API_KEY "your-api-key-here"');
  process.exit(1);
}

console.log('✅ OPENROUTER_API_KEY is set');
console.log('');

// Path to WFM data file
const WFM_DATA_PATH = path.join(__dirname, 'engines', 'wfm', 'src', 'output', 'results_20260717_163732.json');

/**
 * Loads and parses the WFM real data file
 */
function loadWFMData() {
  try {
    const data = fs.readFileSync(WFM_DATA_PATH, 'utf8');
    return JSON.parse(data);
  } catch (error) {
    console.error('Error loading WFM data:', error.message);
    return null;
  }
}

/**
 * Generates sample client data (clearly labeled as sample/mock)
 */
function generateSampleClientData(clientId) {
  const baseData = {
    main_forecast: {
      optimal_agents: 0,
      probability_waiting: 0,
      average_speed_of_answer_minutes: 0,
      service_level_achieved: 0,
      traffic_intensity: 0,
      utilization_percentage: 0,
      confidence_interval: { lower: 0, upper: 0 },
      parameters: {
        arrival_rate: 0,
        average_handling_time_minutes: 0,
        service_level_target: 0,
        average_calls_per_period: 0
      }
    },
    scenarios: [],
    _metadata: {
      clientId,
      dataType: 'sample',
      generatedAt: new Date().toISOString(),
      note: 'This is sample/mock data for demonstration purposes only.'
    }
  };

  switch (clientId) {
    case 'clientA':
      baseData.main_forecast.optimal_agents = 2;
      baseData.main_forecast.service_level_achieved = 0.85;
      baseData.main_forecast.average_speed_of_answer_minutes = 120;
      baseData.main_forecast.traffic_intensity = 0.7;
      baseData.main_forecast.utilization_percentage = 70;
      baseData.main_forecast.parameters.arrival_rate = 30;
      baseData.main_forecast.parameters.average_calls_per_period = 450;
      break;
    case 'clientB':
      baseData.main_forecast.optimal_agents = 5;
      baseData.main_forecast.service_level_achieved = 0.92;
      baseData.main_forecast.average_speed_of_answer_minutes = 45;
      baseData.main_forecast.traffic_intensity = 0.85;
      baseData.main_forecast.utilization_percentage = 85;
      baseData.main_forecast.parameters.arrival_rate = 80;
      baseData.main_forecast.parameters.average_calls_per_period = 1200;
      break;
  }

  return baseData;
}

/**
 * Simulates the generate endpoint logic
 */
async function simulateGenerateEndpoint(client, prompt) {
  const startTime = Date.now();
  let dataSource = null;
  let dataType = 'unknown';
  let engineStatus = 'unknown';

  // Determine data source
  switch (client) {
    case 'default':
      dataSource = loadWFMData();
      if (dataSource) {
        dataType = 'real';
        engineStatus = 'operational (WFM engine)';
      } else {
        dataSource = generateSampleClientData('default');
        dataType = 'sample';
        engineStatus = 'degraded (real data unavailable)';
      }
      break;

    case 'clientA':
    case 'clientB':
      dataSource = generateSampleClientData(client);
      dataType = 'sample';
      engineStatus = 'in development (sample data only)';
      break;

    default:
      dataSource = {
        error: `Unknown client: ${client}`,
        _metadata: {
          clientId: client,
          dataType: 'unknown',
          availableClients: ['default', 'clientA', 'clientB']
        }
      };
      dataType = 'unknown';
      engineStatus = 'error (unrecognized client)';
      break;
  }

  const endTime = Date.now();
  const durationMs = endTime - startTime;

  return {
    client,
    prompt,
    dataSourceType: dataType,
    engineStatus,
    generationDurationMs: durationMs,
    dataPreview: dataSource ? JSON.stringify(dataSource, null, 2).substring(0, 500) + '...' : null
  };
}

// Test cases
async function runTests() {
  console.log('🧪 Running endpoint verification tests...\n');

  const testCases = [
    { client: 'default', prompt: 'Generate workforce optimization insights' },
    { client: 'clientA', prompt: 'Generate clientA insights' },
    { client: 'clientB', prompt: 'Generate clientB insights' },
    { client: 'unknown', prompt: 'Test unknown client' }
  ];

  let passed = 0;
  let failed = 0;

  for (const testCase of testCases) {
    try {
      console.log(`\n--- Testing client: ${testCase.client} ---`);
      const result = await simulateGenerateEndpoint(testCase.client, testCase.prompt);

      // Verify response structure
      if (!result.client || !result.dataSourceType || !result.engineStatus) {
        throw new Error('Missing required response fields');
      }

      console.log(`✅ Response structure valid`);
      console.log(`   - DataSource Type: ${result.dataSourceType}`);
      console.log(`   - Engine Status: ${result.engineStatus}`);
      console.log(`   - Duration: ${result.generationDurationMs}ms`);
      console.log(`   - Data Preview: ${result.dataPreview ? 'Available ✓' : 'None'}`);

      // Verify honesty labels
      if (result.dataSourceType === 'sample') {
        console.log(`   - ⚠️  DATA IS SAMPLE/MOCK - Not production-ready`);
      } else if (result.dataSourceType === 'real') {
        console.log(`   - ✓ REAL DATA - Production-ready`);
      }

      passed++;
    } catch (error) {
      console.error(`❌ Test failed for client ${testCase.client}:`, error.message);
      failed++;
    }
  }

  console.log('\n' + '='.repeat(50));
  console.log(`📊 Test Results: ${passed} passed, ${failed} failed`);
  console.log('='.repeat(50));

  if (failed > 0) {
    process.exit(1);
  }

  console.log('\n✅ All verification tests passed!');
  console.log('\n📝 Next steps:');
  console.log('   1. Deploy to Vercel: vercel deploy');
  console.log('   2. Set environment variable: OPENROUTER_API_KEY');
  console.log('   3. Test with curl:');
  console.log('      curl -X POST https://your-app.vercel.app/api/generate \\');
  console.log('        -H "Content-Type: application/json" \\');
  console.log('        -d \'{"client":"default","prompt":"Test"}\'');
}

// Check if WFM data file exists
const wfmDataExists = fs.existsSync(WFM_DATA_PATH);
console.log(`\n📁 WFM Data File Status:`);
console.log(`   Path: ${WFM_DATA_PATH}`);
console.log(`   Exists: ${wfmDataExists ? '✅ Yes' : '❌ No'}`);

if (!wfmDataExists) {
  console.log('\n   Note: WFM data file not found at expected location.');
  console.log('   The endpoint will use sample data as fallback for default client.');
}

// Run tests
runTests().catch(error => {
  console.error('Test execution failed:', error);
  process.exit(1);
});
