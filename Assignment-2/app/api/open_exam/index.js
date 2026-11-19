// GET /api/exams/{examId}/start
// Validates the student's Cognito JWT (done by API Gateway before this runs),
// starts (or resumes) a timed attempt, and returns the question set with the
// server-authoritative time remaining — the client clock is never trusted.
const { Client } = require("pg");
const { SecretsManagerClient, GetSecretValueCommand } = require("@aws-sdk/client-secrets-manager");

const secrets = new SecretsManagerClient({});
let cachedCreds; // reused across warm invocations in the same execution environment

async function getDbCreds() {
  if (cachedCreds) return cachedCreds;
  const res = await secrets.send(new GetSecretValueCommand({ SecretId: process.env.DB_SECRET_ARN }));
  cachedCreds = JSON.parse(res.SecretString);
  return cachedCreds;
}

async function withClient(fn) {
  const creds = await getDbCreds();
  const client = new Client({
    host: process.env.DB_PROXY_ENDPOINT, // always go through RDS Proxy, never the cluster endpoint directly
    port: 5432,
    user: creds.username,
    password: creds.password,
    database: creds.dbname,
    ssl: { rejectUnauthorized: false },
  });
  await client.connect();
  try {
    return await fn(client);
  } finally {
    await client.end();
  }
}

exports.handler = async (event) => {
  const examId = event.pathParameters?.examId;
  const studentSub = event.requestContext?.authorizer?.jwt?.claims?.sub;

  if (!examId || !studentSub) {
    return { statusCode: 400, body: JSON.stringify({ error: "missing examId or auth context" }) };
  }

  const result = await withClient(async (client) => {
    const exam = await client.query(
      "SELECT id, title, duration_seconds, questions FROM exams WHERE id = $1",
      [examId]
    );
    if (exam.rowCount === 0) return null;

    const attempt = await client.query(
      `INSERT INTO attempts (exam_id, student_sub, started_at)
       VALUES ($1, $2, now())
       ON CONFLICT (exam_id, student_sub) DO UPDATE SET started_at = attempts.started_at
       RETURNING id, started_at`,
      [examId, studentSub]
    );

    const startedAt = attempt.rows[0].started_at;
    const deadline = new Date(startedAt.getTime() + exam.rows[0].duration_seconds * 1000);

    return {
      attemptId: attempt.rows[0].id,
      title: exam.rows[0].title,
      questions: exam.rows[0].questions,
      serverTimeRemainingSeconds: Math.max(0, Math.round((deadline - new Date()) / 1000)),
    };
  });

  if (!result) {
    return { statusCode: 404, body: JSON.stringify({ error: "exam not found" }) };
  }
  return { statusCode: 200, body: JSON.stringify(result) };
};
