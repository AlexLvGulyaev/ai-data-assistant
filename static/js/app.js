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
    });
});