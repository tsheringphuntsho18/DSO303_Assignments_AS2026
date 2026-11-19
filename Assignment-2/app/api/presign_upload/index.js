// POST /api/assignments/{id}/upload-url
// Returns a short-lived presigned S3 PUT URL so the browser can upload the
// file (up to 50 MB — PDF or ZIP) directly to S3. No file bytes ever pass
// through API Gateway (10 MB limit) or this Lambda.
const { S3Client, PutObjectCommand } = require("@aws-sdk/client-s3");
const { getSignedUrl } = require("@aws-sdk/s3-request-presigner");

const s3 = new S3Client({});
const MAX_BYTES = 50 * 1024 * 1024;
const ALLOWED_TYPES = new Set(["application/pdf", "application/zip", "application/x-zip-compressed"]);

exports.handler = async (event) => {
  const assignmentId = event.pathParameters?.id;
  const studentSub = event.requestContext?.authorizer?.jwt?.claims?.sub;

  let body;
  try {
    body = JSON.parse(event.body || "{}");
  } catch {
    return { statusCode: 400, body: JSON.stringify({ error: "invalid JSON body" }) };
  }

  const { fileName, contentType, fileSizeBytes } = body;

  if (!fileName || !contentType || !fileSizeBytes) {
    return { statusCode: 400, body: JSON.stringify({ error: "fileName, contentType and fileSizeBytes are required" }) };
  }
  if (!ALLOWED_TYPES.has(contentType)) {
    return { statusCode: 415, body: JSON.stringify({ error: "only PDF or ZIP uploads are accepted" }) };
  }
  if (fileSizeBytes > MAX_BYTES) {
    return { statusCode: 413, body: JSON.stringify({ error: `file exceeds the 50MB limit (${fileSizeBytes} bytes)` }) };
  }

  const key = `submissions/${assignmentId}/${studentSub}/${Date.now()}-${fileName}`;

  const command = new PutObjectCommand({
    Bucket: process.env.SUBMISSIONS_BUCKET,
    Key: key,
    ContentType: contentType,
    ContentLength: fileSizeBytes,
    Metadata: { "assignment-id": assignmentId, "student-sub": studentSub },
  });

  const uploadUrl = await getSignedUrl(s3, command, { expiresIn: 300 }); // 5 minutes

  return {
    statusCode: 200,
    body: JSON.stringify({ uploadUrl, key, expiresInSeconds: 300 }),
  };
};
