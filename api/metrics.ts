/**
 * Simple metrics collection and monitoring for the /api/generate endpoint
 * Provides basic observability without external dependencies
 */

interface MetricEntry {
  timestamp: string;
  client: string;
  dataSourceType: string;
  durationMs: number;
  status: 'success' | 'error';
  error?: string;
}

interface AggregatedMetrics {
  totalRequests: number;
  successCount: number;
  errorCount: number;
  avgDurationMs: number;
  byClient: Record<string, {
    count: number;
    avgDurationMs: number;
    errors: number;
  }>;
  byDataSource: Record<string, number>;
}

/**
 * In-memory metrics store (in production, use persistent storage like Redis, Prometheus, etc.)
 */
class MetricsCollector {
  private metrics: MetricEntry[] = [];
  private readonly maxEntries = 10000; // Limit memory usage

  record(metric: MetricEntry): void {
    this.metrics.push(metric);

    // Trim old entries if over limit
    if (this.metrics.length > this.maxEntries) {
      this.metrics = this.metrics.slice(-this.maxEntries);
    }
  }

  getRecent(count: number = 100): MetricEntry[] {
    return this.metrics.slice(-count);
  }

  getAggregated(since?: Date): AggregatedMetrics {
    const filtered = since
      ? this.metrics.filter(m => new Date(m.timestamp) >= since)
      : this.metrics;

    if (filtered.length === 0) {
      return {
        totalRequests: 0,
        successCount: 0,
        errorCount: 0,
        avgDurationMs: 0,
        byClient: {},
        byDataSource: {}
      };
    }

    const successMetrics = filtered.filter(m => m.status === 'success');
    const errorMetrics = filtered.filter(m => m.status === 'error');

    // Aggregate by client
    const byClient: AggregatedMetrics['byClient'] = {};
    filtered.forEach(m => {
      if (!byClient[m.client]) {
        byClient[m.client] = { count: 0, avgDurationMs: 0, errors: 0 };
      }
      byClient[m.client].count++;
      byClient[m.client].avgDurationMs += m.durationMs;
      if (m.status === 'error') {
        byClient[m.client].errors++;
      }
    });

    // Calculate averages
    Object.keys(byClient).forEach(client => {
      byClient[client].avgDurationMs = Math.round(
        byClient[client].avgDurationMs / byClient[client].count
      );
    });

    // Aggregate by data source
    const byDataSource: AggregatedMetrics['byDataSource'] = {};
    filtered.forEach(m => {
      byDataSource[m.dataSourceType] = (byDataSource[m.dataSourceType] || 0) + 1;
    });

    return {
      totalRequests: filtered.length,
      successCount: successMetrics.length,
      errorCount: errorMetrics.length,
      avgDurationMs: Math.round(
        successMetrics.reduce((sum, m) => sum + m.durationMs, 0) / successMetrics.length
      ) || 0,
      byClient,
      byDataSource
    };
  }

  clear(): void {
    this.metrics = [];
  }
}

// Singleton instance
export const metricsCollector = new MetricsCollector();

/**
 * Records a request metric from the API handler
 */
export function recordRequestMetric(
  client: string,
  dataSourceType: string,
  durationMs: number,
  status: 'success' | 'error',
  error?: string
): void {
  metricsCollector.record({
    timestamp: new Date().toISOString(),
    client,
    dataSourceType,
    durationMs,
    status,
    error
  });
}

/**
 * Returns current metrics summary for monitoring dashboard
 */
export function getMetricsSummary(): AggregatedMetrics {
  return metricsCollector.getAggregated();
}

/**
 * Returns metrics for the last N requests
 */
export function getRecentMetrics(count: number = 50): MetricEntry[] {
  return metricsCollector.getRecent(count);
}

/**
 * Middleware wrapper for Vercel API handlers to automatically collect metrics
 */
export function withMetrics<T extends (...args: any[]) => Promise<Response>>(
  handler: T
): T {
  return (async (...args: any[]) => {
    const startTime = Date.now();
    let client = 'unknown';
    let dataSourceType = 'unknown';

    try {
      const response = await handler(...args);
      const durationMs = Date.now() - startTime;

      // Try to extract client and data source from response
      // This is a best-effort approach since we don't have direct access to handler internals
      // In a real implementation, you'd pass this info explicitly

      recordRequestMetric(client, dataSourceType, durationMs, 'success');
      return response;
    } catch (error) {
      const durationMs = Date.now() - startTime;
      recordRequestMetric(client, dataSourceType, durationMs, 'error',
        error instanceof Error ? error.message : 'Unknown error');
      throw error;
    }
  }) as T;
}

/**
 * Export metrics in Prometheus format for scraping
 */
export function exportPrometheusMetrics(): string {
  const metrics = getMetricsSummary();

  let output = '# HELP generate_api_requests_total Total number of API requests\n';
  output += '# TYPE generate_api_requests_total counter\n';
  output += `generate_api_requests_total ${metrics.totalRequests}\n\n`;

  output += '# HELP generate_api_success_total Total number of successful requests\n';
  output += '# TYPE generate_api_success_total counter\n';
  output += `generate_api_success_total ${metrics.successCount}\n\n`;

  output += '# HELP generate_api_errors_total Total number of failed requests\n';
  output += '# TYPE generate_api_errors_total counter\n';
  output += `generate_api_errors_total ${metrics.errorCount}\n\n`;

  output += '# HELP generate_api_duration_ms Average request duration in milliseconds\n';
  output += '# TYPE generate_api_duration_ms gauge\n';
  output += `generate_api_duration_ms ${metrics.avgDurationMs}\n\n`;

  Object.entries(metrics.byClient).forEach(([client, data]) => {
    output += `# HELP generate_api_client_requests_total Requests per client\n`;
    output += `# TYPE generate_api_client_requests_total counter\n`;
    output += `generate_api_client_requests_total{client="${client}"} ${data.count}\n\n`;

    output += `# HELP generate_api_client_duration_ms Average duration per client\n`;
    output += `# TYPE generate_api_client_duration_ms gauge\n`;
    output += `generate_api_client_duration_ms{client="${client}"} ${data.avgDurationMs}\n\n`;

    output += `# HELP generate_api_client_errors_total Errors per client\n`;
    output += `# TYPE generate_api_client_errors_total counter\n`;
    output += `generate_api_client_errors_total{client="${client}"} ${data.errors}\n\n`;
  });

  Object.entries(metrics.byDataSource).forEach(([source, count]) => {
    output += `# HELP generate_api_datasource_requests_total Requests per data source type\n`;
    output += `# TYPE generate_api_datasource_requests_total counter\n`;
    output += `generate_api_datasource_requests_total{datasource="${source}"} ${count}\n\n`;
  });

  return output;
}

/**
 * Express-style middleware for serving metrics endpoint
 * Usage: app.get('/metrics', metricsMiddleware)
 */
export function metricsMiddleware(req: any, res: any): void {
  if (req.path === '/metrics' || req.path === '/api/metrics') {
    res.set('Content-Type', 'text/plain; version=0.0.4; charset=utf-8');
    res.send(exportPrometheusMetrics());
  }
}

export { MetricsCollector, MetricEntry, AggregatedMetrics };
