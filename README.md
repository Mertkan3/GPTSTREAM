# Reptile Clip Master

Deutsch-first Stream-zu-Shorts Tool für Twitch/YouTube/VODs und MP4-Uploads.

## Funktionen

- MP4/MOV/MKV/WEBM/MP3/M4A/WAV Upload
- Twitch/YouTube/VOD-Link über `yt-dlp`
- Lokale Transkription über `faster-whisper`
- Clip-Erkennung für deutsche Comedy-/Entertainment-Streams
- Score pro Clip: Hook, Comedy, Eskalation, Pace, Länge, Verständlichkeit
- Titel, Beschreibung, Overlay-Hook und Hashtags für TikTok/Reels
- SRT-Untertitel pro Clip
- Optionaler MP4-Export im 9:16 Format mit Blur-Background
- Optionales Einbrennen von Untertiteln
- ZIP-Download mit Clips, SRTs, CSV, JSON und Transkript

## GitHub/Streamlit Deployment

1. Neues GitHub Repository erstellen.
2. Diese Dateien ins Repo hochladen:
   - `app.py`
   - `requirements.txt`
   - `packages.txt`
   - `.streamlit/config.toml`
   - `README.md`
3. Auf https://share.streamlit.io gehen.
4. Repo auswählen.
5. Entry point: `app.py`
6. Deploy klicken.

## Wichtige Realität

Streamlit Community Cloud ist nicht für stundenlange 4K-VODs gebaut. Nutze dort kleine Uploads oder lade bei VOD-Links nur einen Ausschnitt herunter. Für echte unbegrenzte Nutzung musst du das Tool lokal oder auf einem eigenen Server laufen lassen.

Lokal starten:

```bash
pip install -r requirements.txt
streamlit run app.py
```

Falls FFmpeg fehlt:

- Windows: FFmpeg installieren und in PATH setzen.
- Linux: `sudo apt install ffmpeg`
- macOS: `brew install ffmpeg`

## Best Settings

Für Streamlit Cloud:

- Whisper-Modell: `tiny` oder `base`
- Max. Download-Minuten: 15–45
- MP4 Export: an
- Untertitel einbrennen: erst aus, wenn alles läuft dann testen

Für lokalen PC:

- Whisper-Modell: `small`
- Längere VODs möglich
- Untertitel einbrennen aktivieren

## Rechtliches

Verarbeite nur Content, den du verwenden darfst. Twitch/YouTube-Links können je nach Plattform, Region, Login-Pflicht oder Rechteverwaltung scheitern.
