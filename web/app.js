const API = '';
const USER_ID = 'user_' + (localStorage.getItem('fitUserId') || (() => {
    const id = Math.random().toString(36).slice(2, 10);
    localStorage.setItem('fitUserId', id);
    return id;
})());

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

let selectedImage = null;
let sending = false;

// Auto-resize textarea
messageInput.addEventListener('input', () => {
    messageInput.style.height = 'auto';
    messageInput.style.height = Math.min(messageInput.scrollHeight, 120) + 'px';
});

// Send on Enter (Shift+Enter for newline)
messageInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        send();
    }
});

sendBtn.addEventListener('click', send);

// Image handling
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

// Profile modal
profileBtn.addEventListener('click', async () => {
    profileModal.classList.remove('hidden');
    try {
        const res = await fetch(`${API}/api/user/${USER_ID}`);
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
    } catch {}
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
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        profileModal.classList.add('hidden');
        addMessage('assistant', 'Профиль обновлён!');
    } catch {
        addMessage('assistant', 'Ошибка при сохранении профиля.');
    }
});

async function send() {
    if (sending) return;
    const text = messageInput.value.trim();
    if (!text && !selectedImage) return;

    sending = true;
    sendBtn.disabled = true;

    // Show user message
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

            response = await fetch(`${API}/api/chat/image`, { method: 'POST', body: fd });
            selectedImage = null;
            imageInput.value = '';
            imagePreview.classList.add('hidden');
        } else {
            response = await fetch(`${API}/api/chat`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
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

function addMessage(role, text, imageUrl) {
    const div = document.createElement('div');
    div.className = `message ${role}`;

    let html = '';
    if (imageUrl) {
        html += `<img class="message-image" src="${imageUrl}" alt="food photo">`;
    }
    html += formatMessage(text);

    div.innerHTML = `<div class="message-content">${html}</div>`;
    chat.appendChild(div);
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
    div.innerHTML = `<div class="message-content"><div class="typing"><span></span><span></span><span></span></div></div>`;
    chat.appendChild(div);
    chat.scrollTop = chat.scrollHeight;
    return div;
}
