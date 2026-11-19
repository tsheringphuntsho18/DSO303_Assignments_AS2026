// SQS worker, triggered by eduexam-marking-queue. Auto-marks MCQ answers
// against the exam's answer key, decoupled from the student's submit
// request so marking never blocks the student-facing API. Throws on
// failure so SQS retries (up to 5x, per the queue's redrive policy) before
// the message lands in the DLQ.
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

function scoreMcq(answerKey, studentAnswers) {
  let correct = 0;
  for (const [questionId, correctOption] of Object.entries(answerKey)) {
    if (studentAnswers[questionId] === correctOption) correct += 1;
  }
  return { correct, total: Object.keys(answerKey).length };
}

exports.handler = async (event) => {
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
    for (const record of event.Records) {
      const { attemptId } = JSON.parse(record.body);

      const row = await client.query(
        `SELECT a.answers, e.mcq_answer_key
           FROM attempts a JOIN exams e ON e.id = a.exam_id
          WHERE a.id = $1`,
        [attemptId]
      );
      if (row.rowCount === 0) continue; // nothing to mark; let the message be removed

      const { correct, total } = scoreMcq(row.rows[0].mcq_answer_key, row.rows[0].answers || {});

      await client.query(
        `UPDATE attempts SET mcq_score = $1, mcq_total = $2, marked_at = now() WHERE id = $3`,
        [correct, total, attemptId]
      );
    }
  } finally {
    await client.end();
  }
};
