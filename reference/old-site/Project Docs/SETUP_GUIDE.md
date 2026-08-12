# Betting Odds Extractor — Windows Setup Guide

This app runs **fully offline** on your computer using a free local AI model.
No internet required after setup. No API costs. Ever.

---

## What you'll be installing

| Tool | What it does | Cost |
|------|-------------|------|
| Python | Runs the app | Free |
| Ollama | Runs the local AI model | Free |
| LLaVA | The vision AI model that reads images | Free |
| openpyxl / Pillow | Python packages for Excel + image preview | Free |

---

## Step 1 — Install Python

1. Go to **https://www.python.org/downloads/**
2. Click the big yellow **"Download Python 3.x.x"** button
3. Run the installer
4. ⚠️ **Important:** On the first screen, check the box that says **"Add Python to PATH"** before clicking Install
5. Click **Install Now** and wait for it to finish

**To verify it worked:** Open the Start menu, search for **Command Prompt**, open it, and type:
```
python --version
```
You should see something like `Python 3.12.0`

---

## Step 2 — Install required Python packages

In the same Command Prompt window, copy and paste this line and press Enter:

```
pip install openpyxl Pillow
```

Wait for it to finish (you'll see "Successfully installed" messages).

---

## Step 3 — Install Ollama

1. Go to **https://ollama.com/download**
2. Click **Download for Windows**
3. Run the installer — it installs like any normal Windows app
4. Once installed, Ollama runs quietly in the background (you'll see its icon in your system tray near the clock)

---

## Step 4 — Download the LLaVA vision model

This is the AI that actually reads your images. It's about **4 GB**, so make sure you have space and a decent internet connection for this one-time download.

1. Open **Command Prompt**
2. Type this and press Enter:
```
ollama pull llava
```
3. Wait for the download to complete — you'll see a progress bar

**This is the only time you need internet.** After this, everything runs offline.

---

## Step 5 — Run the app

1. Copy the file **odds_extractor.py** to somewhere easy to find (e.g. your Desktop)
2. **Double-click** odds_extractor.py to launch it

> If double-clicking doesn't work, right-click the file → **Open with** → **Python**
>
> Or open Command Prompt, navigate to the file, and run:
> ```
> python odds_extractor.py
> ```

---

## How to use the app

1. **Click the blue box** to browse for your odds screenshot
2. **Date settings:** If the image shows the date, leave this alone — the AI will read it automatically. If there's no date in the image, check the box and type the date manually.
3. **Click "Extract odds"** — the AI will analyse the image (takes 20–60 seconds)
4. Rows appear in the table on the right, and are **automatically saved to Excel**
5. The Excel file is saved to your Desktop as `betting_odds.xlsx` by default (you can change this path in the app)
6. **Repeat** for as many images as you want — all rows accumulate in the same Excel file
7. Click **"Download / open Excel"** to open the file at any time

---

## Troubleshooting

**"Cannot connect to Ollama"**
→ Ollama isn't running. Open the Start menu, search for **Ollama**, and launch it. The icon should appear in your system tray.

**App won't open / Python error**
→ Make sure you checked "Add Python to PATH" during install. If you missed it, re-run the Python installer and choose "Modify", then check that box.

**Extraction is slow**
→ This is normal — the local AI model takes 20–60 seconds per image depending on your PC. Faster machines with a dedicated GPU will be quicker.

**AI returns wrong/empty data**
→ Try a cleaner, higher-resolution screenshot. Very small or blurry images reduce accuracy. You can always re-run the same image.

**"pip is not recognized"**
→ Python wasn't added to PATH. Re-run the Python installer → Modify → check "Add Python to PATH".

---

## Your Excel file

Each row in the spreadsheet represents one team from one game. Columns include:

- **Date** — from the image or manually entered
- **Bet Type** — Moneyline, Spread, or Total
- **Game ID** — the number shown next to the team
- **Status** — Final, Live, etc.
- **Team** — team name
- **Home/Away**
- **Opening** — the opening odds
- **One column per sportsbook** — all odds values

New images are always **appended** to the existing file, never overwriting old data.

---

## Keeping Ollama running automatically

By default, Ollama starts with Windows. If it ever stops:
- Search "Ollama" in the Start menu and relaunch it
- Or go to Task Manager → Startup and make sure Ollama is enabled
