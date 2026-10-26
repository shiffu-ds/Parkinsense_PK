// Reads fixed instructions aloud with the browser's own voices. Only the app's
// instruction text is spoken; no patient data enters this code.

export function pickVoice(voices, lang) {
    const wanted = lang.toLowerCase();
    const prefix = wanted.slice(0, 2);
    return voices.find((voice) => voice.lang.toLowerCase() === wanted)
        || voices.find((voice) => voice.lang.toLowerCase().replace('_', '-').startsWith(prefix))
        || null;
}

export default function(component) {
    const {parentElement, data} = component;
    const button = parentElement.querySelector('.ps-listen');
    const note = parentElement.querySelector('.ps-listen-note');
    button.textContent = `🔊 ${data.labels.listen}`;
    button.onclick = () => {
        const synth = window.speechSynthesis;
        if (!synth || typeof window.SpeechSynthesisUtterance !== 'function') {
            note.textContent = data.labels.unavailable;
            return;
        }
        synth.cancel();
        let spoken = false;
        const speak = () => {
            if (spoken) return;
            spoken = true;
            const voice = pickVoice(synth.getVoices(), data.lang);
            if (!voice && data.lang.startsWith('ur')) {
                note.textContent = data.labels.no_voice;
                return;
            }
            const utterance = new window.SpeechSynthesisUtterance(data.text);
            utterance.lang = data.lang;
            if (voice) utterance.voice = voice;
            utterance.rate = 0.9;
            note.textContent = '';
            synth.speak(utterance);
        };
        if (synth.getVoices().length) {
            speak();
        } else {
            synth.addEventListener('voiceschanged', speak, {once: true});
            setTimeout(speak, 1000);
        }
    };
}
