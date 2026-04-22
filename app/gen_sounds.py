"""
Generate placeholder sound files for Toto agent.

Outputs two mono 16-bit PCM WAVs in assets_processed/sound/:
  - snore.wav  (~3 s looping ambient snore-ish drone)
  - bark.wav   (~0.6 s double bark)

These are synthetic fallbacks so the app has audio out of the box. Replace
them later with real royalty-free samples for a much nicer result — see
README for suggested sources.
"""
from pathlib import Path
import numpy as np
from scipy.io import wavfile

OUT = Path(__file__).parent / "assets_processed" / "sound"
OUT.mkdir(parents=True, exist_ok=True)

SR = 22050


def save(name: str, samples: np.ndarray, sample_rate: int = SR):
    samples = np.asarray(samples, dtype=np.float64)
    peak = float(np.max(np.abs(samples)))
    if peak > 0:
        samples = samples / peak * 0.92
    pcm = (samples * 32767).astype(np.int16)
    wavfile.write(str(OUT / name), sample_rate, pcm)
    print(f"  wrote {OUT / name}")


def make_snore(duration: float = 3.0):
    """A slow breathing drone: low rumble modulated by an inhale/exhale
    envelope at ~0.4 Hz. Deliberately soft so it won't annoy the user."""
    t = np.linspace(0.0, duration, int(SR * duration), endpoint=False)
    breath = (np.sin(2 * np.pi * 0.42 * t) + 1) / 2  # 0..1, ~2.4 s per cycle
    tone = (0.55 * np.sin(2 * np.pi * 88 * t)
            + 0.25 * np.sin(2 * np.pi * 176 * t)
            + 0.10 * np.sin(2 * np.pi * 264 * t))
    # Add breathy noise that fades in/out with the envelope
    rng = np.random.default_rng(7)
    noise = 0.30 * rng.standard_normal(len(t)) * breath
    # Soft cosine window so the loop doesn't click at the seam
    window = 0.5 - 0.5 * np.cos(2 * np.pi * np.arange(len(t)) / (len(t) - 1))
    fade = np.minimum(1.0, np.concatenate([
        np.linspace(0, 1, SR // 4),             # 0.25 s fade in
        np.ones(len(t) - 2 * (SR // 4)),
        np.linspace(1, 0, SR // 4),             # 0.25 s fade out
    ]))
    signal = (tone * breath + noise) * fade
    return signal


def make_bark():
    """Two quick puppy-ish yelps: sharp attack, tonal body around 450 Hz
    with an upward pitch sweep, short decay, brief gap, second bark."""
    def one_bark(base_hz=460, dur=0.22):
        t = np.linspace(0.0, dur, int(SR * dur), endpoint=False)
        # Pitch sweep: starts higher, drops
        pitch = base_hz * (1 + 0.3 * np.exp(-t * 18))
        phase = 2 * np.pi * np.cumsum(pitch) / SR
        tone = (0.55 * np.sin(phase)
                + 0.30 * np.sin(2 * phase)
                + 0.12 * np.sin(3 * phase))
        rng = np.random.default_rng(42)
        noise = 0.25 * rng.standard_normal(len(t))
        # Percussive envelope: fast attack, exponential decay
        env = (1 - np.exp(-t * 120)) * np.exp(-t * 9)
        return (tone + noise) * env

    silence = np.zeros(int(SR * 0.13))
    b1 = one_bark(base_hz=470, dur=0.20)
    b2 = one_bark(base_hz=430, dur=0.22) * 0.9
    return np.concatenate([b1, silence, b2, np.zeros(int(SR * 0.05))])


if __name__ == "__main__":
    print("Generating placeholder sounds...")
    save("snore.wav", make_snore(duration=3.0))
    save("bark.wav",  make_bark())
    print("Done. Replace these with real CC0 samples from pixabay.com "
          "(set --sample-rate 22050 or 44100 mono WAV) to taste.")
