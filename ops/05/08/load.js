import http from 'k6/http';
import { check, sleep } from 'k6';

const target = __ENV.CNPL_TARGET;
const data = JSON.parse(open(__ENV.CNPL_DATASET));
const token = __ENV.CNPL_TOKEN_FILE ? open(__ENV.CNPL_TOKEN_FILE).trim() : '';
const vus = Number(__ENV.CNPL_VUS);
const duration = Number(__ENV.CNPL_DURATION);
export const options = {
  discardResponseBodies: true,
  maxRedirects: 0,
  scenarios: {
    warmup: { executor: 'constant-vus', vus: 1, duration: '10s', exec: 'work' },
    steady: { executor: 'constant-vus', vus, duration: `${duration}s`, startTime: '15s', gracefulStop: '5s', exec: 'work' },
  },
  thresholds: {
    'http_req_failed{scenario:steady}': [{ threshold: `rate<=${__ENV.CNPL_ERROR_RATE}`, abortOnFail: true, delayAbortEval: '10s' }],
    'http_req_duration{scenario:steady}': [{ threshold: `p(95)<=${__ENV.CNPL_P95_MS}`, abortOnFail: true, delayAbortEval: '10s' }],
    'checks{scenario:steady}': ['rate==1'],
  },
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
};

export function work() {
  const row = data[(__ITER + __VU) % data.length];
  const headers = { 'Content-Type': 'application/json', 'X-CNPL-Test-Id': __ENV.CNPL_RUN };
  if (token) headers.Authorization = `Bearer ${token}`;
  const response = http.request(row.method || 'GET', target + row.path, row.body ? JSON.stringify(row.body) : null, { headers, redirects: 0, timeout: '5s', tags: { name: row.name || row.path } });
  check(response, { 'expected status': r => r.status === (row.expected_status || 200) });
  sleep(0.2);
}
