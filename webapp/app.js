const tg = window.Telegram?.WebApp;
tg?.ready();
tg?.expand();

// В самом Telegram user_id берём из initDataUnsafe.
// Для локальной проверки вне Telegram подставляем тестовый id через ?user_id=123 в URL.
function getUserId() {
  const fromTelegram = tg?.initDataUnsafe?.user?.id;
  if (fromTelegram) return fromTelegram;
  const params = new URLSearchParams(window.location.search);
  return params.get("user_id") || null;
}

function dayLevel(done) {
  return done ? 4 : 0;
}

function buildHeatmap(checkins, days = 365) {
  const container = document.createElement("div");
  container.className = "heatmap";

  const today = new Date();
  const start = new Date(today);
  start.setDate(start.getDate() - (days - 1));

  // Выравниваем начало сетки на понедельник, чтобы столбцы = недели, строки = дни недели
  const weekday = (start.getDay() + 6) % 7; // 0 = понедельник
  for (let i = 0; i < weekday; i++) {
    const empty = document.createElement("div");
    empty.className = "heatmap-cell";
    container.appendChild(empty);
  }

  for (let d = new Date(start); d <= today; d.setDate(d.getDate() + 1)) {
    const iso = d.toISOString().slice(0, 10);
    const done = checkins[iso] === 1;
    const cell = document.createElement("div");
    cell.className = "heatmap-cell";
    cell.dataset.level = String(dayLevel(done));
    cell.title = `${iso}${done ? " — выполнено" : ""}`;
    container.appendChild(cell);
  }

  return container;
}

function renderHabits(habits) {
  const wrap = document.getElementById("habitsContainer");
  const empty = document.getElementById("emptyState");
  wrap.innerHTML = "";

  if (!habits.length) {
    empty.style.display = "block";
    return;
  }
  empty.style.display = "none";

  for (const habit of habits) {
    const card = document.createElement("div");
    card.className = "habit-card";

    const head = document.createElement("div");
    head.className = "habit-card-head";
    head.innerHTML = `
      <span class="habit-name">${escapeHtml(habit.name)}</span>
      <span class="habit-streak">🔥 ${habit.streak} (рекорд ${habit.best_streak})</span>
    `;
    card.appendChild(head);
    card.appendChild(buildHeatmap(habit.checkins));
    wrap.appendChild(card);
  }
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

async function loadDashboard() {
  const userId = getUserId();
  if (!userId) {
    document.getElementById("emptyState").style.display = "block";
    document.getElementById("emptyState").textContent =
      "Не удалось определить пользователя. Открой мини-апп через кнопку в Telegram-боте.";
    return;
  }

  try {
    const res = await fetch(`/api/dashboard?user_id=${encodeURIComponent(userId)}`);
    const data = await res.json();

    document.getElementById("levelBadge").textContent = `Уровень ${data.level ?? 1}`;
    document.getElementById("weekPct").textContent = `${data.week_pct ?? 0}%`;
    document.getElementById("monthPct").textContent = `${data.month_pct ?? 0}%`;
    document.getElementById("bestHabit").textContent = data.best_habit || "—";

    renderHabits(data.habits || []);
  } catch (err) {
    console.error("Ошибка загрузки данных:", err);
  }
}

loadDashboard();

