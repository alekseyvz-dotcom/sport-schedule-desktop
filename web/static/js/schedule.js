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

function changePeriod(val) {
    const params = new URLSearchParams(window.location.search);
    params.set('period', val);
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

    setupSwipe();
    highlightCurrentTime();
    setInterval(highlightCurrentTime, 60000);
});

// ── Модальное окно деталей ──

function showBooking(bookingId) {
    const modal = document.getElementById('bookingModal');
    const body = document.getElementById('bookingDetails');
    const d = window.SCHEDULE_DATA;

    // Ищем бронирование в spans (grid) или listBookings (list)
    let b = null;

    if (d && d.spans) {
        const sp = d.spans[String(bookingId)];
        if (sp && sp.booking) {
            b = sp.booking;
        }
    }

    if (!b && d && d.listBookings) {
        const item = d.listBookings.find(x => x.id === bookingId);
        if (item && item.booking) {
            b = item.booking;
        }
    }

    if (!b) {
        body.innerHTML = '<p style="color:var(--text-dim);text-align:center;padding:20px;">Бронирование не найдено</p>';
        modal.style.display = 'flex';
        return;
    }

    const kindLabel = b.activity === 'PD' ? 'ПД (Предпринимательская деятельность)'
                    : b.activity === 'GZ' ? 'ГЗ (Государственное задание)'
                    : (b.activity || '—');

    const statusMap = {
        'planned':   { label: 'Запланировано', css: 'status-planned' },
        'done':      { label: 'Проведено',     css: 'status-done' },
        'cancelled': { label: 'Отменено',      css: 'status-cancelled' },
    };
    const st = statusMap[b.status] || { label: b.status || '—', css: '' };

    const tenantName = b.activity === 'GZ'
        ? (b.gz_group_name || '—')
        : (b.tenant_name || '—');

    // Площадка
    const resourceName = b.resource_name || '—';

    const startDate = b.starts_at ? new Date(b.starts_at) : null;
    const endDate = b.ends_at ? new Date(b.ends_at) : null;

    const dateStr = startDate
        ? startDate.toLocaleDateString('ru-RU')
        : '—';

    const timeStr = (startDate && endDate)
        ? startDate.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
          + ' – '
          + endDate.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
        : '—';

    let durationStr = '—';
    if (startDate && endDate) {
        const durationMin = Math.round((endDate - startDate) / 60000);
        durationStr = durationMin >= 60
            ? Math.floor(durationMin / 60) + ' ч ' + (durationMin % 60 ? (durationMin % 60) + ' мин' : '')
            : durationMin + ' мин';
    }

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
            <span class="detail-label">Площадка</span>
            <span class="detail-value">${resourceName}</span>
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
    document.addEventListener('keydown', closeOnEscape);
}

function closeModal() {
    document.getElementById('bookingModal').style.display = 'none';
    document.removeEventListener('keydown', closeOnEscape);
}

function closeOnEscape(e) {
    if (e.key === 'Escape') closeModal();
}

// ── Свайп для мобилки ──

function setupSwipe() {
    let touchStartX = 0;
    let touchStartY = 0;
    const wrap = document.querySelector('.schedule-wrap') || document.querySelector('.list-wrap');
    if (!wrap) return;

    wrap.addEventListener('touchstart', function (e) {
        touchStartX = e.changedTouches[0].screenX;
        touchStartY = e.changedTouches[0].screenY;
    }, { passive: true });

    wrap.addEventListener('touchend', function (e) {
        const dx = e.changedTouches[0].screenX - touchStartX;
        const dy = e.changedTouches[0].screenY - touchStartY;

        if (Math.abs(dx) > 80 && Math.abs(dx) > Math.abs(dy) * 1.5) {
            if (wrap.scrollWidth > wrap.clientWidth + 10) {
                const atLeft = wrap.scrollLeft <= 5;
                const atRight = wrap.scrollLeft >= wrap.scrollWidth - wrap.clientWidth - 5;
                if (dx > 0 && !atLeft) return;
                if (dx < 0 && !atRight) return;
            }

            const d = window.SCHEDULE_DATA;
            if (d) {
                const params = new URLSearchParams(window.location.search);
                const currentDay = new Date(d.day);
                if (dx > 0) {
                    currentDay.setDate(currentDay.getDate() - 1);
                } else {
                    currentDay.setDate(currentDay.getDate() + 1);
                }
                params.set('day', currentDay.toISOString().slice(0, 10));
                window.location.href = '/schedule?' + params.toString();
            }
        }
    }, { passive: true });
}

// ── Подсветка текущего времени ──

function highlightCurrentTime() {
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
        if (!window._scrolledToNow) {
            closest.scrollIntoView({ block: 'center', behavior: 'smooth' });
            window._scrolledToNow = true;
        }
    }
}
