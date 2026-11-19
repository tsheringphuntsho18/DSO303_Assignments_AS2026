// PUT /api/attempts/{attemptId}/answers
// Called by the SPA every 30 seconds while an exam is open. A write only
// needs to reach Aurora's durable, Multi-AZ storage to be acknowledged, so
// at most one interval of answers is ever at risk — meeting the 5-minute RPO
// target with a wide margin.
const { Client } = require("pg");
const { SecretsManagerClient, GetSecretValueCommand } = require("@aws-sdk/client-secrets-manager");

const secrets = new SecretsManagerClient({});
let cachedCreds;

async function getDbCreds() {
  if (cachedCreds) return cachedCreds;
  const res = await secrets.send(new GetSecretValueCommand({ SecretId: process.env.DB_SECRET_ARN }));
  cachedCreds = JSON.parse(res.SecretString);
  return cachedCreds;
}

exports.handler = async (event) => {
  const attemptId = event.pathParameters?.attemptId;
  const studentSub = event.requestContext?.authorizer?.jwt?.claims?.sub;
  let answers;
  try {
    answers = JSON.parse(event.body || "{}").answers;
  } catch {
    return { statusCode: 400, body: JSON.stringify({ error: "invalid JSON body" }) };
  }

  if (!attemptId || !answers) {
    return { statusCode: 400, body: JSON.stringify({ error: "missing attemptId or answers" }) };
  }

  const creds = await getDbCreds();
  const client = new Client({
    host: process.env.DB_PROXY_ENDPOINT,
    port: 5432,
    user: creds.username,
    password: creds.password,
    database: creds.dbname,
    ssl: { rejectUnauthorized: false },
  });
  await client.connect();

  try {
    const result = await client.query(
      `UPDATE attempts
          SET answers = $1, last_autosaved_at = now()
        WHERE id = $2 AND student_sub = $3 AND submitted_at IS NULL
        RETURNING last_autosaved_at`,
      [JSON.stringify(answers), attemptId, studentSub]
    );
    if (result.rowCount === 0) {
      return { statusCode: 404, body: JSON.stringify({ error: "attempt not found, not yours, or already submitted" }) };
    }
    return { statusCode: 200, body: JSON.stringify({ savedAt: result.rows[0].last_autosaved_at }) };
  } finally {
    await client.end();
  }
};
