// Disposable stacks only. Never run against a deployment's Compose project.
import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
if (process.env.SMOKE_ALLOW_MUTATION !== '1') throw new Error('Set SMOKE_ALLOW_MUTATION=1 for isolated testing.');
for (const failure of ['backup', 'migration']) {
  const project = `vadat-test-${failure}-${process.pid}`;
  const args = ['compose', '--env-file', '/dev/null', '-p', project, '-f', 'docker-compose.yml', '-f', `tests/compose/${failure}-failure.yml`];
  try {
    const up = spawnSync('docker', [...args, 'up', '-d', '--pull', 'never'], { encoding: 'utf8', timeout: 120_000 });
    assert.notEqual(up.status, 0, `${failure} failure should block startup`);
    const id = execFileSync('docker', [...args, 'ps', '-a', '-q', 'web'], { encoding: 'utf8' }).trim();
    assert(id, 'web container must have been created to validate dependency blocking');
    const state = execFileSync('docker', ['inspect', '--format', '{{.State.Status}}', id], { encoding: 'utf8' }).trim();
    assert.equal(state, 'created', `web must not start after ${failure} failure`);
    const service = failure === 'migration' ? 'migrations' : 'backup';
    const failedId = execFileSync('docker', [...args, 'ps', '-a', '-q', service], { encoding: 'utf8' }).trim();
    const exitCode = execFileSync('docker', ['inspect', '--format', '{{.State.ExitCode}}', failedId], { encoding: 'utf8' }).trim();
    assert.notEqual(exitCode, '0');
    console.log(`PASS: failed ${failure} blocks web startup.`);
  } finally {
    // Only volumes belonging to the unique, disposable project created above.
    execFileSync('docker', [...args, 'down', '--volumes'], { stdio: 'ignore' });
  }
}
