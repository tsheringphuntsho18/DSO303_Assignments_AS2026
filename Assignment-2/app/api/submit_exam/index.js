// POST /api/attempts/{attemptId}/submit
// Final submit (on the student clicking "Submit" or the server-side timer
// expiring). Closes the attempt, then hands marking off to SQS so this
// request returns immediately instead of waiting on auto-marking.
const { Client } = require("pg");
const { SQSClient, SendMessageCommand } = require("@aws-sdk/client-sqs");
const { SecretsManagerClient, GetSecretValueCommand } = require("@aws-sdk/client-secrets-manager");

const sqs = new SQSClient({});
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
      `UPDATE attempts SET submitted_at = now()
        WHERE id = $1 AND student_sub = $2 AND submitted_at IS NULL
        RETURNING id`,
      [attemptId, studentSub]
    );
    if (result.rowCount === 0) {
      return { statusCode: 404, body: JSON.stringify({ error: "attempt not found, not yours, or already submitted" }) };
    }

    await sqs.send(new SendMessageCommand({
      QueueUrl: process.env.MARKING_QUEUE_URL,
      MessageBody: JSON.stringify({ attemptId }),
    }));

    return { statusCode: 202, body: JSON.stringify({ attemptId, status: "submitted" }) };
  } finally {
    await client.end();
  }
};
