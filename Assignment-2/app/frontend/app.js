const API = window.EDUEXAM_CONFIG.apiBaseUrl;
let autosaveTimer = null;
let currentAttemptId = null;

async function api(path, options = {}) {
  const res = await fetch(`${API}${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...Auth.authHeader(), ...(options.headers || {}) },
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.status === 202 || res.status === 204 ? null : res.json();
}

// --- Login ---
document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = document.getElementById("login-email").value;
  const password = document.getElementById("login-password").value;
  try {
    await Auth.signIn(email, password);
    document.getElementById("login-view").hidden = true;
    document.getElementById("exam-view").hidden = false;
    document.getElementById("whoami").textContent = `${email} (${Auth.groups.join(", ") || "student"})`;
  } catch (err) {
    document.getElementById("login-error").textContent = err.message;
  }
});

// --- Open exam + autosave loop (every 30 seconds, per the brief) ---
document.getElementById("open-exam-btn").addEventListener("click", async () => {
  const examId = document.getElementById("exam-id").value;
  const data = await api(`/exams/${examId}/start`);
  currentAttemptId = data.attemptId;

  document.getElementById("exam-content").hidden = false;
  document.getElementById("exam-title").textContent = data.title;
  document.getElementById("time-remaining").textContent = data.serverTimeRemainingSeconds;
  document.getElementById("questions").innerHTML = (data.questions || [])
    .map((q, i) => `<p>${i + 1}. ${q.text}</p>`)
    .join("");

  if (autosaveTimer) clearInterval(autosaveTimer);
  autosaveTimer = setInterval(async () => {
    try {
      const answers = collectAnswers();
      await api(`/attempts/${currentAttemptId}/answers`, {
        method: "PUT",
        body: JSON.stringify({ answers }),
      });
      document.getElementById("autosave-status").textContent = `Autosaved at ${new Date().toLocaleTimeString()}`;
    } catch (err) {
      document.getElementById("autosave-status").textContent = `Autosave failed: ${err.message}`;
    }
  }, 30_000);
});

function collectAnswers() {
  // Placeholder: a real exam UI would read each question's selected option.
  return {};
}

document.getElementById("submit-exam-btn").addEventListener("click", async () => {
  clearInterval(autosaveTimer);
  await api(`/attempts/${currentAttemptId}/submit`, { method: "POST" });
  document.getElementById("autosave-status").textContent = "Submitted.";
});

// --- Upload assignment via presigned URL ---
document.getElementById("upload-btn").addEventListener("click", async () => {
  const assignmentId = document.getElementById("assignment-id").value;
  const file = document.getElementById("file-input").files[0];
  const status = document.getElementById("upload-status");
  const progress = document.getElementById("upload-progress");
  if (!file) { status.textContent = "Choose a file first."; return; }

  try {
    const { uploadUrl } = await api(`/assignments/${assignmentId}/upload-url`, {
      method: "POST",
      body: JSON.stringify({ fileName: file.name, contentType: file.type, fileSizeBytes: file.size }),
    });

    progress.hidden = false;
    await new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("PUT", uploadUrl);
      xhr.setRequestHeader("Content-Type", file.type);
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) progress.value = Math.round((e.loaded / e.total) * 100);
      };
      xhr.onload = () => (xhr.status < 300 ? resolve() : reject(new Error(`S3 upload failed: ${xhr.status}`)));
      xhr.onerror = () => reject(new Error("network error during upload"));
      xhr.send(file);
    });

    status.textContent = "Upload complete — the tutor will be notified automatically.";
  } catch (err) {
    status.textContent = `Upload failed: ${err.message}`;
  }
});

// --- Tutor: release results ---
document.getElementById("release-btn").addEventListener("click", async () => {
  const examId = document.getElementById("release-exam-id").value;
  const status = document.getElementById("release-status");
  try {
    const result = await api(`/exams/${examId}/release-results`, { method: "POST" });
    status.textContent = `Released results for ${result.releasedCount} attempt(s).`;
  } catch (err) {
    status.textContent = `Failed: ${err.message}`;
  }
});
