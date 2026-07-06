const TEAM_SLOTS = [
  { key: "tank", label: "Tank", role: "tank" },
  { key: "dps1", label: "DPS 1", role: "dps" },
  { key: "dps2", label: "DPS 2", role: "dps" },
  { key: "support1", label: "Support 1", role: "support" },
  { key: "support2", label: "Support 2", role: "support" },
];

const DEFAULT_SETUP = {
  enemy_team: {
    tank: "winston",
    dps1: "genji",
    dps2: "sombra",
    support1: "lucio",
    support2: "kiriko",
  },
  my_team: {
    tank: null,
    dps1: null,
    dps2: null,
    support1: null,
    support2: null,
  },
  locked_slots: {},
  carry_targets: ["genji"],
  top: 8,
};

const ROLE_LABELS = {
  tank: "Tank",
  dps: "DPS",
  support: "Support",
};

const SCORE_LABELS = {
  alpha: "Counter",
  beta: "Synergy",
  delta: "Countered",
};

const PERSONAL_PREFERENCES_ENABLED = false;

let catalog = null;
let setup = clone(DEFAULT_SETUP);
let activeTarget = { type: "enemy", key: "tank" };
let recommendTimer = null;
let settingsDraft = null;

const els = {};

document.addEventListener("DOMContentLoaded", init);

async function init() {
  bindElements();
  bindEvents();
  setStatus("Loading");

  try {
    catalog = await api("/api/catalog");
    settingsDraft = {
      preferences: clone(catalog.preferences),
      config: clone(catalog.config),
    };
    setup = loadSetup();
    normalizeSetup();
    renderAll();
    await requestRecommendations();
  } catch (err) {
    setStatus("Offline", "bad");
    renderError(err.message);
  }
}

function bindElements() {
  [
    "saveState",
    "resetSetup",
    "recommendNow",
    "openSettings",
    "closeSettings",
    "enemyCount",
    "teamCount",
    "enemySlots",
    "teamSlots",
    "heroSearch",
    "gridRoleFilter",
    "activeTarget",
    "heroGrid",
    "apiStatus",
    "warnings",
    "resultsList",
    "settingsDrawer",
    "scoreWeights",
    "roleWeights",
    "carryMultiplier",
    "saveConfig",
    "configSaveMessage",
    "settingsHeroSearch",
    "preferenceList",
    "savePreferences",
    "prefSaveMessage",
  ].forEach((id) => {
    els[id] = document.getElementById(id);
  });
}

function bindEvents() {
  els.recommendNow.addEventListener("click", requestRecommendations);
  els.resetSetup.addEventListener("click", () => {
    setup = clone(DEFAULT_SETUP);
    activeTarget = { type: "enemy", key: "tank" };
    normalizeSetup();
    saveSetup();
    renderAll();
    queueRecommendations();
  });

  els.heroSearch.addEventListener("input", renderHeroGrid);
  els.settingsHeroSearch.addEventListener("input", renderPreferenceList);

  els.gridRoleFilter.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-role]");
    if (!button) return;
    const slot = TEAM_SLOTS.find((item) => item.role === button.dataset.role);
    if (slot) {
      activeTarget = { type: activeTarget.type, key: slot.key };
      renderAll();
    }
  });

  els.openSettings.addEventListener("click", () => {
    els.settingsDrawer.classList.add("open");
    els.settingsDrawer.setAttribute("aria-hidden", "false");
    renderSettings();
  });

  els.closeSettings.addEventListener("click", closeSettings);
  els.settingsDrawer.addEventListener("click", (event) => {
    if (event.target === els.settingsDrawer) closeSettings();
  });

  els.saveConfig.addEventListener("click", saveConfig);
  els.savePreferences.addEventListener("click", savePreferences);
}

function closeSettings() {
  els.settingsDrawer.classList.remove("open");
  els.settingsDrawer.setAttribute("aria-hidden", "true");
}

async function api(path, options = {}) {
  const headers = options.headers || {};
  if (options.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(path, { ...options, headers });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || `Request failed: ${response.status}`);
  }
  return data;
}

function renderAll() {
  renderSlots();
  renderGridRoleFilter();
  renderActiveTarget();
  renderHeroGrid();
  renderSettings();
}

function renderSlots() {
  renderEnemySlots();
  renderTeamSlots();
}

function renderEnemySlots() {
  els.enemySlots.innerHTML = "";
  TEAM_SLOTS.forEach((slotInfo) => {
    const slug = setup.enemy_team[slotInfo.key];
    const hero = slug ? catalog.heroes[slug] : null;
    const slot = document.createElement("div");
    slot.className = `slot enemy-slot ${slotInfo.role} ${slug ? "filled" : "empty"} ${isActive("enemy", slotInfo.key) ? "active" : ""}`;
    slot.tabIndex = 0;
    slot.addEventListener("click", () => activateSlot("enemy", slotInfo.key));

    slot.innerHTML = `
      <div>
        <div class="slot-meta">Enemy ${escapeHtml(slotInfo.label)}</div>
        <div class="slot-main">
          ${heroIconMarkup(hero, "slot-icon")}
          <div class="slot-name">${hero ? escapeHtml(hero.name) : "Empty"}</div>
        </div>
      </div>
      <div>
        <div class="role-bar ${slotInfo.role}"></div>
        <div class="slot-actions">
          <button class="tiny-button carry-button ${slug && setup.carry_targets.includes(slug) ? "active" : ""}" type="button" ${slug ? "" : "disabled"}>Carry</button>
          <button class="tiny-button clear-button" type="button" ${slug ? "" : "disabled"}>Clear</button>
        </div>
      </div>
    `;

    slot.querySelector(".carry-button").addEventListener("click", (event) => {
      event.stopPropagation();
      if (slug) toggleCarry(slug);
    });
    slot.querySelector(".clear-button").addEventListener("click", (event) => {
      event.stopPropagation();
      setEnemy(slotInfo.key, null);
    });
    els.enemySlots.appendChild(slot);
  });

  els.enemyCount.textContent = `${filledCount(setup.enemy_team)}/5`;
}

function renderTeamSlots() {
  els.teamSlots.innerHTML = "";
  TEAM_SLOTS.forEach((slotInfo) => {
    const slug = setup.my_team[slotInfo.key];
    const hero = slug ? catalog.heroes[slug] : null;
    const locked = Boolean(setup.locked_slots[slotInfo.key]);
    const slot = document.createElement("div");
    slot.className = `slot team-slot ${slotInfo.role} ${slug ? "filled" : "empty"} ${locked ? "locked" : "suggested"} ${isActive("team", slotInfo.key) ? "active" : ""}`;
    slot.tabIndex = 0;
    slot.addEventListener("click", () => activateSlot("team", slotInfo.key));

    slot.innerHTML = `
      <div>
        <div class="slot-meta">${locked ? "Locked" : "Suggested"} ${escapeHtml(slotInfo.label)}</div>
        <div class="slot-main">
          ${heroIconMarkup(hero, "slot-icon")}
          <div class="slot-name">${hero ? escapeHtml(hero.name) : "Empty"}</div>
        </div>
      </div>
      <div>
        <div class="role-bar ${slotInfo.role}"></div>
        <div class="slot-actions">
          <button class="tiny-button lock-button ${locked ? "active" : ""}" type="button" ${slug ? "" : "disabled"}>${locked ? "Locked" : "Lock"}</button>
          <button class="tiny-button clear-button" type="button" ${slug ? "" : "disabled"}>Clear</button>
        </div>
      </div>
    `;

    slot.querySelector(".lock-button").addEventListener("click", (event) => {
      event.stopPropagation();
      if (slug) toggleLocked(slotInfo.key);
    });
    slot.querySelector(".clear-button").addEventListener("click", (event) => {
      event.stopPropagation();
      setTeam(slotInfo.key, null, false);
    });
    els.teamSlots.appendChild(slot);
  });

  els.teamCount.textContent = `${filledCount(setup.my_team)}/5`;
}

function activateSlot(type, key) {
  activeTarget = { type, key };
  renderSlots();
  renderGridRoleFilter();
  renderActiveTarget();
  renderHeroGrid();
}

function renderGridRoleFilter() {
  const selected = activeSlotInfo().role;
  els.gridRoleFilter.querySelectorAll("button").forEach((button) => {
    button.classList.toggle("active", button.dataset.role === selected);
  });
}

function renderActiveTarget() {
  const slot = activeSlotInfo();
  const side = activeTarget.type === "enemy" ? "Enemy" : "Your";
  els.activeTarget.textContent = `Picking ${side} ${slot.label}: showing ${ROLE_LABELS[slot.role]} heroes`;
}

function renderHeroGrid() {
  const query = els.heroSearch.value.trim().toLowerCase();
  const role = activeSlotInfo().role;
  const exclude = new Set(PERSONAL_PREFERENCES_ENABLED ? catalog.preferences.exclude || [] : []);
  const heroes = catalog.hero_order
    .map((slug) => catalog.heroes[slug])
    .filter((hero) => hero.role === role)
    .filter((hero) => !query || hero.name.toLowerCase().includes(query) || hero.slug.includes(query));

  els.heroGrid.innerHTML = "";
  if (!heroes.length) {
    els.heroGrid.innerHTML = `<div class="empty-state">No ${escapeHtml(ROLE_LABELS[role])} heroes found.</div>`;
    return;
  }

  heroes.forEach((hero) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `hero-tile ${hero.role} ${exclude.has(hero.slug) ? "excluded" : ""}`;
    button.innerHTML = `
      ${heroIconMarkup(hero, "tile-mark")}
      <div class="tile-copy">
        <div class="tile-name">${escapeHtml(hero.name)}</div>
        <div class="tile-sub">
          <span class="role-badge ${hero.role}">${escapeHtml(ROLE_LABELS[hero.role])}</span>
          <span class="subrole-badge">${escapeHtml(hero.subrole || "unconfirmed")}</span>
        </div>
      </div>
    `;
    button.addEventListener("click", () => chooseHero(hero.slug));
    els.heroGrid.appendChild(button);
  });
}

function renderTeamRecommendation(data) {
  const recommendation = data.team_recommendation;
  els.resultsList.innerHTML = "";
  renderWarnings(data.warnings || []);

  if (!recommendation || !recommendation.slots.length) {
    els.resultsList.innerHTML = `<div class="empty-state">No full-stack recommendation available.</div>`;
    return;
  }

  const summary = document.createElement("article");
  summary.className = "result-card stack-summary";
  summary.innerHTML = `
    <div class="result-head">
      <div class="result-title">
        <h3>Recommended 5 Stack</h3>
        <div class="stack-chips">
          ${recommendation.slots.map(stackChipMarkup).join("")}
        </div>
      </div>
      <div class="score">${formatNumber(recommendation.total)}</div>
    </div>
  `;
  els.resultsList.appendChild(summary);

  recommendation.slots.forEach((row) => {
    const arch = row.archetypes && row.archetypes.length ? row.archetypes[0] : "";
    const card = document.createElement("article");
    card.className = `result-card ${row.role}`;
    card.innerHTML = `
      <div class="result-head">
        <div class="result-title">
          <div class="result-title-row">
            ${heroIconMarkup(catalog.heroes[row.slug], "result-icon")}
            <h3>${escapeHtml(row.slot_label)}: ${escapeHtml(row.hero)}</h3>
          </div>
          <p>
            <span class="role-badge ${row.role}">${escapeHtml(ROLE_LABELS[row.role])}</span>
            <span class="subrole-badge">${escapeHtml(row.subrole || "unconfirmed")}</span>
            ${arch ? `<span class="arch-badge ${escapeHtml(arch)}">${escapeHtml(arch)}</span>` : ""}
            <span class="subrole-badge">${row.locked ? "locked" : "suggested"}</span>
          </p>
        </div>
        <div class="score">${formatNumber(row.total)}</div>
      </div>
      <div class="metrics">
        ${metric("Counter", row.counter)}
        ${metric("Countered", row.countered)}
        ${metric("Synergy", row.synergy)}
        ${PERSONAL_PREFERENCES_ENABLED ? metric("Comfort", row.comfort) : ""}
      </div>
      <div class="contributions">
        ${row.contributions.map(contributionMarkup).join("")}
      </div>
    `;
    els.resultsList.appendChild(card);
  });
}

function renderWarnings(warnings) {
  els.warnings.innerHTML = "";
  warnings.forEach((message) => {
    const warning = document.createElement("div");
    warning.className = "warning";
    warning.textContent = message;
    els.warnings.appendChild(warning);
  });
}

function renderSettings() {
  if (!catalog || !settingsDraft) return;
  if (!PERSONAL_PREFERENCES_ENABLED) {
    els.settingsHeroSearch.disabled = true;
    els.savePreferences.disabled = true;
  }
  renderConfigFields();
  renderPreferenceList();
}

function renderConfigFields() {
  const config = settingsDraft.config;
  els.scoreWeights.innerHTML = "";
  Object.keys(SCORE_LABELS).forEach((key) => {
    els.scoreWeights.appendChild(numberField(SCORE_LABELS[key], `score-${key}`, config.weights[key], (value) => {
      config.weights[key] = value;
    }));
  });

  els.roleWeights.innerHTML = "";
  Object.keys(ROLE_LABELS).forEach((key) => {
    els.roleWeights.appendChild(numberField(ROLE_LABELS[key], `role-${key}`, config.role_weights[key], (value) => {
      config.role_weights[key] = value;
    }));
  });

  els.carryMultiplier.value = config.carry_multiplier;
  els.carryMultiplier.oninput = () => {
    settingsDraft.config.carry_multiplier = parseNumber(els.carryMultiplier.value, 0);
  };
}

function renderPreferenceList() {
  if (!PERSONAL_PREFERENCES_ENABLED) {
    els.preferenceList.innerHTML = "";
    return;
  }

  const query = els.settingsHeroSearch.value.trim().toLowerCase();
  const pref = settingsDraft.preferences;
  const excluded = new Set(pref.exclude || []);
  const heroes = catalog.hero_order
    .map((slug) => catalog.heroes[slug])
    .filter((hero) => !query || hero.name.toLowerCase().includes(query) || hero.slug.includes(query));

  els.preferenceList.innerHTML = "";
  heroes.forEach((hero) => {
    const row = document.createElement("div");
    row.className = "preference-row";
    row.innerHTML = `
      <div class="preference-name">
        <strong>${escapeHtml(hero.name)}</strong>
        <span>${escapeHtml(ROLE_LABELS[hero.role])} / ${escapeHtml(hero.subrole || "unconfirmed")}</span>
      </div>
      <label class="number-field">
        <span>Comfort</span>
        <input type="number" min="-10" max="10" step="0.5" value="${pref.comfort[hero.slug] ?? 0}">
      </label>
      <label class="check-field">
        <input type="checkbox" ${excluded.has(hero.slug) ? "checked" : ""}>
        <span>Exclude</span>
      </label>
    `;

    row.querySelector("input[type='number']").addEventListener("input", (event) => {
      const value = parseNumber(event.target.value, 0);
      if (value === 0) {
        delete pref.comfort[hero.slug];
      } else {
        pref.comfort[hero.slug] = value;
      }
    });

    row.querySelector("input[type='checkbox']").addEventListener("change", (event) => {
      const set = new Set(pref.exclude || []);
      if (event.target.checked) {
        set.add(hero.slug);
      } else {
        set.delete(hero.slug);
      }
      pref.exclude = Array.from(set);
      renderHeroGrid();
    });

    els.preferenceList.appendChild(row);
  });
}

function numberField(label, id, value, onChange) {
  const wrapper = document.createElement("label");
  wrapper.className = "number-field";
  wrapper.htmlFor = id;
  wrapper.innerHTML = `
    <span>${escapeHtml(label)}</span>
    <input id="${escapeHtml(id)}" type="number" min="0" max="10" step="0.1" value="${value}">
  `;
  wrapper.querySelector("input").addEventListener("input", (event) => {
    onChange(parseNumber(event.target.value, 0));
  });
  return wrapper;
}

function chooseHero(slug) {
  const hero = catalog.heroes[slug];
  const role = activeSlotInfo().role;
  if (!hero || hero.role !== role) return;

  if (activeTarget.type === "enemy") {
    setEnemy(activeTarget.key, slug);
    activateNextEmpty("enemy");
    return;
  }
  setTeam(activeTarget.key, slug, true);
}

function setEnemy(key, slug) {
  setup.enemy_team[key] = slug;
  setup.carry_targets = setup.carry_targets.filter((target) => target && enemySlugs().includes(target));
  saveSetup();
  renderSlots();
  queueRecommendations();
}

function setTeam(key, slug, locked) {
  setup.my_team[key] = slug;
  if (slug && locked) {
    setup.locked_slots[key] = true;
  } else {
    delete setup.locked_slots[key];
  }
  saveSetup();
  renderSlots();
  queueRecommendations();
}

function toggleLocked(key) {
  if (!setup.my_team[key]) return;
  if (setup.locked_slots[key]) {
    delete setup.locked_slots[key];
  } else {
    setup.locked_slots[key] = true;
  }
  saveSetup();
  renderSlots();
  queueRecommendations();
}

function toggleCarry(slug) {
  const set = new Set(setup.carry_targets);
  if (set.has(slug)) {
    set.delete(slug);
  } else {
    set.add(slug);
  }
  setup.carry_targets = Array.from(set).filter((target) => enemySlugs().includes(target));
  saveSetup();
  renderSlots();
  queueRecommendations();
}

function activateNextEmpty(type) {
  const team = type === "enemy" ? setup.enemy_team : setup.my_team;
  const currentIndex = TEAM_SLOTS.findIndex((slot) => slot.key === activeTarget.key);
  const next = TEAM_SLOTS.find((slot, index) => index > currentIndex && !team[slot.key]);
  if (next) activateSlot(type, next.key);
}

function queueRecommendations() {
  window.clearTimeout(recommendTimer);
  recommendTimer = window.setTimeout(requestRecommendations, 180);
}

async function requestRecommendations() {
  if (!catalog) return;
  setStatus("Building");
  try {
    const data = await api("/api/recommend-team", {
      method: "POST",
      body: JSON.stringify(buildPayload()),
    });
    applyTeamRecommendation(data.team_recommendation);
    renderTeamRecommendation(data);
    setStatus("Ready", "good");
  } catch (err) {
    setStatus("Issue", "bad");
    renderError(err.message);
  }
}

function applyTeamRecommendation(recommendation) {
  if (!recommendation || !recommendation.team) return;
  TEAM_SLOTS.forEach((slot) => {
    const locked = setup.locked_slots[slot.key];
    if (!locked && recommendation.team[slot.key]) {
      setup.my_team[slot.key] = recommendation.team[slot.key];
    }
  });
  saveSetup();
  renderTeamSlots();
}

function buildPayload() {
  const lockedTeam = {};
  TEAM_SLOTS.forEach((slot) => {
    const slug = setup.my_team[slot.key];
    if (slug && setup.locked_slots[slot.key]) lockedTeam[slot.key] = slug;
  });

  return {
    enemy_team: compactTeam(setup.enemy_team),
    my_team: lockedTeam,
    carry_targets: setup.carry_targets.filter((slug) => enemySlugs().includes(slug)),
    top: setup.top,
  };
}

async function saveConfig() {
  setSaveMessage(els.configSaveMessage, "Saving");
  try {
    const payload = {
      weights: settingsDraft.config.weights,
      role_weights: settingsDraft.config.role_weights,
      carry_multiplier: settingsDraft.config.carry_multiplier,
    };
    const data = await api("/api/config", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    catalog.config = data.config;
    settingsDraft.config = clone(data.config);
    setSaveMessage(els.configSaveMessage, "Saved");
    await requestRecommendations();
  } catch (err) {
    setSaveMessage(els.configSaveMessage, err.message);
  }
}

async function savePreferences() {
  if (!PERSONAL_PREFERENCES_ENABLED) {
    setSaveMessage(els.prefSaveMessage, "Disabled");
    return;
  }

  setSaveMessage(els.prefSaveMessage, "Saving");
  try {
    const data = await api("/api/preferences", {
      method: "PUT",
      body: JSON.stringify(settingsDraft.preferences),
    });
    catalog.preferences = data.preferences;
    settingsDraft.preferences = clone(data.preferences);
    renderHeroGrid();
    renderPreferenceList();
    setSaveMessage(els.prefSaveMessage, "Saved");
    await requestRecommendations();
  } catch (err) {
    setSaveMessage(els.prefSaveMessage, err.message);
  }
}

function setSaveMessage(el, text) {
  el.textContent = text;
  if (text === "Saved") {
    window.setTimeout(() => {
      if (el.textContent === "Saved") el.textContent = "";
    }, 1800);
  }
}

function normalizeSetup() {
  if (Array.isArray(setup.enemySlots) && !setup.enemy_team) {
    setup.enemy_team = {};
    TEAM_SLOTS.forEach((slot, index) => {
      setup.enemy_team[slot.key] = setup.enemySlots[index] || null;
    });
  }

  setup.enemy_team = setup.enemy_team && typeof setup.enemy_team === "object" ? setup.enemy_team : {};
  setup.my_team = setup.my_team && typeof setup.my_team === "object" ? setup.my_team : {};
  setup.locked_slots = setup.locked_slots && typeof setup.locked_slots === "object" ? setup.locked_slots : {};

  TEAM_SLOTS.forEach((slot) => {
    if (!(slot.key in setup.enemy_team)) setup.enemy_team[slot.key] = null;
    if (!(slot.key in setup.my_team)) setup.my_team[slot.key] = null;
    if (setup.enemy_team[slot.key] && catalog.heroes[setup.enemy_team[slot.key]]?.role !== slot.role) {
      setup.enemy_team[slot.key] = null;
    }
    if (setup.my_team[slot.key] && catalog.heroes[setup.my_team[slot.key]]?.role !== slot.role) {
      setup.my_team[slot.key] = null;
      delete setup.locked_slots[slot.key];
    }
  });

  setup.carry_targets = Array.isArray(setup.carry_targets)
    ? setup.carry_targets.filter((slug) => enemySlugs().includes(slug))
    : [];
}

function loadSetup() {
  try {
    const raw = window.localStorage.getItem("ow-counterpick-setup");
    return raw ? { ...clone(DEFAULT_SETUP), ...JSON.parse(raw) } : clone(DEFAULT_SETUP);
  } catch {
    return clone(DEFAULT_SETUP);
  }
}

function saveSetup() {
  window.localStorage.setItem("ow-counterpick-setup", JSON.stringify(setup));
  els.saveState.textContent = "Saved locally";
}

function activeSlotInfo() {
  return TEAM_SLOTS.find((slot) => slot.key === activeTarget.key) || TEAM_SLOTS[0];
}

function isActive(type, key) {
  return activeTarget.type === type && activeTarget.key === key;
}

function filledCount(team) {
  return TEAM_SLOTS.filter((slot) => team[slot.key]).length;
}

function enemySlugs() {
  return TEAM_SLOTS.map((slot) => setup.enemy_team[slot.key]).filter(Boolean);
}

function compactTeam(team) {
  const compact = {};
  TEAM_SLOTS.forEach((slot) => {
    if (team[slot.key]) compact[slot.key] = team[slot.key];
  });
  return compact;
}

function metric(label, value) {
  return `
    <div class="metric">
      <span>${escapeHtml(label)}</span>
      <strong>${formatNumber(value)}</strong>
    </div>
  `;
}

function contributionMarkup(item) {
  const carry = item.is_carry ? " carry" : "";
  return `
    <div class="contribution-row">
      <strong>${escapeHtml(item.enemy_name)}${carry}</strong>
      <span>for ${formatNumber(item.counter)}</span>
      <span>back ${formatNumber(item.countered)}</span>
    </div>
  `;
}

function stackChipMarkup(row) {
  const hero = catalog.heroes[row.slug];
  return `
    <span class="stack-chip ${escapeHtml(row.role)}">
      ${hero && hero.icon ? `<img src="${escapeHtml(hero.icon)}" alt="" loading="lazy">` : ""}
      <span>${escapeHtml(row.slot_label)}</span>
      <strong>${escapeHtml(row.hero)}</strong>
    </span>
  `;
}

function renderError(message) {
  els.warnings.innerHTML = `<div class="warning">${escapeHtml(message)}</div>`;
  els.resultsList.innerHTML = `<div class="empty-state">No results.</div>`;
}

function heroIconMarkup(hero, className) {
  if (!hero) {
    return `<div class="${className} empty-icon">?</div>`;
  }
  if (hero.icon) {
    return `<img class="${className}" src="${escapeHtml(hero.icon)}" alt="" loading="lazy">`;
  }
  return `<div class="${className}">${escapeHtml(initials(hero.name))}</div>`;
}

function setStatus(text, tone = "") {
  els.apiStatus.textContent = text;
  els.apiStatus.className = `status-pill ${tone}`.trim();
}

function initials(name) {
  const cleaned = name.replace(/[^a-z0-9 ]/gi, " ").trim();
  const parts = cleaned.split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

function formatNumber(value) {
  const number = Number(value || 0);
  return Number.isInteger(number) ? String(number) : number.toFixed(2).replace(/0$/, "").replace(/\.0$/, "");
}

function parseNumber(value, fallback) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
