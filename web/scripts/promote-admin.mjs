import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';

const email = process.argv[2]?.trim();
if (!email || !email.includes('@') || process.argv.length !== 3) {
  console.error(
    'Usage: node scripts/promote-admin.mjs existing-user@example.org'
  );
  process.exit(1);
}
// SQL literals are escaped; the address is never treated as a SQL expression.
const literal = "'" + email.replaceAll("'", "''") + "'";
// A dollar delimiter cannot occur in the interpolated input.
let delimiter = '$promote$';
while (email.includes(delimiter))
  delimiter = delimiter.replace('$promote', '$promote_');
const sql = `DO ${delimiter} BEGIN
  IF NOT EXISTS (SELECT 1 FROM "User" WHERE email = ${literal}) THEN
    RAISE EXCEPTION 'No existing account matches that email';
  END IF;
  UPDATE "User" SET role = 'ADMIN', "updatedAt" = CURRENT_TIMESTAMP WHERE email = ${literal};
END ${delimiter};`;
const containerCli = '/node_modules/prisma/build/index.js';
const cli = existsSync(containerCli)
  ? containerCli
  : 'node_modules/prisma/build/index.js';
const result = spawnSync(process.execPath, [cli, 'db', 'execute', '--stdin'], {
  input: sql,
  stdio: ['pipe', 'inherit', 'inherit'],
});
if (result.error) console.error(result.error.message);
process.exit(result.status ?? 1);
