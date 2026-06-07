import { CONFIG } from './config.js';
import { SoundsAPI } from './api-client.js';
import { loadClientState, persistClientPreferences } from './client-state-api.js';
import { buildSessionHeaders } from './session-auth.js';

export const DEFAULT_SOUND_ID = 'builtin.default_chime';
export const SILENT_SOUND_ID = 'builtin.silent';
export const PREF_REMINDER_DEFAULT_POPUP_SOUND_ENABLED = 'pref.reminder_default_popup_sound_enabled';
export const PREF_REMINDER_DEFAULT_POPUP_SOUND_ID = 'pref.reminder_default_popup_sound_id';
export const PREF_REMINDER_DEFAULT_ACK_SOUND_ENABLED = 'pref.reminder_default_ack_sound_enabled';
export const PREF_REMINDER_DEFAULT_ACK_SOUND_ID = 'pref.reminder_default_ack_sound_id';

let cachedLibrary = null;
let cachedDefaultSettings = null;
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

function defaultSoundSettings() {
    return {
        popupEnabled: false,
        popupSoundId: DEFAULT_SOUND_ID,
        ackEnabled: false,
        ackSoundId: DEFAULT_SOUND_ID,
    };
}

function preferenceBoolean(preferences, key) {
    if (!preferences || typeof preferences !== 'object') {
        throw new Error('preferenceBoolean requires preferences');
    }
    const raw = preferences[key];
    if (raw === undefined) {
        return false;
    }
    if (raw === 'true') {
        return true;
    }
    if (raw === 'false') {
        return false;
    }
    throw new Error(`Invalid boolean sound preference for ${key}`);
}

function preferenceSoundId(preferences, key) {
    if (!preferences || typeof preferences !== 'object') {
        throw new Error('preferenceSoundId requires preferences');
    }
    const raw = preferences[key];
    if (raw === undefined) {
        return DEFAULT_SOUND_ID;
    }
    if (typeof raw !== 'string' || raw.length === 0) {
        throw new Error(`Invalid sound id preference for ${key}`);
    }
    return raw;
}

function defaultSettingsFromPreferences(preferences) {
    return {
        popupEnabled: preferenceBoolean(preferences, PREF_REMINDER_DEFAULT_POPUP_SOUND_ENABLED),
        popupSoundId: preferenceSoundId(preferences, PREF_REMINDER_DEFAULT_POPUP_SOUND_ID),
        ackEnabled: preferenceBoolean(preferences, PREF_REMINDER_DEFAULT_ACK_SOUND_ENABLED),
        ackSoundId: preferenceSoundId(preferences, PREF_REMINDER_DEFAULT_ACK_SOUND_ID),
    };
}

async function loadPreferences() {
    const clientState = await loadClientState();
    if (!clientState || typeof clientState !== 'object') {
        throw new Error('Sound client state missing');
    }
    const preferences = clientState.preferences;
    if (!preferences || typeof preferences !== 'object' || Array.isArray(preferences)) {
        throw new Error('Sound preferences missing');
    }
    return preferences;
}

function effectiveSoundId(reminder, kind, defaultSettingsValue) {
    if (!reminder || typeof reminder !== 'object') {
        throw new Error('effectiveSoundId requires reminder');
    }
    if (!defaultSettingsValue || typeof defaultSettingsValue !== 'object') {
        throw new Error('effectiveSoundId requires defaultSettingsValue');
    }
    if (kind !== 'popup' && kind !== 'ack') {
        throw new Error(`Unsupported reminder sound kind: ${kind}`);
    }
    const enabledKey = kind === 'popup' ? 'popup_sound_enabled' : 'ack_sound_enabled';
    const soundIdKey = kind === 'popup' ? 'popup_sound_id' : 'ack_sound_id';
    if (reminder[enabledKey] === true) {
        const reminderSoundId = reminder[soundIdKey];
        if (typeof reminderSoundId !== 'string' || reminderSoundId.length === 0) {
            throw new Error(`Reminder missing ${soundIdKey}`);
        }
        return reminderSoundId;
    }
    const defaultEnabled = kind === 'popup' ? defaultSettingsValue.popupEnabled : defaultSettingsValue.ackEnabled;
    if (defaultEnabled !== true) {
        return SILENT_SOUND_ID;
    }
    const defaultSoundId = kind === 'popup' ? defaultSettingsValue.popupSoundId : defaultSettingsValue.ackSoundId;
    if (typeof defaultSoundId !== 'string' || defaultSoundId.length === 0) {
        throw new Error(`Default reminder sound missing for ${kind}`);
    }
    return defaultSoundId;
}

function reminderHasAudibleSoundWithDefaults(reminder, defaultSettingsValue) {
    const popupSoundId = effectiveSoundId(reminder, 'popup', defaultSettingsValue);
    if (popupSoundId !== SILENT_SOUND_ID) {
        return true;
    }
    return effectiveSoundId(reminder, 'ack', defaultSettingsValue) !== SILENT_SOUND_ID;
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
        cachedDefaultSettings = null;
    },

    async defaultSettings() {
        cachedDefaultSettings = defaultSettingsFromPreferences(await loadPreferences());
        return cachedDefaultSettings;
    },

    currentDefaultSettings() {
        if (cachedDefaultSettings === null) {
            return defaultSoundSettings();
        }
        return cachedDefaultSettings;
    },

    async saveDefaultSettings(nextPreferences) {
        if (!nextPreferences || typeof nextPreferences !== 'object') {
            throw new Error('SoundService.saveDefaultSettings requires object');
        }
        const clientState = await loadClientState();
        if (!clientState || typeof clientState !== 'object') {
            throw new Error('Sound client state missing');
        }
        const current = clientState.preferences;
        if (!current || typeof current !== 'object' || Array.isArray(current)) {
            throw new Error('Sound preferences missing');
        }
        const merged = { ...current };
        const library = await this.library();
        const validSoundIds = soundIds(library);
        const soundKeys = [
            PREF_REMINDER_DEFAULT_POPUP_SOUND_ID,
            PREF_REMINDER_DEFAULT_ACK_SOUND_ID,
        ];
        for (const [key, value] of Object.entries(nextPreferences)) {
            if (soundKeys.includes(key) && !validSoundIds.has(value)) {
                throw new Error(`Unknown default reminder sound selected for ${key}: ${value}`);
            }
            merged[key] = value;
        }
        const saved = await persistClientPreferences(merged);
        if (!saved || typeof saved !== 'object') {
            throw new Error('Saved sound preferences payload missing');
        }
        const preferences = saved.preferences;
        if (!preferences || typeof preferences !== 'object' || Array.isArray(preferences)) {
            throw new Error('Saved sound preferences missing');
        }
        cachedDefaultSettings = defaultSettingsFromPreferences(preferences);
        return cachedDefaultSettings;
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
        let defaults = cachedDefaultSettings;
        if (defaults === null) {
            defaults = await this.defaultSettings();
        }
        const soundId = effectiveSoundId(reminder, kind, defaults);
        if (soundId === SILENT_SOUND_ID) {
            return { status: 'disabled' };
        }
        if (cachedLibrary === null) {
            await this.refreshLibrary();
        }
        return await this.playSound(soundId);
    },

    reminderHasAudibleSound(reminder, defaultSettingsValue) {
        return reminderHasAudibleSoundWithDefaults(reminder, defaultSettingsValue);
    },
};
