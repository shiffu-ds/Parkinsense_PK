// This module persists between data updates. No patient data enters code/HTML.
const views = new WeakMap();

export default function(component) {
    const {parentElement, data} = component;
    const graph = parentElement.querySelector('.live-graph');
    let state = views.get(parentElement);
    if (!state) {
        state = {pending: null, busy: false, disposed: false, interacting: false,
                 timer: null, libraryDeadline: Date.now() + 15000};
        views.set(parentElement, state);
        state.flush = async () => {
            if (state.disposed || state.busy || state.interacting || !state.pending) return;
            const Plotly = window.__parkinsenseLivePlotly;
            if (!Plotly) {
                if (Date.now() < state.libraryDeadline) {
                    clearTimeout(state.timer);
                    state.timer = setTimeout(state.flush, 40);
                } else {
                    graph.textContent = 'The 3D viewer could not load. Refresh the page to try again.';
                }
                return;
            }
            const figure = state.pending;
            state.pending = null;
            state.busy = true;
            try {
                await Plotly.react(graph, figure.data, figure.layout,
                    {displaylogo: false, scrollZoom: true, responsive: true});
            } catch (_) {
                graph.textContent = 'The 3D view could not render. Restart the camera preview.';
            } finally {
                state.busy = false;
                if (state.disposed) Plotly.purge(graph);
                else if (state.pending) state.timer = setTimeout(state.flush, 0);
            }
        };
        state.pointerDown = () => {state.interacting = true;};
        state.pointerUp = () => {
            state.interacting = false;
            state.flush();
        };
        graph.addEventListener('pointerdown', state.pointerDown);
        window.addEventListener('pointerup', state.pointerUp);
        window.addEventListener('pointercancel', state.pointerUp);
        state.resize = new ResizeObserver(() => {
            const Plotly = window.__parkinsenseLivePlotly;
            if (Plotly && graph._fullLayout && !state.disposed) Plotly.Plots.resize(graph);
        });
        state.resize.observe(graph);
    }
    state.pending = data.figure;
    state.flush();
    // Streamlit invokes this on unmount, not on each data refresh.
    return () => {
        state.disposed = true;
        state.pending = null;
        clearTimeout(state.timer);
        state.resize.disconnect();
        graph.removeEventListener('pointerdown', state.pointerDown);
        window.removeEventListener('pointerup', state.pointerUp);
        window.removeEventListener('pointercancel', state.pointerUp);
        window.__parkinsenseLivePlotly?.purge(graph);
        views.delete(parentElement);
    };
}
