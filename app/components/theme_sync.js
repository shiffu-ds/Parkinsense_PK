// Keeps server-drawn colours in step with the theme Streamlit actually shows.
// Page tokens, the sidebar logo and chart colours are chosen in Python from
// st.context.theme, which only refreshes on a rerun. A system or Settings
// theme switch repaints Streamlit's own widgets at once, so when the shown
// theme no longer matches the one this page was drawn for, ask for one rerun.
// No patient data enters this component.

export function shownTheme(doc = document) {
    const app = doc.querySelector('[data-testid="stApp"]') || doc.body;
    const channels = app && getComputedStyle(app).backgroundColor.match(/[\d.]+/g);
    if (!channels || channels.length < 3) return null;
    if (channels.length > 3 && Number(channels[3]) === 0) return null;  // Not painted yet.
    const [r, g, b] = channels.slice(0, 3).map(Number);
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255 < 0.5 ? 'dark' : 'light';
}

export default function(component) {
    const {data, setTriggerValue} = component;
    const sync = window.__parkinsenseThemeSync || (window.__parkinsenseThemeSync = {requested: null});
    sync.drawn = data && data.drawn;
    sync.trigger = setTriggerValue;
    sync.check = () => {
        const shown = shownTheme();
        if (!shown) return;
        if (shown === sync.drawn) {
            sync.requested = null;  // In step again; a later switch may ask once more.
            return;
        }
        if (shown === sync.requested) return;  // Asked once for this theme; never loop.
        sync.requested = shown;
        try {
            sync.trigger('changed', shown);
        } catch (_) {
            sync.requested = null;
        }
    };
    if (!sync.timer) {
        // A Settings-menu switch fires no event, so also look once a second.
        sync.timer = setInterval(() => sync.check(), 1000);
        const media = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)');
        if (media && media.addEventListener) media.addEventListener('change', () => setTimeout(() => sync.check(), 60));
    }
    sync.check();
}
