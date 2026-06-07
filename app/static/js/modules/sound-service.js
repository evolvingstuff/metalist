import { CONFIG } from './config.js';
import { SoundsAPI } from './api-client.js';
import { buildSessionHeaders } from './session-auth.js';

export const DEFAULT_SOUND_ID = 'builtin.default_chime';

let cachedLibrary = null;
const activeAudioElements = new Set();
const activeAudioContexts = new Set();

function requireLibraryShape(payload) {
    if (!payload || typeof payload !== 'object') {
        throw new Error('Sound library payload missing');
    }
    if (!Array.isArray(payload.sounds)) {
        throw new Error('Sound library payload missing sounds');
    }
    if (!payload.usage || typeof payload.usage !== 'object') {
        throw new Error('Sound library payload missing usage');
    }
    return payload;
}

function soundIds(library) {
    if (!library || typeof library !== 'object') {
        throw new Error('soundIds requires library');
    }
    return new Set(library.sounds.map((sound) => {
        if (!sound || typeof sound !== 'object') {
            throw new Error('Sound library entry must be object');
        }
        if (typeof sound.id !== 'string' || sound.id.length === 0) {
            throw new Error('Sound library entry missing id');
        }
        return sound.id;
    }));
}

function browserAudioContextConstructor() {
    if (typeof window.AudioContext === 'function') {
        return window.AudioContext;
    }
    if (typeof window.webkitAudioContext === 'function') {
        return window.webkitAudioContext;
    }
    throw new Error('Browser does not support Web Audio');
}

function playBuiltinDefaultChime() {
    const AudioContextCtor = browserAudioContextConstructor();
    const context = new AudioContextCtor();
    activeAudioContexts.add(context);
    return context.resume().then(
        () => {
            const now = context.currentTime;
            const gain = context.createGain();
            gain.gain.setValueAtTime(0.0001, now);
            gain.gain.exponentialRampToValueAtTime(0.18, now + 0.015);
            gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.42);
            gain.connect(context.destination);

            const first = context.createOscillator();
            first.type = 'sine';
            first.frequency.setValueAtTime(659.25, now);
            first.connect(gain);
            first.start(now);
            first.stop(now + 0.42);

            const second = context.createOscillator();
            second.type = 'sine';
            second.frequency.setValueAtTime(987.77, now);
            second.connect(gain);
            second.start(now);
            second.stop(now + 0.28);

            window.setTimeout(() => {
                activeAudioContexts.delete(context);
                void context.close();
            }, 700);
            return { status: 'played' };
        },
        (error) => {
            activeAudioContexts.delete(context);
            return {
                status: 'blocked',
                message: error instanceof Error ? error.message : String(error),
            };
        },
    );
}

function playUploadedSound(soundId) {
    return fetch(CONFIG.API.SOUNDS.PLAY(soundId), {
        method: 'GET',
        headers: buildSessionHeaders(false),
    }).then(
        (response) => {
            if (!response.ok) {
                return {
                    status: 'failed',
                    message: `Sound request failed: ${response.status}`,
                };
            }
            return response.blob().then((blob) => {
                const objectUrl = URL.createObjectURL(blob);
                const audio = new Audio(objectUrl);
                activeAudioElements.add(audio);
                audio.addEventListener('ended', () => {
                    activeAudioElements.delete(audio);
                    URL.revokeObjectURL(objectUrl);
                }, { once: true });
                audio.addEventListener('error', () => {
                    activeAudioElements.delete(audio);
                    URL.revokeObjectURL(objectUrl);
                }, { once: true });
                return audio.play().then(
                    () => ({ status: 'played' }),
                    (error) => {
                        activeAudioElements.delete(audio);
                        URL.revokeObjectURL(objectUrl);
                        return {
                            status: 'blocked',
                            message: error instanceof Error ? error.message : String(error),
                        };
                    },
                );
            });
        },
        (error) => ({
            status: 'failed',
            message: error instanceof Error ? error.message : String(error),
        }),
    );
}

export const SoundService = {
    async refreshLibrary() {
        cachedLibrary = requireLibraryShape(await SoundsAPI.listSounds());
        return cachedLibrary;
    },

    async library() {
        if (cachedLibrary === null) {
            return await this.refreshLibrary();
        }
        return cachedLibrary;
    },

    clearCache() {
        cachedLibrary = null;
    },

    playSound(soundId) {
        if (typeof soundId !== 'string' || soundId.length === 0) {
            throw new Error('SoundService.playSound requires soundId');
        }
        if (cachedLibrary === null) {
            throw new Error('Sound library must be loaded before playback');
        }
        const library = cachedLibrary;
        if (!soundIds(library).has(soundId)) {
            throw new Error(`Cannot play unknown sound: ${soundId}`);
        }
        if (soundId === DEFAULT_SOUND_ID) {
            return playBuiltinDefaultChime();
        }
        return playUploadedSound(soundId);
    },

    async playReminderSound(reminder, kind) {
        if (!reminder || typeof reminder !== 'object') {
            throw new Error('SoundService.playReminderSound requires reminder');
        }
        if (kind !== 'popup' && kind !== 'ack') {
            throw new Error(`Unsupported reminder sound kind: ${kind}`);
        }
        const enabledKey = kind === 'popup' ? 'popup_sound_enabled' : 'ack_sound_enabled';
        const soundIdKey = kind === 'popup' ? 'popup_sound_id' : 'ack_sound_id';
        if (reminder[enabledKey] !== true) {
            return { status: 'disabled' };
        }
        const soundId = reminder[soundIdKey];
        if (typeof soundId !== 'string' || soundId.length === 0) {
            throw new Error(`Reminder missing ${soundIdKey}`);
        }
        if (cachedLibrary === null) {
            await this.refreshLibrary();
        }
        return await this.playSound(soundId);
    },
};
