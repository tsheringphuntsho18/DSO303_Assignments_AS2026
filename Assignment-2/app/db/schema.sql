-- EduExam schema. Apply once after the first `terraform apply`, e.g. from
-- AWS CloudShell or an EC2/SSM bastion in the VPC (Aurora has no public
-- endpoint, by design):
--   psql "host=<rds_proxy_endpoint> dbname=eduexam user=eduexam_admin sslmode=require" -f schema.sql

CREATE TABLE IF NOT EXISTS users (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    cognito_sub text UNIQUE NOT NULL,
    email       text UNIQUE NOT NULL,
    role        text NOT NULL CHECK (role IN ('student', 'tutor', 'admin')),
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS exams (
    id               text PRIMARY KEY,
    title            text NOT NULL,
    duration_seconds integer NOT NULL,
    questions        jsonb NOT NULL,       -- [{ "id": "q1", "text": "...", "options": [...] }, ...]
    mcq_answer_key   jsonb NOT NULL,       -- { "q1": "A", "q2": "C", ... }
    created_at       timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS attempts (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    exam_id             text NOT NULL REFERENCES exams(id),
    student_sub         text NOT NULL,     -- Cognito "sub" claim
    started_at          timestamptz NOT NULL DEFAULT now(),
    last_autosaved_at   timestamptz,
    answers             jsonb NOT NULL DEFAULT '{}',
    submitted_at        timestamptz,
    mcq_score           integer,
    mcq_total           integer,
    marked_at           timestamptz,
    results_released_at timestamptz,
    score               numeric,
    UNIQUE (exam_id, student_sub)
);

CREATE TABLE IF NOT EXISTS assignments (
    id         text PRIMARY KEY,
    tutor_id   uuid NOT NULL REFERENCES users(id),
    title      text NOT NULL,
    due_at     timestamptz,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS submissions (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    assignment_id  text NOT NULL REFERENCES assignments(id),
    student_sub    text NOT NULL,
    s3_key         text NOT NULL,
    received_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_attempts_exam ON attempts(exam_id);
CREATE INDEX IF NOT EXISTS idx_submissions_assignment ON submissions(assignment_id);

-- Sample data for the walkthrough demo / simulate.py
INSERT INTO exams (id, title, duration_seconds, questions, mcq_answer_key)
VALUES (
    'exam-101',
    'DSO303 Midterm',
    3600,
    '[{"id":"q1","text":"2+2=?","options":["3","4","5"]},{"id":"q2","text":"Capital of Bhutan?","options":["Thimphu","Paro","Punakha"]}]',
    '{"q1":"4","q2":"Thimphu"}'
) ON CONFLICT (id) DO NOTHING;
