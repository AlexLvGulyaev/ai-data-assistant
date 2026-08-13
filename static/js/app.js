const setupComposer = () => {
    const textarea = document.getElementById("message-text");
    const fileInput = document.getElementById("data-file");
    const filePill = document.getElementById("selected-file-pill");
    const thread = document.getElementById("chat-thread");

    if (textarea) {
        const resize = () => {
            textarea.style.height = "auto";
            textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
        };

        resize();
        textarea.addEventListener("input", resize);

        document.querySelectorAll("[data-prompt]").forEach((button) => {
            button.addEventListener("click", () => {
                textarea.value = button.dataset.prompt || "";
                textarea.focus();
                resize();
            });
        });
    }

    if (fileInput && filePill) {
        const syncFilePill = () => {
            const file = fileInput.files?.[0];
            if (!file) {
                filePill.hidden = true;
                filePill.textContent = "";
                return;
            }

            filePill.hidden = false;
            filePill.textContent = `Выбрано: ${file.name}`;
        };

        fileInput.addEventListener("change", syncFilePill);
        syncFilePill();
    }

    if (thread) {
        thread.scrollTop = thread.scrollHeight;
    }

    // Quick-grid chart picker: «Построить график» раскрывает ряд чипов типа графика.
    // Чипы — отдельные HTMX-формы; тоггл чисто визуальный (show/hide ряда).
    document.querySelectorAll(".chart-picker__toggle").forEach((toggle) => {
        if (toggle.dataset.bound === "1") return;
        toggle.dataset.bound = "1";
        toggle.addEventListener("click", () => {
            const chips = toggle.parentElement.querySelector(".chart-picker__chips");
            if (!chips) return;
            const willOpen = chips.hidden;
            chips.hidden = !willOpen;
            toggle.classList.toggle("is-open", willOpen);
            toggle.setAttribute("aria-expanded", String(willOpen));
        });
    });
};

/* ── Индикация длительных запросов ──────────────────────────────────────
   Три уровня обратной связи на время htmx-запроса к AI/графику/отчёту:
   1) пилюля-лоадер (правый нижний угол) со спиннером + живым таймером;
   2) инлайн «AI печатает» (три точки) прямо в чате — только для запросов,
      где модель реально думает (POST /chat/{id}/message, /actions/*);
   3) блокировка ввода (composer + быстрые кнопки + файл-чипы) — чтобы
      было ясно, что система занята; скролл чата остаётся доступным.
   Счётчик in-flight запросов защищает от рассинхрона при наложенных вызовах.
   ──────────────────────────────────────────────────────────────────────── */

let busyCount = 0;
let timerInterval = null;
let timerStart = null;

const toggleLoader = (show) => {
    const globalLoader = document.getElementById("global-loader");
    if (!globalLoader) {
        return;
    }
    globalLoader.style.display = show ? "inline-flex" : "none";
};

const startTimer = () => {
    const secs = document.getElementById("loader-seconds");
    if (!secs) {
        return;
    }
    timerStart = Date.now();
    secs.textContent = "0с";
    if (timerInterval) {
        clearInterval(timerInterval);
    }
    timerInterval = setInterval(() => {
        const elapsed = Math.floor((Date.now() - timerStart) / 1000);
        secs.textContent = `${elapsed}с`;
    }, 250);
};

const stopTimer = () => {
    if (timerInterval) {
        clearInterval(timerInterval);
        timerInterval = null;
    }
};

const setBusy = (busy) => {
    const shell = document.getElementById("page-shell");
    if (!shell) {
        return;
    }
    shell.classList.toggle("is-busy", busy);
    shell.querySelectorAll('button, textarea, input[type="file"]').forEach((el) => {
        if (busy) {
            el.dataset.previouslyDisabled = el.disabled ? "1" : "0";
            el.disabled = true;
        } else if (el.dataset.previouslyDisabled !== undefined) {
            el.disabled = el.dataset.previouslyDisabled === "1";
            delete el.dataset.previouslyDisabled;
        }
    });
};

const isAiTurn = (path) => /\/chat\/[^/]+\/message(\/|$)/.test(path) || /\/actions\//.test(path);

const showTyping = () => {
    const thread = document.getElementById("chat-thread");
    if (!thread || thread.querySelector(".is-typing")) {
        return;
    }
    const node = document.createElement("article");
    node.className = "message message--assistant is-typing";
    node.setAttribute("aria-live", "polite");
    node.innerHTML =
        '<div class="message__avatar">AI</div>' +
        '<div class="message__body"><div class="typing-dots"><span></span><span></span><span></span></div></div>';
    thread.appendChild(node);
    thread.scrollTop = thread.scrollHeight;
};

const hideTyping = () => {
    document.querySelectorAll("#chat-thread .is-typing").forEach((n) => n.remove());
};

const enterBusy = () => {
    toggleLoader(true);
    startTimer();
    setBusy(true);
};

const exitBusy = () => {
    toggleLoader(false);
    stopTimer();
    setBusy(false);
    hideTyping();
};

document.addEventListener("DOMContentLoaded", () => {
    setupComposer();
    setupAdmin();

    document.body.addEventListener("htmx:beforeRequest", (e) => {
        busyCount += 1;
        if (busyCount === 1) {
            enterBusy();
        }
        const path = e.detail?.requestConfig?.path || "";
        if (isAiTurn(path)) {
            showTyping();
        }
    });

    document.body.addEventListener("htmx:afterRequest", () => {
        busyCount = Math.max(0, busyCount - 1);
        if (busyCount === 0) {
            exitBusy();
        }
    });

    document.body.addEventListener("htmx:afterSwap", () => {
        // Свежий #page-shell уже в DOM — сбрасываем счётчик и перевязываем composer.
        busyCount = 0;
        exitBusy();
        setupComposer();
        setupAdmin();
    });
});

/* ── Админка оператора ─────────────────────────────────────────────────
   1) Единая кнопка «Сохранить настройки» в шапке живёт вне формы —
      сабмитит общую форму через requestSubmit() (htmx перехватывает submit).
   2) Чипы пресетов провайдера НЕ сабмитят: клик лишь заполняет 4 поля и
      скрытый input provider, активный чип подсвечивается. Запись — общим
      «Сохранить».
   3) Тултипы параметров рендерятся фиксированным оверлеем (не absolute
      внутри карточки) — иначе их клиппит overflow:auto боковой колонки, и
      подсказки не видны. ──────────────────────────────────────────────── */

const setupAdmin = () => {
    // Кнопка сохранения (вне формы).
    const saveBtn = document.getElementById("admin-save-btn");
    const form = document.getElementById("admin-settings-form");
    if (saveBtn && form && saveBtn.dataset.bound !== "1") {
        saveBtn.dataset.bound = "1";
        saveBtn.addEventListener("click", () => form.requestSubmit());
    }

    // Чипы пресетов — заполняют поля, без сабмита.
    document.querySelectorAll(".js-preset-chip").forEach((chip) => {
        if (chip.dataset.bound === "1") return;
        chip.dataset.bound = "1";
        chip.addEventListener("click", () => {
            const f = document.getElementById("admin-settings-form");
            if (!f) return;
            const setVal = (name, val) => {
                const el = f.querySelector(`[name="${name}"]`);
                if (el) el.value = val;
            };
            setVal("openai_base_url", chip.dataset.baseUrl || "");
            setVal("openai_model", chip.dataset.model || "");
            setVal("provider_name", chip.dataset.name || "");
            const sel = f.querySelector('[name="structured_output"]');
            if (sel) sel.value = chip.dataset.structured === "true" ? "true" : "false";
            setVal("provider", chip.dataset.provider || "");
            document.querySelectorAll(".js-preset-chip").forEach((c) =>
                c.classList.toggle("preset-chip--active", c === chip)
            );
        });
    });

    setupAdminTooltips();
};

let adminTooltipsBound = false;

const setupAdminTooltips = () => {
    if (adminTooltipsBound) return;
    if (!document.getElementById("admin-settings-form")) return;
    adminTooltipsBound = true;

    const tip = document.createElement("div");
    tip.id = "admin-tooltip-floating";
    tip.className = "admin-tooltip-floating";
    tip.style.display = "none";
    document.body.appendChild(tip);

    const show = (target) => {
        const src = target.querySelector(".admin-tooltip__text");
        if (!src) return;
        tip.textContent = src.textContent;
        tip.style.display = "block";
        const r = target.getBoundingClientRect();
        const tw = tip.offsetWidth;
        const th = tip.offsetHeight;
        let left = r.left + r.width / 2 - tw / 2;
        let top = r.top - th - 8;
        if (top < 8) top = r.bottom + 8; // мало места сверху → показываем снизу
        left = Math.max(8, Math.min(left, window.innerWidth - tw - 8));
        tip.style.left = `${left}px`;
        tip.style.top = `${top}px`;
    };
    const hide = () => { tip.style.display = "none"; };

    document.addEventListener("mouseover", (e) => {
        const t = e.target.closest ? e.target.closest(".admin-tooltip") : null;
        if (t) show(t);
    });
    document.addEventListener("mouseout", (e) => {
        const t = e.target.closest ? e.target.closest(".admin-tooltip") : null;
        if (t) hide();
    });
    window.addEventListener("scroll", hide, true);
};