import http from 'k6/http';
import exec from 'k6/execution';
import { check } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

const measurementDuration = new Trend('io_measurement_http_req_duration', true);
const measurementFailures = new Rate('io_measurement_failures');
const measurementRequests = new Counter('io_measurement_requests');
const measurementCompletionsInWindow = new Counter('io_measurement_completions_in_window');
const measurementSuccessesInWindow = new Counter('io_measurement_successes_in_window');
const measurementFailuresInWindow = new Counter('io_measurement_failures_in_window');
const measurementCompletionsAfterWindow = new Counter('io_measurement_completions_after_window');
const measurementFailuresAfterWindow = new Counter('io_measurement_failures_after_window');
const totalValidResponses = new Counter('io_total_valid_responses');

function positiveInteger(name, fallback) {
  const value = Number(__ENV[name] || fallback);
  if (!Number.isInteger(value) || value <= 0) throw new Error(`${name} deve ser um inteiro positivo.`);
  return value;
}

function nonNegativeInteger(name, fallback) {
  const raw = __ENV[name];
  const value = Number(raw === undefined || raw === '' ? fallback : raw);
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new Error(`${name} deve ser um inteiro não negativo seguro.`);
  }
  return value;
}

function durationMilliseconds(name, value) {
  const match = /^(\d+(?:\.\d+)?)(ms|s|m|h)$/.exec(value);
  if (!match) throw new Error(`${name} deve usar ms, s, m ou h.`);
  return Number(match[1]) * { ms: 1, s: 1000, m: 60000, h: 3600000 }[match[2]];
}

function requestUuid(phase, iteration) {
  const namespace = phase === 'warmup' ? '1' : '2';
  return `00000000-0000-4000-8000-${namespace}${iteration.toString(16).padStart(11, '0')}`;
}

const rate = positiveInteger('RATE', 100);
const warmupRate = positiveInteger('WARMUP_RATE', Math.min(rate, 100));
const preAllocatedVUs = positiveInteger('PRE_ALLOCATED_VUS', 100);
const maxVUs = positiveInteger('MAX_VUS', 1000);
const itemMin = positiveInteger('ITEM_MIN_ID', 1);
const itemMax = positiveInteger('ITEM_MAX_ID', 100000);
const itemCount = itemMax - itemMin + 1;
const itemOffset = nonNegativeInteger('ITEM_OFFSET', 0) % itemCount;
const timeUnit = __ENV.TIME_UNIT || '1s';
const warmupDuration = __ENV.WARMUP_DURATION || '30s';
const measurementWindow = __ENV.MEASUREMENT_DURATION || '60s';
const measurementWindowMs = durationMilliseconds('MEASUREMENT_DURATION', measurementWindow);
const model = __ENV.EXPECTED_MODEL || 'unknown';
const requestTimeout = __ENV.REQUEST_TIMEOUT || '15s';
const runId = __ENV.RUN_ID;

if (itemMax < itemMin) throw new Error('ITEM_MAX_ID deve ser maior ou igual a ITEM_MIN_ID.');
if (maxVUs < preAllocatedVUs) throw new Error('MAX_VUS deve ser maior ou igual a PRE_ALLOCATED_VUS.');
if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(runId || '')) {
  throw new Error('RUN_ID deve ser um UUID válido.');
}

export const options = {
  scenarios: {
    warmup: {
      executor: 'constant-arrival-rate', exec: 'ioRequest', rate: warmupRate, timeUnit,
      duration: warmupDuration, preAllocatedVUs, maxVUs, gracefulStop: '0s',
      tags: { workload: 'io', phase: 'warmup', model },
    },
    measurement: {
      executor: 'constant-arrival-rate', exec: 'ioRequest', startTime: warmupDuration, rate,
      timeUnit, duration: measurementWindow, preAllocatedVUs, maxVUs, gracefulStop: '5s',
      tags: { workload: 'io', phase: 'measurement', model },
    },
  },
  thresholds: { checks: ['rate==1'], io_measurement_failures: ['rate==0'] },
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max', 'count'],
};

export function setup() {
  if (!__ENV.BASE_URL) throw new Error('Defina BASE_URL para o modelo em execução.');
  return { baseUrl: __ENV.BASE_URL };
}

export function ioRequest(data) {
  const phase = exec.scenario.name;
  const iteration = exec.scenario.iterationInTest;
  const requestId = requestUuid(phase, iteration);
  const phaseOffset = phase === 'warmup' ? 0 : 104729;
  const itemId = itemMin + ((iteration * 7919 + phaseOffset + itemOffset) % itemCount);
  const response = http.post(`${data.baseUrl}/io`, JSON.stringify({ itemId, runId, requestId }), {
    headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
    tags: { endpoint: 'io' }, timeout: requestTimeout,
  });
  let body;
  try { body = response.json(); } catch (_) { body = null; }
  const valid = check(response, {
    'IO respondeu 200': (result) => result.status === 200,
    'produto corresponde à requisição': () => body?.item?.id === itemId,
    'categoria foi retornada': () => Number.isInteger(body?.category?.id) && body.category.id > 0,
    'evento corresponde à requisição': () => body?.event?.itemId === itemId
      && body?.event?.runId === runId && body?.event?.requestId === requestId,
    'evento é ITEM_VIEW': () => body?.event?.eventType === 'ITEM_VIEW',
  });
  totalValidResponses.add(valid ? 1 : 0);
  if (phase === 'measurement') {
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
