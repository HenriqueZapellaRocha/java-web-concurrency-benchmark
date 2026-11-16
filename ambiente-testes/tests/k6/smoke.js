import http from 'k6/http';
import { check, fail } from 'k6';

// Verificação funcional da infraestrutura. Não é um teste de desempenho dos workloads.
export const options = {
  vus: 1,
  iterations: 1,
  thresholds: { checks: ['rate==1'], http_req_failed: ['rate==0'] },
};

export default function () {
  const baseUrl = __ENV.BASE_URL;
  const model = __ENV.EXPECTED_MODEL;
  if (!baseUrl || !['m1', 'm2', 'm3'].includes(model)) {
    fail('Defina BASE_URL e EXPECTED_MODEL=m1|m2|m3.');
  }
  const health = http.get(`${baseUrl}/actuator/health/readiness`);
  check(health, { 'aplicação e banco prontos': (r) => r.status === 200 && r.json('status') === 'UP' });
  const databaseIndicator = model === 'm3' ? 'r2dbc' : 'db';
  check(health, {
    'conexão real da aplicação com PostgreSQL': (r) => r.status === 200 && r.json(`components.${databaseIndicator}.status`) === 'UP',
  });
  const response = http.get(`${baseUrl}/environment`);
  if (response.status !== 200) {
    fail(`Diagnóstico respondeu HTTP ${response.status}`);
  }
  const body = response.json();
  check(body, {
    'modelo esperado': (r) => r.model === model,
    'tipo de thread esperado': (r) => r.virtual === (model === 'm2'),
    'marcador não bloqueante do Reactor': (r) => r.nonBlocking === (model === 'm3'),
    'Spring Boot congelado': (r) => r.springBootVersion === '3.5.6',
    'Temurin congelado': (r) => r.javaVersion === '21.0.11+10-LTS' && r.javaVendor === 'Eclipse Adoptium',
    'pilha HTTP esperada': (r) => r.webStack === (model === 'm3' ? 'spring-webflux/netty' : 'spring-mvc/tomcat'),
  });
}
