// EventBridge target, triggered by the S3 "Object Created" rule on the
// submissions bucket (async.tf). Records the submission, then hands the
// actual email off to the email-queue so this function returns fast and a
// slow/failed SES call never blocks the S3 event pipeline.
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

// Key format from presign_upload: submissions/{assignmentId}/{studentSub}/{timestamp}-{fileName}
function parseKey(key) {
  const [, assignmentId, studentSub, rest] = key.split("/");
  return { assignmentId, studentSub, fileName: rest };
}

exports.handler = async (event) => {
  const key = event.detail.object.key;
  const { assignmentId, studentSub, fileName } = parseKey(key);

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

  let tutorEmail;
  try {
    await client.query(
      `INSERT INTO submissions (assignment_id, student_sub, s3_key, received_at)
       VALUES ($1, $2, $3, now())`,
      [assignmentId, studentSub, key]
    );

    const tutor = await client.query(
      `SELECT u.email FROM assignments a
         JOIN users u ON u.id = a.tutor_id
        WHERE a.id = $1`,
      [assignmentId]
    );
    tutorEmail = tutor.rows[0]?.email;
  } finally {
    await client.end();
  }

  if (!tutorEmail) return; // nothing more to do if the assignment has no tutor on record

  await sqs.send(new SendMessageCommand({
    QueueUrl: process.env.EMAIL_QUEUE_URL,
    MessageBody: JSON.stringify({
      type: "submission_received",
      to: tutorEmail,
      assignmentId,
      studentSub,
      fileName,
    }),
  }));
};
