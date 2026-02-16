/* ══════════════════════════════════════
   Schedule page — JavaScript
   ══════════════════════════════════════ */

// ── Навигация ──

function changeOrg(orgId) {
    const params = new URLSearchParams(window.location.search);
    params.set('org_id', orgId);
    window.location.href = '/schedule?' + params.toString();
}

function changeDate(dateStr) {
    const params = new URLSearchParams(window.location.search);
    params.set('day', dateStr);
    window.location.href = '/schedule?' + params.toString();
}

function toggleCancelled(checked) {
    const params = new URLSearchParams(window.location.search);
    params.set('show_cancelled', checked ? 'true' : 'false');
    window.location.href = '/schedule?' + params.toString();
}

// ── Клик по дате для открытия нативного date-picker ──

document.addEventListener('DOMContentLoaded', function () {
    const dateFormatted = document.querySelector('.date-formatted');
    const datePicker = document.getElementById('datePicker');

    if (dateFormatted && datePicker) {
        dateFormatted.addEventListener('click', function () {
            datePicker.showPicker ? datePicker.showPicker() : datePicker.click();
        });
    }

    // Горизонтальный свайп для смены дня (мобиль)
    setupSwipe();

    // Подсветка текущего времени
    highlightCurrentTime();
    setInterval(highlightCurrentTime, 60000);
});

// ── Модальное окно деталей ──

function showBooking(bookingId) {
    const modal = document.getElementById('bookingModal');
    const body = document.getElementById('bookingDetails');

    if (!window.SCHEDULE_DATA || !window.SCHEDULE_DATA.spans) {
        body.innerHTML = '<p>Данные недоступны</p>';
        modal.style.display = 'flex';
        return;
    }

    const sp = window.SCHEDULE_DATA.spans[String(bookingId)];
    if (!sp) {
        body.innerHTML = '<p>Бронирование не найдено</p>';
        modal.style.display = 'flex';
        return;
    }

    const b = sp.booking;

    const kindLabel = b.activity === 'PD' ? 'ПД (Предпринимательская деятельность)'
                    : b.activity === 'GZ' ? 'ГЗ (Государственное задание)'
                    : b.activity;

    const statusMap = {
        'planned':   { label: 'Запланировано', css: 'status-planned' },
        'done':      { label: 'Проведено',     css: 'status-done' },
        'cancelled': { label: 'Отменено',      css: 'status-cancelled' },
    };
    const st = statusMap[b.status] || { label: b.status, css: '' };

    const tenantName = b.activity === 'GZ'
        ? (b.gz_group_name || '—')
        : (b.tenant_name || '—');

    const startDate = new Date(b.starts_at);
    const endDate = new Date(b.ends_at);
    const dateStr = startDate.toLocaleDateString('ru-RU');
    const timeStr = startDate.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
                  + ' – '
                  + endDate.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });

    // Длительность в минутах
    const durationMin = Math.round((endDate - startDate) / 60000);
    const durationStr = durationMin >= 60
        ? Math.floor(durationMin / 60) + ' ч ' + (durationMin % 60 ? (durationMin % 60) + ' мин' : '')
        : durationMin + ' мин';

    body.innerHTML = `
        <div class="detail-row">
            <span class="detail-label">Дата</span>
            <span class="detail-value">${dateStr}</span>
        </div>
        <div class="detail-row">
            <span class="detail-label">Время</span>
            <span class="detail-value">${timeStr}</span>
        </div>
        <div class="detail-row">
            <span class="detail-label">Длительность</span>
            <span class="detail-value">${durationStr}</span>
        </div>
        <div class="detail-row">
            <span class="detail-label">Тип</span>
            <span class="detail-value">${kindLabel}</span>
        </div>
        <div class="detail-row">
            <span class="detail-label">${b.activity === 'GZ' ? 'Группа' : 'Арендатор'}</span>
            <span class="detail-value">${tenantName}</span>
        </div>
        <div class="detail-row">
            <span class="detail-label">Событие</span>
            <span class="detail-value">${b.title || '—'}</span>
        </div>
        <div class="detail-row">
            <span class="detail-label">Статус</span>
            <span class="detail-value">
                <span class="status-badge ${st.css}">${st.label}</span>
            </span>
        </div>
        ${b.comment ? `
        <div class="detail-row">
            <span class="detail-label">Комментарий</span>
            <span class="detail-value">${b.comment}</span>
        </div>
        ` : ''}
    `;

    modal.style.display = 'flex';

    // Закрытие по Escape
    document.addEventListener('keydown', closeOnEscape);
}

function closeModal() {
    document.getElementById('bookingModal').style.display = 'none';
    document.removeEventListener('keydown', closeOnEscape);
}

function closeOnEscape(e) {
    if (e.key === 'Escape') closeModal();
}

// ── Свайп для мобилки (лево/право = день) ──

function setupSwipe() {
    let touchStartX = 0;
    let touchStartY = 0;
    const wrap = document.querySelector('.schedule-wrap');
    if (!wrap) return;

    wrap.addEventListener('touchstart', function (e) {
        touchStartX = e.changedTouches[0].screenX;
        touchStartY = e.changedTouches[0].screenY;
    }, { passive: true });

    wrap.addEventListener('touchend', function (e) {
        const dx = e.changedTouches[0].screenX - touchStartX;
        const dy = e.changedTouches[0].screenY - touchStartY;

        // горизонтальный свайп > 80px и больше чем вертикальный
        if (Math.abs(dx) > 80 && Math.abs(dx) > Math.abs(dy) * 1.5) {
            // Если таблица скроллится горизонтально — не переключаем день
            if (wrap.scrollWidth > wrap.clientWidth + 10) {
                const atLeft = wrap.scrollLeft <= 5;
                const atRight = wrap.scrollLeft >= wrap.scrollWidth - wrap.clientWidth - 5;

                if (dx > 0 && !atLeft) return;  // свайп вправо, но таблица не в начале
                if (dx < 0 && !atRight) return;  // свайп влево, но таблица не в конце
            }

            const params = new URLSearchParams(window.location.search);
            if (dx > 0) {
                // свайп вправо → предыдущий день
                window.location.href = '/schedule?' + params.toString().replace(
                    /day=[^&]+/, 'day=' + window.SCHEDULE_DATA.prevDay
                );
            } else {
                // свайп влево → следующий день
                window.location.href = '/schedule?' + params.toString().replace(
                    /day=[^&]+/, 'day=' + window.SCHEDULE_DATA.nextDay
                );
            }
        }
    }, { passive: true });
}

// ── Подсветка текущего времени ──

function highlightCurrentTime() {
    // Убираем предыдущую подсветку
    document.querySelectorAll('.cell-time.now').forEach(el => el.classList.remove('now'));

    const today = new Date().toISOString().slice(0, 10);
    if (!window.SCHEDULE_DATA || window.SCHEDULE_DATA.day !== today) return;

    const now = new Date();
    const nowMinutes = now.getHours() * 60 + now.getMinutes();

    const timeCells = document.querySelectorAll('.cell-time');
    let closest = null;
    let closestDiff = Infinity;

    timeCells.forEach(cell => {
        const text = cell.textContent.trim();
        const parts = text.split(':');
        if (parts.length !== 2) return;
        const cellMinutes = parseInt(parts[0]) * 60 + parseInt(parts[1]);
        const diff = Math.abs(nowMinutes - cellMinutes);
        if (diff < closestDiff) {
            closestDiff = diff;
            closest = cell;
        }
    });

    if (closest && closestDiff <= 30) {
        closest.classList.add('now');
        // Скроллим к текущему времени при первой загрузке
        if (!window._scrolledToNow) {
            closest.scrollIntoView({ block: 'center', behavior: 'smooth' });
            window._scrolledToNow = true;
        }
    }
}
