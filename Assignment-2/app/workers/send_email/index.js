// SQS worker, triggered by eduexam-email-queue. Sends "results released" and
// "assignment received" notifications via SES. Any delivery failure throws,
// so SQS retries (up to 5x) before the message lands in the DLQ, where a
// CloudWatch alarm flags it — a notification is never silently dropped.
const { SESv2Client, SendEmailCommand } = require("@aws-sdk/client-sesv2");

const ses = new SESv2Client({});

const TEMPLATES = {
  results_released: (msg) => ({
    subject: "Your exam results are available",
    body: `Your results for attempt ${msg.attemptId} have been released. Score: ${msg.score}.`,
  }),
  submission_received: (msg) => ({
    subject: `New submission: ${msg.fileName}`,
    body: `A student submitted "${msg.fileName}" for assignment ${msg.assignmentId}.`,
  }),
};

exports.handler = async (event) => {
  for (const record of event.Records) {
    const msg = JSON.parse(record.body);
    const template = TEMPLATES[msg.type];
    if (!template) continue;

    const { subject, body } = template(msg);
    const to = msg.to || msg.studentEmail;
    if (!to) continue;

    await ses.send(new SendEmailCommand({
      FromEmailAddress: process.env.SES_FROM_ADDRESS,
      Destination: { ToAddresses: [to] },
      Content: {
        Simple: {
          Subject: { Data: subject },
          Body: { Text: { Data: body } },
        },
      },
    }));
  }
};
