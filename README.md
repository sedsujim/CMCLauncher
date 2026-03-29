# CMC Launcher

A lightweight, custom Minecraft launcher focused on performance, profile management, and mod support.

---

## Features

- **Profile Management** - Stored as JSON files in `profiles/`
- **Version Downloads** - Automatically downloads and launches Minecraft versions using `minecraft-launcher-lib`
- **Mod Manager** - Enable/disable mods with a simple UI
- **Discord Rich Presence** - Display your current game status on Discord
- **Flexible Configuration** - Settings stored in `config/config.json`
- **Detailed Logging** - All operations logged to `logs/` directory

---

## Project Structure

```
CMCLauncher/
├── core/              # Core modules: installer, Java utils, helpers
├── config/            # Configuration files (config.json)
├── profiles/          # Individual profile files (<id>.json)
├── assets/            # Resources (icon.png, background.png, click.wav, etc.)
├── logs/              # Installation and error logs
├── main.py            # Main application entry point
├── requirements.txt   # Python dependencies
└── README.md          # This file
```

---

## Requirements

- **Python 3.10+**
- **Java** (version depends on Minecraft version - see Java notes below)
- **Internet connection** for downloading Minecraft versions

### Install Dependencies

```bash
pip install -r requirements.txt
```

> **Recommended:** Use a virtual environment (venv)

---

## Installation and Setup

### Usually, in the realeases part will be the .flatpak, *FINALLY* , so :

```bash
flatpak install cmclauncher.flatpak
```

### ofc taking in count that the file is in the same folder as your terminal
---

## Quick Start Guide

1. **Create a Profile**
   - Navigate to the **Profiles** tab
   - Enter an internal ID, display name, and in-game player name
   - Click **Save**

2. **Launch Minecraft**
   - Go to the **Play** tab
   - Select your profile and desired Minecraft version
   - Click **PLAY**
   - The launcher will automatically download the version if needed

3. **Check Logs**
   - If installation fails, check the `logs/` directory for error details

---

## Java Version Requirements

Different Minecraft versions require different Java versions:

| Minecraft Version | Required Java Version |
|-------------------|-----------------------|
| 1.7.x - 1.16.x    | Java 8                |
| 1.17.x - 1.20.4   | Java 17               |
| 1.20.5+           | Java 21               |

### Troubleshooting Java Issues

- **Old versions (≤ 1.16.x)** typically require **Java 8**
- Attempting to launch 1.8.x or 1.16.5 with Java 17/21 may fail due to native library incompatibilities
- The launcher includes Java detection utilities
- You can select the appropriate Java binary in the **Options** tab

---

## Mod Management

1. Navigate to the **Mods** tab
2. Click **Add Mod** to select a `.jar` file
3. Double-click any mod in the list to enable/disable it
4. Disabled mods are moved to `mods/disabled/`

---

## Troubleshooting

### Version Download Fails

- Check `logs/install-<version>-<timestamp>.log` for detailed error messages
- Common causes:
  - Network connectivity issues
  - Mojang server downtime
  - Insufficient disk space
  - Permission issues

### Minecraft Crashes on Launch

- **Check Java version** - Ensure you're using the correct Java version for your Minecraft version
- **Review logs** - Check the latest log file in `logs/`
- **Verify installation** - Delete the version folder and re-download

### Discord Rich Presence Not Working

- Ensure Discord is running
- Verify you've uploaded art assets in the Discord Developer Portal
- Check that your Client ID is correct in `config/config.json`

---

## Git Quick Reference

### Initial Setup

```bash
# Initialize repository
git init

# Add all files
git add .

# Create initial commit
git commit -m "Initial commit - CMC Launcher"

# Add remote (create repo on GitHub first)
git remote add origin https://github.com/YOUR_USERNAME/CMCLauncher.git

# Push to main branch
git branch -M main
git push -u origin main
```

### Configure Git Identity

```bash
git config --global user.name "Your Name"
git config --global user.email "your-email@example.com"
```

### Recommended `.gitignore`

Create a `.gitignore` file with the following content:

```gitignore
# Virtual environment
venv/
env/

# Python cache
__pycache__/
*.pyc
*.pyo
*.pyd

# Logs
*.log
logs/

# Configuration (optional - remove if you want to share configs)
config/config.json

# Profiles (optional - keep profiles local)
profiles/*.json

# Minecraft directory (avoid uploading entire .minecraft folder)
minecraft/
.minecraft/

# Build artifacts
dist/
build/
*.spec

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db
```

---

## Building Releases

### Windows (PyInstaller)

```bash
pip install pyinstaller
pyinstaller --onefile --windowed main.py --add-data "assets;assets" --name CMCLauncher
```

The executable will be in the `dist/` folder.

### Linux (PyInstaller)

```bash
pip install pyinstaller
pyinstaller --onefile --windowed main.py --add-data "assets:assets" --name CMCLauncher
```

### Creating GitHub Releases

1. Go to your repository on GitHub
2. Click **Releases** → **Create a new release**
3. Tag the version (e.g., `v1.0.0`)
4. Upload the built executables as assets
5. Write release notes
6. Publish

---

## Configuration Reference

### `config/config.json`

```json
{
  "last_version": "1.20.1",
  "default_ram_gb": 4,
  "rpc_client_id": "YOUR_DISCORD_CLIENT_ID",
  "java_paths": {}
}
```

| Field | Description |
|-------|-------------|
| `last_version` | Last Minecraft version used |
| `default_ram_gb` | Default RAM allocation (in GB) |
| `rpc_client_id` | Discord application Client ID |
| `java_paths` | Custom Java installation paths |

### Profile Format (`profiles/<id>.json`)

```json
{
  "display_name": "My Profile",
  "player_name": "PlayerName",
  "ram_gb": 4
}
```

---

## Contributing

This is a personal project. If you'd like to contribute:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## License

This project is personal. If you wish to use or distribute it, please contact the author.

For open-source distribution, consider adding an MIT or GPL license.

---

## Support

If you encounter issues:

1. Check the `logs/` directory for error details
2. Review the Troubleshooting section above
3. Open an issue on GitHub with:
   - Error message
   - Log files
   - Steps to reproduce
   - System information (OS, Python version, Java version)

---

## Roadmap

- [ ] Online authentication support (Microsoft/Mojang accounts)
- [ ] Automatic mod updates (CurseForge/Modrinth integration)
- [ ] Multiple instance support
- [ ] Shader pack manager
- [ ] Resource pack manager
- [ ] Server list integration
- [ ] Automatic Java installation

---

*in progress flatpak thingy lol*
