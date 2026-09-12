// Run only against an isolated test stack: this creates and promotes a test user.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';

if (process.env.SMOKE_ALLOW_MUTATION !== '1') throw new Error('Set SMOKE_ALLOW_MUTATION=1 only for an isolated test stack.');
const origin = process.env.SMOKE_ORIGIN || 'http://localhost:3317';
const container = process.env.SMOKE_WEB_CONTAINER || 'vadat-integration-web-1';
const request = (path, options = {}) => fetch(new URL(path, origin), options);
const jsonPost = (body, cookie) => ({ method: 'POST', headers: { 'content-type': 'application/json', origin, ...(cookie ? { cookie } : {}) }, body: JSON.stringify(body) });
for (let attempt = 0; attempt < 60; attempt++) {
  try { if ((await request('/api/health')).ok) break; } catch {}
  if (attempt === 59) throw new Error('Web service did not become ready.');
  await new Promise(resolve => setTimeout(resolve, 1000));
}
for (const path of ['/', '/audit', '/team', '/api/models']) assert.equal((await request(path)).status, 200, path);
assert.equal((await request('/api/admin/models')).status, 401);
const initial = await (await request('/api/models')).json();
assert(initial.models.length > 0);
const audit = await request('/api/audit', jsonPost({ html_content: '<html><head><title>Smoke</title></head><body><img src=x><a href=#>click here</a></body></html>' }));
assert.match(audit.headers.get('content-type'), /ndjson/);
const events = (await audit.text()).trim().split('\n').map(line => JSON.parse(line));
assert(events.some(event => event.type === 'progress'));
const results = events.filter(event => event.type === 'result');
assert.equal(results.length, 1); assert.equal(results[0].success, true);
assert.equal(results[0].summary.dry_run, true); assert(results[0].programmatic_findings.length > 0);
assert.equal((await request('/api/audit', jsonPost({ model: 'unknown' }))).status, 400);
console.log('PASS: public routes, anonymous audit, model enforcement, NDJSON, and no-key dry run.');

const email = `integration-${Date.now()}@example.test`;
const password = 'isolated-test-password-32-characters';
const forgedSignup = await request('/api/auth/sign-up/email', jsonPost({ name: 'Integration Test', email, password, role: 'ADMIN' }));
assert.equal(forgedSignup.status, 400, 'registration must reject client-supplied roles');
const signup = await request('/api/auth/sign-up/email', jsonPost({ name: 'Integration Test', email, password }));
assert.equal(signup.status, 200, await signup.clone().text());
const cookies = response => response.headers.getSetCookie().map(value => value.split(';')[0]).join('; ');
let cookie = cookies(signup); assert(cookie);
assert.equal((await request('/api/admin/models', { headers: { cookie } })).status, 403, 'signup must not accept ADMIN from the browser');
execFileSync('docker', ['exec', container, 'node', 'scripts/promote-admin.mjs', email], { stdio: 'inherit' });
const signin = await request('/api/auth/sign-in/email', jsonPost({ email, password }));
assert.equal(signin.status, 200); cookie = cookies(signin); assert(cookie);
const admin = await request('/api/admin/models', { headers: { cookie } });
assert.equal(admin.status, 200, await admin.clone().text());
const original = await admin.json();
const selected = original.models.find(model => model.id !== original.defaultModelId).id;
const settings = { enabledModelIds: [selected], defaultModelId: selected };
const put = (data, source = origin) => request('/api/admin/models', { method: 'PUT', headers: { 'content-type': 'application/json', cookie, origin: source }, body: JSON.stringify(data) });
assert.equal((await put(settings, 'https://cross-origin.example')).status, 403);
assert.equal((await put({ enabledModelIds: [], defaultModelId: selected })).status, 400);
assert.equal((await put(settings)).status, 200);
assert.equal((await request('/api/models').then(r => r.json())).defaultModelId, selected);
assert.equal((await request('/api/audit', jsonPost({ model: original.defaultModelId, html_content: '<p>Test</p>' }))).status, 400);
console.log('PASS: registration role protection, administrator promotion, authorization, same-origin validation, and live settings.');

// CI recreates the entire stack, including PostgreSQL, without deleting volumes.
// The lightweight default is useful when testing with only a container name.
if (process.env.SMOKE_RECREATE_STACK === '1') {
  execFileSync('docker', ['compose', '--env-file', '/dev/null', '-p', 'vadat-integration', '-f', 'docker-compose.yml', '-f', 'docker-compose.build.yml', 'up', '-d', '--no-build', '--pull', 'never', '--force-recreate', 'db', 'backup', 'migrations', 'api', 'web'], { stdio: 'inherit', timeout: 120_000 });
} else {
  execFileSync('docker', ['restart', container], { stdio: 'ignore' });
}
let persisted;
for (let i = 0; i < 60; i++) {
  try { const response = await request('/api/models'); if (response.ok) { persisted = await response.json(); break; } } catch {}
  await new Promise(resolve => setTimeout(resolve, 1000));
}
assert.equal(persisted?.defaultModelId, selected);
assert.equal((await put({ enabledModelIds: original.enabledModelIds, defaultModelId: original.defaultModelId })).status, 200);
console.log('PASS: settings persisted through restart/recreation; original model settings restored.');
