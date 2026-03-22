"use strict";

// ──────────────────────────────────────────
//  State
// ──────────────────────────────────────────
let token     = null;
let score     = 0;
let answering = false;

const socket = io();

// ──────────────────────────────────────────
//  Boot
// ──────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async () => {
  // Enter key on name input
  document.getElementById("player-name").addEventListener("keydown", e => {
    if (e.key === "Enter") startGame();
  });

  // Try to resume an existing session
  const saved = localStorage.getItem("wedding_token");
  if (saved) await tryResume(saved);
});

// ──────────────────────────────────────────
//  Socket
// ──────────────────────────────────────────
socket.on("leaderboard_update", data => {
  if (document.getElementById("screen-end").classList.contains("active")) {
    renderBoard(data);
  }
});

// ──────────────────────────────────────────
//  Resume
// ──────────────────────────────────────────
async function tryResume(savedToken) {
  try {
    const res  = await post("/api/resume", { token: savedToken });
    const data = await res.json();

    if (!res.ok || data.error === "not_found") {
      localStorage.removeItem("wedding_token");
      return;
    }

    token = savedToken;
    score = data.score;

    if (data.finished) {
      showScreen("screen-end");
      populateEndScreen(data.score);
      if (data.leaderboard) renderBoard(data.leaderboard);
    } else if (data.question) {
      showScreen("screen-question");
      applyQuestion(data.question);
      updateProgress(data.question.index, data.question.total);
      updateScoreChip(score);
    }
  } catch {
    localStorage.removeItem("wedding_token");
  }
}

// ──────────────────────────────────────────
//  Start
// ──────────────────────────────────────────
async function startGame() {
  const input = document.getElementById("player-name");
  const name  = input.value.trim();

  if (!name) {
    input.classList.add("shake");
    input.focus();
    input.addEventListener("animationend", () => input.classList.remove("shake"), { once: true });
    return;
  }

  const btn = document.getElementById("start-btn");
  btn.disabled    = true;
  btn.textContent = "מתחיל...";

  try {
    const res  = await post("/api/start", { name });
    const data = await res.json();

    if (data.error) {
      showError(data.error);
      btn.disabled    = false;
      btn.textContent = "בוא נתחיל! 🎉";
      return;
    }

    token = data.token;
    score = 0;
    localStorage.setItem("wedding_token", token);

    showScreen("screen-question");
    applyQuestion(data.question);
    updateProgress(0, data.question.total);
    updateScoreChip(0);

  } catch {
    showError("שגיאה בהתחברות לשרת");
    btn.disabled    = false;
    btn.textContent = "בוא נתחיל! 🎉";
  }
}

// ──────────────────────────────────────────
//  Answer
// ──────────────────────────────────────────
async function selectAnswer(idx, btn) {
  if (answering) return;
  answering = true;

  btn.classList.add("selected");
  document.querySelectorAll(".option-btn").forEach(b => b.classList.add("locked"));

  try {
    const res  = await post("/api/answer", { token, answer_index: idx });
    const data = await res.json();

    score = data.score;
    updateScoreChip(score);

    await sleep(380);   // brief pause so tap feedback is visible

    if (data.finished) {
      localStorage.removeItem("wedding_token");
      showScreen("screen-end");
      populateEndScreen(data.score);
      if (data.leaderboard) renderBoard(data.leaderboard);
      socket.emit("request_leaderboard");
    } else {
      applyQuestion(data.question);
      updateProgress(data.question.index, data.question.total);
    }

  } catch {
    showError("שגיאה בשליחת התשובה");
  } finally {
    answering = false;
  }
}

// ──────────────────────────────────────────
//  UI helpers
// ──────────────────────────────────────────
function applyQuestion(q) {
  document.getElementById("question-text").textContent = q.text;
  document.getElementById("q-counter").textContent =
    `שאלה ${q.index + 1} מתוך ${q.total}`;

  const grid = document.getElementById("options-grid");
  grid.innerHTML = "";
  q.options.forEach((opt, i) => {
    const b = document.createElement("button");
    b.className   = "option-btn";
    b.textContent = opt;
    b.onclick = () => selectAnswer(i, b);
    grid.appendChild(b);
  });

  // Restart card animation
  const card = document.getElementById("question-card");
  card.style.animation = "none";
  card.offsetHeight;              // reflow
  card.style.animation = "";
}

function updateProgress(idx, total) {
  document.getElementById("progress-fill").style.width =
    (idx / total * 100) + "%";
}

function updateScoreChip(val) {
  const el = document.getElementById("q-score");
  el.textContent = `${val} נקודות`;
  el.classList.remove("bump");
  el.offsetHeight;
  el.classList.add("bump");
}

function populateEndScreen(finalScore) {
  document.getElementById("final-score").textContent = finalScore;

  const pct = finalScore / (TOTAL_Q * 10);
  let emoji, title, msg;

  if (pct >= 0.9) {
    emoji = "🏆";
    title = "מדהים!";
    msg   = "אתה מכיר את הזוג אפילו יותר טוב מהם עצמם! 🤩";
  } else if (pct >= 0.7) {
    emoji = "🎉";
    title = "כל הכבוד!";
    msg   = "אתה מכיר את מעיין ואמיר ממש טוב! 👏";
  } else if (pct >= 0.5) {
    emoji = "😄";
    title = "לא רע!";
    msg   = "יש עוד מה ללמוד על הזוג... 😉";
  } else {
    emoji = "😅";
    title = "אופס!";
    msg   = "נסה לבלות יותר זמן עם מעיין ואמיר 😂";
  }

  document.getElementById("end-emoji").textContent  = emoji;
  document.getElementById("end-title").textContent  = title;
  document.getElementById("end-msg").textContent    = msg;
}

function renderBoard(players) {
  const el = document.getElementById("board-live");
  if (!players || players.length === 0) {
    el.innerHTML = '<div class="board-loading">אין שחקנים עדיין</div>';
    return;
  }
  const medals = ["🥇","🥈","🥉"];
  el.innerHTML = players.map((p, i) => `
    <div class="board-item r${i+1}">
      <div class="board-rank">${medals[i] || (i+1)}</div>
      <div class="board-name">${esc(p.name)}</div>
      <div class="board-score">${p.score}</div>
    </div>
  `).join("");
}

function showScreen(id) {
  document.querySelectorAll(".screen").forEach(s => s.classList.remove("active"));
  document.getElementById(id).classList.add("active");
  window.scrollTo(0, 0);
}

function showError(msg) {
  alert(msg);
}

// ──────────────────────────────────────────
//  Utils
// ──────────────────────────────────────────
function post(url, body) {
  return fetch(url, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(body),
  });
}

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

function esc(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}
