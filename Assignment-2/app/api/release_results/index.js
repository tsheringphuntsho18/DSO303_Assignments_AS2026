// POST /api/exams/{examId}/release-results
// Tutor-only route (enforced by the "tutor"/"admin" group claim). Marks all
// graded attempts as released and enqueues one email-notification job per
// student instead of emailing synchronously, so a slow SES call or a burst
// of releases never blocks the tutor's request.
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
  const examId = event.pathParameters?.examId;
  const groups = event.requestContext?.authorizer?.jwt?.claims?.["cognito:groups"] || "";
  if (!groups.includes("tutor") && !groups.includes("admin")) {
    return { statusCode: 403, body: JSON.stringify({ error: "tutor or admin role required" }) };
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
    const released = await client.query(
      `UPDATE attempts SET results_released_at = now()
        WHERE exam_id = $1 AND submitted_at IS NOT NULL AND results_released_at IS NULL
        RETURNING id, student_sub, score`,
      [examId]
    );

    for (const row of released.rows) {
      await sqs.send(new SendMessageCommand({
        QueueUrl: process.env.EMAIL_QUEUE_URL,
        MessageBody: JSON.stringify({
          type: "results_released",
          attemptId: row.id,
          studentSub: row.student_sub,
          score: row.score,
        }),
      }));
    }

    return { statusCode: 200, body: JSON.stringify({ releasedCount: released.rowCount }) };
  } finally {
    await client.end();
  }
};
