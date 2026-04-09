const API = '';
const API_SECRET = window.__FIT_API_SECRET || '';

function _getOrCreateUserId() {
    const stored = localStorage.getItem('fitUserId');
    if (stored) return stored;
    const id = crypto.randomUUID().replace(/-/g, '').slice(0, 16);
    localStorage.setItem('fitUserId', id);
    return id;
}
const USER_ID = 'user_' + _getOrCreateUserId();

function _headers(extra = {}) {
    const h = { 'X-Api-Secret': API_SECRET, ...extra };
    return h;
}

function _jsonHeaders() {
    return _headers({ 'Content-Type': 'application/json' });
}

const chat = document.getElementById('chat');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const imageInput = document.getElementById('imageInput');
const imagePreview = document.getElementById('imagePreview');
const previewImg = document.getElementById('previewImg');
const weightInput = document.getElementById('weightInput');
const removeImage = document.getElementById('removeImage');
const profileBtn = document.getElementById('profileBtn');
const profileModal = document.getElementById('profileModal');
const closeProfile = document.getElementById('closeProfile');
const profileForm = document.getElementById('profileForm');
const inputArea = document.getElementById('inputArea');
const onboardingProgress = document.getElementById('onboardingProgress');
const progressLabel = document.getElementById('progressLabel');

let selectedImage = null;
let sending = false;

// ── Onboarding ──────────────────────────────────────────────────────────

const ONBOARDING_STEPS = [
    {
        key: 'goal',
        message: 'Чтобы составить план специально для тебя — скажи, какая у тебя цель?',
        label: 'Цель',
        options: [
            { value: 'lose',     label: '🔥 Похудение',    display: 'Похудение' },
            { value: 'gain',     label: '💪 Набор массы',   display: 'Набор массы' },
            { value: 'maintain', label: '❤️ Здоровье',      display: 'Здоровье' },
        ],
    },
    {
        key: 'level',
        message: 'Какой у тебя уровень подготовки?',
        label: 'Уровень',
        options: [
            { value: 'beginner',     label: '🌱 Новичок',      display: 'Новичок' },
            { value: 'intermediate', label: '🏃 Средний',      display: 'Средний' },
            { value: 'advanced',     label: '🏆 Продвинутый',  display: 'Продвинутый' },
        ],
    },
    {
        key: 'days',
        message: 'Сколько дней в неделю готов тренироваться?',
        label: 'График',
        options: [
            { value: '2', label: '2 дня', display: '2 дня' },
            { value: '3', label: '3 дня', display: '3 дня' },
            { value: '4', label: '4 дня', display: '4 дня' },
            { value: '5', label: '5 дней', display: '5 дней' },
            { value: '6', label: '6 дней', display: '6 дней' },
        ],
    },
];

let onboardingStep = 0;
let onboardingData = {};

function isOnboardingComplete() {
    return localStorage.getItem('fitOnboarded') === 'true';
}

function markOnboardingComplete() {
    localStorage.setItem('fitOnboarded', 'true');
}

function updateProgressIndicator(step) {
    const dots = onboardingProgress.querySelectorAll('.step-dot');
    const lines = onboardingProgress.querySelectorAll('.step-line');

    dots.forEach((dot, i) => {
        dot.classList.remove('active', 'done');
        if (i < step) dot.classList.add('done');
        else if (i === step) dot.classList.add('active');
    });

    lines.forEach((line, i) => {
        line.classList.toggle('done', i < step);
    });

    progressLabel.textContent = `Шаг ${step + 1} из ${ONBOARDING_STEPS.length}`;
}

function hideProgressIndicator() {
    onboardingProgress.classList.add('hidden');
}

function showProgressIndicator() {
    onboardingProgress.classList.remove('hidden');
}

function showOnboardingStep(step) {
    const s = ONBOARDING_STEPS[step];
    updateProgressIndicator(step);

    const delay = step === 0 ? 0 : 350;
    setTimeout(() => {
        addMessage('assistant', s.message);

        setTimeout(() => {
            addQuickReplies(s.options, (opt) => {
                onboardingData[s.key] = opt.value;
                addMessage('user', opt.display);
                onboardingStep = step + 1;

                if (onboardingStep < ONBOARDING_STEPS.length) {
                    showOnboardingStep(onboardingStep);
                } else {
                    finishOnboarding();
                }
            });
        }, 100);
    }, delay);
}

async function finishOnboarding() {
    hideProgressIndicator();
    inputArea.classList.remove('disabled-during-onboarding');
    markOnboardingComplete();

    const goalMap = { lose: 'похудение', gain: 'набор массы', maintain: 'поддержание здоровья' };
    const levelMap = { beginner: 'новичок', intermediate: 'средний', advanced: 'продвинутый' };

    try {
        await fetch(`${API}/api/user`, {
            method: 'POST',
            headers: _jsonHeaders(),
            body: JSON.stringify({
                user_id: USER_ID,
                goal: onboardingData.goal,
            }),
        });
    } catch (err) {
        console.warn('Profile save failed during onboarding:', err);
    }

    const prompt =
        `Моя цель — ${goalMap[onboardingData.goal] || onboardingData.goal}. ` +
        `Уровень подготовки — ${levelMap[onboardingData.level] || onboardingData.level}. ` +
        `Готов тренироваться ${onboardingData.days} дней в неделю. ` +
        `Составь мне программу тренировок!`;

    addMessage('user', prompt);
    const typingEl = showTyping();

    try {
        const response = await fetch(`${API}/api/chat`, {
            method: 'POST',
            headers: _jsonHeaders(),
            body: JSON.stringify({ message: prompt, user_id: USER_ID }),
        });
        const data = await response.json();
        typingEl.remove();
        addMessage('assistant', data.response || 'Ошибка получения ответа.');
    } catch (err) {
        typingEl.remove();
        addMessage('assistant', `Ошибка: ${err.message}. Убедитесь что сервер запущен.`);
    }
}

function startApp() {
    if (isOnboardingComplete()) {
        hideProgressIndicator();
        addMessage('assistant', 'С возвращением! Чем могу помочь?');
    } else {
        inputArea.classList.add('disabled-during-onboarding');
        showProgressIndicator();
        showOnboardingStep(0);
    }
}

// ── Avatars ─────────────────────────────────────────────────────────────

const BOT_AVATAR_HTML = '<div class="avatar bot-avatar">🏋️</div>';
const USER_AVATAR_HTML =
    '<div class="avatar user-avatar">' +
    '<svg viewBox="0 0 24 24"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>' +
    '</div>';

// ── Messages ────────────────────────────────────────────────────────────

function addMessage(role, text, imageUrl) {
    const div = document.createElement('div');
    div.className = `message ${role}`;

    const avatar = role === 'assistant' ? BOT_AVATAR_HTML : USER_AVATAR_HTML;

    let contentHtml = '';
    if (imageUrl) {
        contentHtml += `<img class="message-image" src="${imageUrl}" alt="photo">`;
    }
    contentHtml += formatMessage(text);

    div.innerHTML = `${avatar}<div class="message-content">${contentHtml}</div>`;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
    return div;
}

function addQuickReplies(options, callback) {
    const wrap = document.createElement('div');
    wrap.className = 'quick-replies';

    options.forEach((opt) => {
        const btn = document.createElement('button');
        btn.className = 'quick-reply-btn';
        btn.textContent = opt.label;
        btn.addEventListener('click', () => {
            wrap.querySelectorAll('.quick-reply-btn').forEach((b) => {
                if (b === btn) b.classList.add('selected');
                else b.classList.add('faded');
            });
            setTimeout(() => {
                wrap.remove();
                callback(opt);
            }, 200);
        });
        wrap.appendChild(btn);
    });

    chat.appendChild(wrap);
    chat.scrollTop = chat.scrollHeight;
}

function formatMessage(text) {
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/`(.*?)`/g, '<code>$1</code>')
        .replace(/\n/g, '<br>');
}

function showTyping() {
    const div = document.createElement('div');
    div.className = 'message assistant';
    div.innerHTML =
        `${BOT_AVATAR_HTML}<div class="message-content"><div class="typing"><span></span><span></span><span></span></div></div>`;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
    return div;
}

// ── Auto-resize textarea ────────────────────────────────────────────────

messageInput.addEventListener('input', () => {
    messageInput.style.height = 'auto';
    messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + 'px';
});

messageInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        send();
    }
});

sendBtn.addEventListener('click', send);

// ── Image handling ──────────────────────────────────────────────────────

imageInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (!file) return;
    selectedImage = file;
    previewImg.src = URL.createObjectURL(file);
    imagePreview.classList.remove('hidden');
});

removeImage.addEventListener('click', () => {
    selectedImage = null;
    imageInput.value = '';
    imagePreview.classList.add('hidden');
});

// ── Profile modal ───────────────────────────────────────────────────────

profileBtn.addEventListener('click', async () => {
    profileModal.classList.remove('hidden');
    try {
        const res = await fetch(`${API}/api/user/${USER_ID}`, { headers: _headers() });
        if (res.ok) {
            const data = await res.json();
            const u = data.user;
            const form = profileForm;
            if (u.name) form.name.value = u.name;
            if (u.age) form.age.value = u.age;
            if (u.height) form.height.value = u.height;
            if (u.weight) form.weight.value = u.weight;
            if (u.gender) form.gender.value = u.gender;
            if (u.activity) form.activity.value = u.activity;
            if (u.goal) form.goal.value = u.goal;
        }
    } catch (err) {
        console.warn('Failed to load profile:', err);
    }
});

closeProfile.addEventListener('click', () => profileModal.classList.add('hidden'));
profileModal.addEventListener('click', (e) => {
    if (e.target === profileModal) profileModal.classList.add('hidden');
});

profileForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(profileForm);
    const body = { user_id: USER_ID };
    for (const [k, v] of fd.entries()) {
        if (v) body[k] = isNaN(v) ? v : Number(v);
    }
    try {
        await fetch(`${API}/api/user`, {
            method: 'POST',
            headers: _jsonHeaders(),
            body: JSON.stringify(body),
        });
        profileModal.classList.add('hidden');
        addMessage('assistant', 'Профиль обновлён!');
    } catch {
        addMessage('assistant', 'Ошибка при сохранении профиля.');
    }
});

// ── Send ────────────────────────────────────────────────────────────────

async function send() {
    if (sending) return;
    const text = messageInput.value.trim();
    if (!text && !selectedImage) return;

    sending = true;
    sendBtn.disabled = true;

    if (selectedImage) {
        const imgUrl = URL.createObjectURL(selectedImage);
        addMessage('user', text || 'Что это за блюдо?', imgUrl);
    } else {
        addMessage('user', text);
    }

    messageInput.value = '';
    messageInput.style.height = 'auto';

    const typingEl = showTyping();

    try {
        let response;
        if (selectedImage) {
            const fd = new FormData();
            fd.append('image', selectedImage);
            fd.append('message', text || 'Что это за блюдо?');
            fd.append('user_id', USER_ID);
            fd.append('weight_grams', weightInput.value || '300');

            response = await fetch(`${API}/api/chat/image`, {
                method: 'POST',
                headers: _headers(),
                body: fd,
            });
            selectedImage = null;
            imageInput.value = '';
            imagePreview.classList.add('hidden');
        } else {
            response = await fetch(`${API}/api/chat`, {
                method: 'POST',
                headers: _jsonHeaders(),
                body: JSON.stringify({ message: text, user_id: USER_ID }),
            });
        }

        const data = await response.json();
        typingEl.remove();
        addMessage('assistant', data.response || 'Ошибка получения ответа.');
    } catch (err) {
        typingEl.remove();
        addMessage('assistant', `Ошибка: ${err.message}. Убедитесь что сервер запущен.`);
    }

    sending = false;
    sendBtn.disabled = false;
    messageInput.focus();
}

// ── Init ────────────────────────────────────────────────────────────────

startApp();
