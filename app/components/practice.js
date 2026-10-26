// Practice tools that run only in this browser: a walking beat and loud-voice
// feedback. Nothing is recorded, stored or sent, and no patient data enters
// this code. These are practice aids, not measurements.

const states = new WeakMap();
const VOICE_FLOOR_DB = -55;

export function clampBpm(value) {
    return Math.max(40, Math.min(140, Math.round(value / 5) * 5));
}

export function levelDb(samples) {
    let sum = 0;
    for (const value of samples) sum += value * value;
    const rms = Math.sqrt(sum / Math.max(1, samples.length));
    return rms > 0 ? 20 * Math.log10(rms) : -100;
}

export function meterFraction(db) {
    return Math.max(0, Math.min(1, (db + 60) / 60));
}

export function median(values) {
    const sorted = [...values].sort((a, b) => a - b);
    const middle = Math.floor(sorted.length / 2);
    return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function element(tag, className, parent) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (parent) parent.appendChild(node);
    return node;
}

function metronome(root) {
    root.replaceChildren();
    const display = element('p', 'ps-practice-big', root);
    const pulse = element('div', 'ps-practice-pulse', root);
    pulse.setAttribute('aria-hidden', 'true');
    const row = element('div', 'ps-practice-actions', root);
    const slower = element('button', '', row);
    const start = element('button', 'ps-practice-primary', row);
    const faster = element('button', '', row);
    for (const button of [slower, start, faster]) button.type = 'button';
    const state = {data: null, bpm: null, context: null, timer: null, next: 0, beats: [], running: false};

    const render = () => {
        const labels = state.data.labels;
        display.textContent = labels.bpm.replace('{bpm}', state.bpm);
        slower.textContent = labels.slower;
        faster.textContent = labels.faster;
        start.textContent = state.running ? labels.stop : labels.start;
    };
    const schedule = () => {
        const context = state.context;
        while (state.next < context.currentTime + 0.12) {
            const tone = context.createOscillator();
            const gain = context.createGain();
            tone.frequency.value = 880;
            gain.gain.setValueAtTime(0.0001, state.next);
            gain.gain.exponentialRampToValueAtTime(0.5, state.next + 0.005);
            gain.gain.exponentialRampToValueAtTime(0.0001, state.next + 0.06);
            tone.connect(gain).connect(context.destination);
            tone.start(state.next);
            tone.stop(state.next + 0.07);
            state.beats.push(state.next);
            state.next += 60 / state.bpm;
        }
    };
    const flash = () => {
        if (!state.running) return;
        while (state.beats.length && state.beats[0] <= state.context.currentTime) {
            state.beats.shift();
            pulse.classList.add('on');
            setTimeout(() => pulse.classList.remove('on'), 90);
        }
        requestAnimationFrame(flash);
    };
    state.stop = () => {
        state.running = false;
        clearInterval(state.timer);
        state.beats = [];
        if (state.data) render();
    };
    start.addEventListener('click', async () => {
        if (state.running) {
            state.stop();
            return;
        }
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        state.context = state.context || new AudioContext();
        await state.context.resume();
        state.running = true;
        state.next = state.context.currentTime + 0.1;
        state.timer = setInterval(schedule, 25);
        schedule();
        requestAnimationFrame(flash);
        render();
    });
    slower.addEventListener('click', () => { state.bpm = clampBpm(state.bpm - 5); render(); });
    faster.addEventListener('click', () => { state.bpm = clampBpm(state.bpm + 5); render(); });
    state.update = (data) => {
        state.data = data;
        if (state.bpm === null) state.bpm = clampBpm(data.default_bpm || 90);
        render();
    };
    state.dispose = () => {
        state.stop();
        if (state.context) state.context.close();
    };
    return state;
}

function loudness(root) {
    root.replaceChildren();
    const status = element('p', 'ps-practice-status', root);
    status.setAttribute('aria-live', 'polite');
    const meter = element('div', 'ps-practice-meter', root);
    const fill = element('div', 'ps-practice-fill', meter);
    const usualMark = element('div', 'ps-practice-mark', meter);
    const targetMark = element('div', 'ps-practice-mark ps-practice-target', meter);
    const zone = element('p', 'ps-practice-zone', root);
    const row = element('div', 'ps-practice-actions', root);
    const start = element('button', 'ps-practice-primary', row);
    start.type = 'button';
    const state = {data: null, stream: null, context: null, analyser: null, frame: null, phase: 'idle',
                   samples: [], usual: null, target: null, inZone: 0, last: null, began: 0};

    const labels = () => state.data.labels;
    const render = () => {
        start.textContent = state.phase === 'idle' ? labels().start : labels().stop;
        zone.textContent = labels().time.replace('{seconds}', Math.round(state.inZone));
        if (state.phase === 'idle' && !status.dataset.error) status.textContent = labels().ready;
    };
    const loop = (now) => {
        if (state.phase === 'idle') return;
        const buffer = new Float32Array(state.analyser.fftSize);
        state.analyser.getFloatTimeDomainData(buffer);
        const db = levelDb(buffer);
        const elapsed = state.last === null ? 0 : (now - state.last) / 1000;
        state.last = now;
        fill.style.width = `${Math.round(meterFraction(db) * 100)}%`;
        if (state.phase === 'calibrating') {
            if (db > VOICE_FLOOR_DB) state.samples.push(db);
            if (now - state.began > 3000 && state.samples.length > 20) {
                state.usual = median(state.samples);
                state.target = Math.min(-3, state.usual + 6);
                usualMark.style.left = `${Math.round(meterFraction(state.usual) * 100)}%`;
                targetMark.style.left = `${Math.round(meterFraction(state.target) * 100)}%`;
                usualMark.hidden = targetMark.hidden = false;
                state.phase = 'practice';
                status.textContent = labels().go;
            }
        } else if (db >= state.target && db > VOICE_FLOOR_DB) {
            state.inZone += elapsed;
        }
        fill.classList.toggle('in-zone', state.phase === 'practice' && db >= state.target);
        render();
        state.frame = requestAnimationFrame(loop);
    };
    state.stop = () => {
        state.phase = 'idle';
        cancelAnimationFrame(state.frame);
        if (state.stream) state.stream.getTracks().forEach((track) => track.stop());
        if (state.context) state.context.close();
        Object.assign(state, {stream: null, context: null, analyser: null, last: null});
        fill.style.width = '0%';
        if (state.data) render();
    };
    start.addEventListener('click', async () => {
        if (state.phase !== 'idle') {
            state.stop();
            return;
        }
        delete status.dataset.error;
        try {
            state.stream = await navigator.mediaDevices.getUserMedia(
                {audio: {echoCancellation: false, noiseSuppression: false, autoGainControl: false}});
        } catch (_) {
            status.dataset.error = '1';
            status.textContent = labels().denied;
            return;
        }
        const AudioContext = window.AudioContext || window.webkitAudioContext;
        state.context = new AudioContext();
        state.analyser = state.context.createAnalyser();
        state.analyser.fftSize = 2048;
        state.context.createMediaStreamSource(state.stream).connect(state.analyser);
        Object.assign(state, {phase: 'calibrating', samples: [], inZone: 0, began: performance.now(), last: null});
        usualMark.hidden = targetMark.hidden = true;
        status.textContent = labels().calibrating;
        state.frame = requestAnimationFrame(loop);
        render();
    });
    usualMark.hidden = targetMark.hidden = true;
    state.update = (data) => {
        state.data = data;
        render();
    };
    state.dispose = () => state.stop();
    return state;
}

export default function(component) {
    const {parentElement, data} = component;
    let state = states.get(parentElement);
    if (!state) {
        const root = parentElement.querySelector('.ps-practice');
        state = data.mode === 'metronome' ? metronome(root) : loudness(root);
        states.set(parentElement, state);
    }
    state.update(data);
    return () => {
        state.dispose();
        states.delete(parentElement);
    };
}
