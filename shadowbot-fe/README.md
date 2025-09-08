# Shadow Bot

A real-time AI assistant that provides contextual help during video calls, interviews, presentations, and meetings using screen capture and audio analysis.

## Features

- **Live AI Assistance**: Real-time help powered by Google Gemini 2.0 Flash Live
- **Screen & Audio Capture**: Analyzes what you see and hear for contextual responses
- **Multiple Profiles**: Interview, Customer Support, Business Meeting
- **Transparent Overlay**: Always-on-top window that can be positioned anywhere
- **Click-through Mode**: Make window transparent to clicks when needed
- **Cross-platform**: Works on macOS, Windows

## Setup

1. **Get a Gemini API Key**: Visit [Google AI Studio](https://aistudio.google.com/apikey)
2. **Install Dependencies**: `npm install`
3. **Run the App**: `npm start`

## Usage

1. Enter your Gemini API key in the main window
2. Choose your profile and language in settings
3. Click "Start Session" to begin
4. Position the window using keyboard shortcuts
5. The AI will provide real-time assistance based on your screen and what interview asks

## Keyboard Shortcuts

- **Window Movement**: `Ctrl/Cmd + Arrow Keys` - Move window
- **Click-through**: `Ctrl/Cmd + M` - Toggle mouse events
- **Close/Back**: `Ctrl/Cmd + \` - Close window or go back
- **Send Message**: `Enter` - Send text to AI

## Audio Capture

- **macOS**: [SystemAudioDump](https://github.com/Mohammed-Yasin-Mulla/Sound) for system audio
- **Windows**: Loopback audio capture
- **Linux**: Microphone input

## Requirements

- Electron-compatible OS (macOS, Windows, Linux)
- Gemini API key
- Screen recording permissions
- Microphone/audio permissions

## How You Can Build Installers

# Install deps
npm install

# Start app locally for dev
npm start

# Create packaged app for your OS
npm run package

# Create installer (exe/dmg/appimage)
npm run make


## Bypass SmartScreen/Gatekeeper

🚀 **How to Run Shadow Bot After Download**

🪟 **On Windows (SmartScreen Warning)**

- Double-click the downloaded .exe installer.

- If you see “Windows protected your PC”:

- Click More info.

- Click Run anyway.

- The installer will start normally.

🍏 **On macOS (Gatekeeper Warning)**

- Download the .dmg and drag Shadow Bot into Applications.

- The first time you try to open it, macOS may say: “Shadow Bot cannot be opened because it is from an unidentified developer.”

- To bypass: Open System Settings → Privacy & Security.

- Scroll down, you’ll see a message about Shadow Bot.

- Click Open Anyway.

- Confirm again when prompted.

- From then on, you can launch it like any other app.