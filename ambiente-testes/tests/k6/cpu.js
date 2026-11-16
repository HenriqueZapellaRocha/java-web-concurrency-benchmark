import http from 'k6/http';
import exec from 'k6/execution';
import { check } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

const measurementDuration = new Trend('cpu_measurement_http_req_duration', true);
const measurementFailures = new Rate('cpu_measurement_failures');
const measurementRequests = new Counter('cpu_measurement_requests');
const measurementCompletionsInWindow = new Counter('cpu_measurement_completions_in_window');
const measurementSuccessesInWindow = new Counter('cpu_measurement_successes_in_window');
const measurementFailuresInWindow = new Counter('cpu_measurement_failures_in_window');
const measurementCompletionsAfterWindow = new Counter('cpu_measurement_completions_after_window');
const measurementFailuresAfterWindow = new Counter('cpu_measurement_failures_after_window');

function positiveInteger(name, fallback) {
  const value = Number(__ENV[name] || fallback);
  if (!Number.isInteger(value) || value <= 0) {
    throw new Error(`${name} deve ser um inteiro positivo.`);
  }
  return value;
}

function durationMilliseconds(name, value) {
  const match = /^(\d+(?:\.\d+)?)(ms|s|m|h)$/.exec(value);
  if (!match) {
    throw new Error(`${name} deve usar ms, s, m ou h.`);
  }
  const factors = { ms: 1, s: 1000, m: 60000, h: 3600000 };
  return Number(match[1]) * factors[match[2]];
}

const rate = positiveInteger('RATE', 10);
const warmupRate = positiveInteger('WARMUP_RATE', Math.min(rate, 250));
const preAllocatedVUs = positiveInteger('PRE_ALLOCATED_VUS', 10);
const maxVUs = positiveInteger('MAX_VUS', 100);
const expectedIterations = positiveInteger('EXPECTED_ITERATIONS', 200000);
const timeUnit = __ENV.TIME_UNIT || '1s';
const warmupDuration = __ENV.WARMUP_DURATION || '15s';
const measurementWindow = __ENV.MEASUREMENT_DURATION || '30s';
const measurementWindowMs = durationMilliseconds('MEASUREMENT_DURATION', measurementWindow);
const model = __ENV.EXPECTED_MODEL || 'unknown';
const executionMode = __ENV.EXECUTION_MODE || 'unknown';
const requestTimeout = __ENV.REQUEST_TIMEOUT || '15s';

if (maxVUs < preAllocatedVUs) {
  throw new Error('MAX_VUS deve ser maior ou igual a PRE_ALLOCATED_VUS.');
}

export const options = {
  scenarios: {
    warmup: {
      executor: 'constant-arrival-rate',
      exec: 'cpu',
      rate: warmupRate,
      timeUnit,
      duration: warmupDuration,
      preAllocatedVUs,
      maxVUs,
      gracefulStop: '0s',
      tags: { workload: 'cpu', phase: 'warmup', model, execution_mode: executionMode },
    },
    measurement: {
      executor: 'constant-arrival-rate',
      exec: 'cpu',
      startTime: warmupDuration,
      rate,
      timeUnit,
      duration: measurementWindow,
      preAllocatedVUs,
      maxVUs,
      gracefulStop: '5s',
      tags: { workload: 'cpu', phase: 'measurement', model, execution_mode: executionMode },
    },
  },
  thresholds: {
    checks: ['rate==1'],
    cpu_measurement_failures: ['rate==0'],
  },
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max', 'count'],
};

export function setup() {
  const baseUrl = __ENV.BASE_URL;
  if (!baseUrl) {
    throw new Error('Defina BASE_URL para o modelo em execução.');
  }
  return { baseUrl };
}

export function cpu(data) {
  const response = http.post(`${data.baseUrl}/cpu`, null, {
    headers: { Accept: 'application/json' },
    tags: { endpoint: 'cpu' },
    timeout: requestTimeout,
  });
  let body;
  try {
    body = response.json();
  } catch (_) {
    body = null;
  }
  const valid = check(response, {
    'CPU respondeu 200': (result) => result.status === 200,
    'iterações correspondem à configuração': () => body?.iterations === expectedIterations,
    'chave PBKDF2 hexadecimal': () => /^[0-9a-f]{64}$/.test(body?.digest || ''),
  });

  if (exec.scenario.name === 'measurement') {
    measurementRequests.add(1);
    const completedInWindow = Date.now() - exec.scenario.startTime <= measurementWindowMs;
    measurementCompletionsInWindow.add(completedInWindow ? 1 : 0);
    measurementSuccessesInWindow.add(completedInWindow && valid ? 1 : 0);
    measurementFailuresInWindow.add(completedInWindow && !valid ? 1 : 0);
    measurementCompletionsAfterWindow.add(completedInWindow ? 0 : 1);
    measurementFailuresAfterWindow.add(!completedInWindow && !valid ? 1 : 0);
    measurementDuration.add(response.timings.duration);
    measurementFailures.add(!valid);
  }
}
