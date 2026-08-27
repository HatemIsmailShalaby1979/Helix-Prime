// API endpoint for generating insights using OpenRouter
// Implements client-specific data segmentation with honesty about data availability

import { OpenRouter } from '@ai-sdk/provider';
import * as fs from 'fs';
import * as path from 'path';
import { recordRequestMetric } from '../api/metrics';

// Initialize OpenRouter provider
const API_KEY = process.env.OPENROUTER_API_KEY;
if (!API_KEY) {
  throw new Error('OPENROUTER_API_KEY environment variable is required');
}

const openRouter = new OpenRouter({
  apiKey: API_KEY,
  routing: 'bard'
});

// Path to WFM real data output
const WFM_DATA_PATH = path.join(process.cwd(), 'engines', 'wfm', 'src', 'output', 'results_20260717_163732.json');

/**
 * Loads and parses the WFM real data file
 */
async function loadWFMData(): Promise<any> {
  try {
    const data = fs.readFileSync(WFM_DATA_PATH, 'utf8');
    return JSON.parse(data);
  } catch (error) {
    console.error('Error loading WFM data:', error);
    return null;
  }
}

/**
 * Generates sample client data (clearly labeled as sample/mock)
 */
function generateSampleClientData(clientId: string): any {
  const baseData: any = {
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
      note: 'This is sample/mock data for demonstration purposes only. Real data not yet available for this engine.'
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
    default:
      break;
  }

  return baseData;
}

/**
 * Vercel API handler for the generate endpoint
 */
export default async function handler(req: Request): Promise<Response> {
  const startTime = Date.now();
  let client = 'unknown';
  let dataType = 'unknown';

  try {
    // Parse request body
    let body: any = {};
    try {
      const text = await req.text();
      body = text ? JSON.parse(text) : {};
    } catch {
      body = {};
    }

    client = body.client || 'default';
    const prompt = body.prompt || 'Generate insights';

    let dataSource: any = null;
    let engineStatus = 'unknown';

    // Determine data source based on client selection
    switch (client) {
      case 'default':
        dataSource = await loadWFMData();
        if (dataSource) {
          dataType = 'real';
          engineStatus = 'operational (WFM engine — real data loaded)';
        } else {
          dataSource = generateSampleClientData('default');
          dataType = 'sample';
          engineStatus = 'degraded — real WFM data unavailable, using sample fallback';
        }
        break;

      case 'clientA':
      case 'clientB':
        dataSource = generateSampleClientData(client);
        dataType = 'sample';
        engineStatus = 'in development — sample/mock data only, no real data yet';
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
        engineStatus = 'error — unrecognized client selected';
        break;
    }

    // Construct the prompt for OpenRouter
    let openRouterPrompt = `User prompt: "${prompt}"\n\n`;

    if (dataSource && !dataSource.error) {
      openRouterPrompt += `Current ${engineStatus}\n`;
      openRouterPrompt += `Data type: ${dataType}\n`;
      openRouterPrompt += JSON.stringify(dataSource, null, 2);
    } else {
      openRouterPrompt += `System status: ${engineStatus}\n`;
      openRouterPrompt += `Please provide a helpful response based on the available information.`;
    }

    // Determine max_tokens dynamically based on input length
    // Longer source content → proportionally longer output
    // Floor: 4096 tokens (~3200 words), Cap: 8192 tokens (~6500 words)
    // Scale: 1 token per ~4 characters of input
    const sourceLength = openRouterPrompt.length;
    const dynamicMaxTokens = Math.min(
      Math.max(Math.floor(sourceLength / 4), 4096),
      8192
    );

    // Call OpenRouter to generate completion
    const completion = await openRouter.generate({
      model: 'gpt-4o',
      prompt: openRouterPrompt,
      max_tokens: dynamicMaxTokens
    });

    const endTime = Date.now();
    const durationMs = endTime - startTime;

    // Record metrics
    recordRequestMetric(client, dataType, durationMs, 'success');

    // Build response data
    const responseBody: any = {
      client,
      prompt,
      dataSourceType: dataType,
      engineStatus,
      generationDurationMs: durationMs,
      result: completion.completion.trim(),
      sourceModel: 'gpt-4o',
      timestamp: new Date().toISOString()
    };

    // Add data source note if it's sample data
    if (dataType === 'sample') {
      responseBody.note = 'The data shown is sample/mock data for demonstration. Real data is not yet available for this engine/client combination.';
    }

    return new Response(JSON.stringify(responseBody, null, 2), {
      status: 200,
      headers: {
        'content-type': 'application/json; charset=utf-8',
        'cache-control': 'no-cache, no-store, must-revalidate',
        'pragma': 'no-cache',
        'expires': '0'
      }
    });

  } catch (error) {
    const endTime = Date.now();
    const durationMs = endTime - startTime;
    const errorMessage = error instanceof Error ? error.message : 'Unknown error';

    console.error(`[Generate API] Error after ${durationMs}ms:`, error);

    // Record error metric
    recordRequestMetric(client, dataType, durationMs, 'error', errorMessage);

    return new Response(JSON.stringify({
      error: errorMessage,
      status: 'error',
      durationMs: durationMs,
      timestamp: new Date().toISOString()
    }), {
      status: 500,
      headers: {
        'content-type': 'application/json; charset=utf-8'
      }
    });
  }
}
