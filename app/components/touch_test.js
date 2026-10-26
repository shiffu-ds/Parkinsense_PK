// Touchscreen spiral drawing and two-circle tapping. The canvas only collects
// raw touches: normalized coordinates (drawing-width units) and times. All
// scoring happens in Python. No patient data enters this code or its HTML.

const states = new WeakMap();
const MAX_POINTS = 4000;
const MAX_TAPS = 400;

export function spiralPoints(geometry, samples = 900) {
    const total = 2 * Math.PI * geometry.turns;
    const points = [];
    for (let i = 0; i <= samples; i++) {
        const theta = total * i / samples;
        const radius = geometry.r_max * theta / total;
        points.push([geometry.cx + radius * Math.cos(theta), geometry.cy + radius * Math.sin(theta)]);
    }
    return points;
}

export function targetAt(x, y, geometry) {
    let best = -1;
    let bestDistance = Infinity;
    geometry.targets.forEach(([cx, cy], index) => {
        const distance = Math.hypot(x - cx, y - cy);
        if (distance <= geometry.radius && distance < bestDistance) {
            best = index;
            bestDistance = distance;
        }
    });
    return best;
}

function setup(component) {
    const {parentElement} = component;
    const root = parentElement.querySelector('.ps-touch');
    const canvas = root.querySelector('canvas');
    const status = root.querySelector('.ps-touch-status');
    const clear = root.querySelector('.ps-touch-clear');
    const done = root.querySelector('.ps-touch-done');
    const state = {root, canvas, status, clear, done, points: [], taps: [], stroke: -1, drawing: false,
                   started: null, finished: false, submitted: false, timer: null, ticker: null, pointer: 'unknown',
                   next: 0, flash: null};

    const point = (event) => {
        const rect = canvas.getBoundingClientRect();
        return [(event.clientX - rect.left) / rect.width, (event.clientY - rect.top) / rect.width];
    };
    const seconds = (event) => (event.timeStamp - state.started) / 1000;

    canvas.addEventListener('pointerdown', (event) => {
        if (!event.isPrimary || state.submitted || state.finished) return;
        event.preventDefault();
        state.pointer = event.pointerType || 'unknown';
        const data = state.data;
        if (state.started === null) state.started = event.timeStamp;
        const [x, y] = point(event);
        if (data.mode === 'spiral') {
            try {
                canvas.setPointerCapture(event.pointerId);
            } catch (_) {
                // Some browsers refuse capture for synthetic or stylus-hover pointers; drawing still works.
            }
            state.drawing = true;
            state.stroke += 1;
            if (state.points.length < MAX_POINTS) state.points.push([x, y, seconds(event), state.stroke]);
        } else {
            if (state.taps.length === 0) beginCountdown(state);
            if (state.taps.length < MAX_TAPS) state.taps.push([x, y, seconds(event)]);
            const hit = targetAt(x, y, data.tapping);
            if (hit >= 0) {
                state.flash = hit;
                state.next = 1 - hit;
                setTimeout(() => { state.flash = null; draw(state); }, 120);
            }
        }
        updateButtons(state);
        draw(state);
    });
    canvas.addEventListener('pointermove', (event) => {
        if (!state.drawing || !event.isPrimary) return;
        event.preventDefault();
        const events = typeof event.getCoalescedEvents === 'function' ? event.getCoalescedEvents() : [event];
        for (const item of (events.length ? events : [event])) {
            if (state.points.length >= MAX_POINTS) break;
            const [x, y] = point(item);
            state.points.push([x, y, seconds(item), state.stroke]);
        }
        draw(state);
    });
    const stop = () => {
        state.drawing = false;
        updateButtons(state);
    };
    canvas.addEventListener('pointerup', stop);
    canvas.addEventListener('pointercancel', stop);
    clear.addEventListener('click', () => reset(state));
    done.addEventListener('click', () => submit(state, state.data.mode === 'tapping' ? false : true));
    new ResizeObserver(() => resize(state)).observe(root);
    return state;
}

function beginCountdown(state) {
    const total = state.data.tapping.seconds;
    state.timer = setTimeout(() => {
        state.finished = true;
        submit(state, true);
    }, total * 1000);
    state.ticker = setInterval(() => {
        if (state.finished || state.started === null) return;
        const left = Math.max(0, total - (performance.now() - state.started) / 1000);
        state.status.textContent = state.data.labels.remaining.replace('{seconds}', Math.ceil(left));
    }, 250);
}

function reset(state) {
    clearTimeout(state.timer);
    clearInterval(state.ticker);
    Object.assign(state, {points: [], taps: [], stroke: -1, drawing: false, started: null, finished: false,
                          submitted: false, timer: null, ticker: null, next: 0, flash: null});
    state.status.textContent = state.data.labels.ready;
    updateButtons(state);
    draw(state);
}

function submit(state, completed) {
    if (state.submitted) return;
    clearTimeout(state.timer);
    clearInterval(state.ticker);
    const data = state.data;
    const rect = state.canvas.getBoundingClientRect();
    const payload = {mode: data.mode, pointer: state.pointer, dpr: window.devicePixelRatio || 1,
                     canvas_px: [Math.round(rect.width), Math.round(rect.height)]};
    if (data.mode === 'spiral') {
        if (state.points.length < 2) return;
        payload.points = state.points;
    } else {
        payload.taps = state.taps;
        payload.completed = completed && state.taps.length > 0;
    }
    state.submitted = true;
    state.status.textContent = data.labels.analysing;
    updateButtons(state);
    state.trigger('submitted', payload);
}

function updateButtons(state) {
    const data = state.data;
    state.clear.disabled = state.points.length === 0 && state.taps.length === 0 && !state.submitted;
    state.done.hidden = data.mode === 'tapping' && state.taps.length === 0;
    state.done.disabled = state.submitted || state.drawing ||
        (data.mode === 'spiral' ? state.points.length < 2 : state.taps.length === 0);
}

function resize(state) {
    if (!state.data) return;
    const width = Math.max(200, Math.min(state.root.clientWidth, 460));
    const ratio = state.data.mode === 'spiral' ? 1 : state.data.tapping.height;
    const scale = window.devicePixelRatio || 1;
    state.canvas.style.width = `${width}px`;
    state.canvas.style.height = `${Math.round(width * ratio)}px`;
    state.canvas.width = Math.round(width * scale);
    state.canvas.height = Math.round(width * ratio * scale);
    draw(state);
}

function draw(state) {
    const {canvas, data} = state;
    if (!data) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const w = canvas.width;
    const colors = data.colors;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = colors.surface;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    if (data.mode === 'spiral') {
        const guide = spiralPoints(data.spiral);
        ctx.strokeStyle = colors.guide;
        ctx.lineWidth = Math.max(2, w * 0.012);
        ctx.beginPath();
        guide.forEach(([x, y], i) => (i ? ctx.lineTo(x * w, y * w) : ctx.moveTo(x * w, y * w)));
        ctx.stroke();
        ctx.fillStyle = colors.accent;
        ctx.beginPath();
        ctx.arc(data.spiral.cx * w, data.spiral.cy * w, w * 0.018, 0, 2 * Math.PI);
        ctx.fill();
        ctx.strokeStyle = colors.accent;
        ctx.lineWidth = Math.max(2, w * 0.008);
        let previous = null;
        for (const [x, y, , stroke] of state.points) {
            if (previous && previous[3] === stroke) {
                ctx.beginPath();
                ctx.moveTo(previous[0] * w, previous[1] * w);
                ctx.lineTo(x * w, y * w);
                ctx.stroke();
            }
            previous = [x, y, 0, stroke];
        }
    } else {
        data.tapping.targets.forEach(([x, y], index) => {
            ctx.beginPath();
            ctx.arc(x * w, y * w, data.tapping.radius * w, 0, 2 * Math.PI);
            ctx.fillStyle = state.flash === index ? colors.accent : colors.soft;
            ctx.fill();
            ctx.lineWidth = Math.max(2, w * (index === state.next && !state.finished ? 0.012 : 0.006));
            ctx.strokeStyle = index === state.next && !state.finished ? colors.attention : colors.accent;
            ctx.stroke();
        });
        ctx.fillStyle = colors.ink;
        for (const [x, y] of state.taps.slice(-6)) {
            ctx.beginPath();
            ctx.arc(x * w, y * w, w * 0.008, 0, 2 * Math.PI);
            ctx.fill();
        }
    }
}

export default function(component) {
    const {parentElement, data, setTriggerValue} = component;
    let state = states.get(parentElement);
    const fresh = !state;
    if (fresh) {
        state = setup(component);
        states.set(parentElement, state);
    }
    const modeChanged = state.data && state.data.mode !== data.mode;
    state.data = data;
    state.trigger = setTriggerValue;
    state.canvas.setAttribute('aria-label', data.labels.canvas);
    state.clear.textContent = data.labels.clear;
    state.done.textContent = data.mode === 'tapping' ? data.labels.stop : data.labels.done;
    if (fresh || modeChanged) reset(state);
    else if (state.submitted && data.measured) state.status.textContent = data.labels.measured;
    resize(state);
    return () => {
        clearTimeout(state.timer);
        clearInterval(state.ticker);
        states.delete(parentElement);
    };
}
