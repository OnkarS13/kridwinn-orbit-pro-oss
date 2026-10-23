# Kridwinn Orbit Pro

Windows desktop application (PySide6) for a GIS print-server production workflow:
PDF preparation, RIP rendering and multi-server printing.

## Features

- **PDF Desk** – merge, split, page-dimension checks, page imposition
- **PDF PREP** – CMYK region colour conversion, DPI, scaling, margins, rotation, reversing, blank pages
- **RIP Engine** – PDF → image → RIP on one or more GIS print servers
- **Print Engine (GIS)** – single/dual-server RIP-to-print with live status, print history and production logs
- **GIS Server Config** – manage and test print-server connections
- **Build CSV** – CSV generation from folders
- Offline licensing with RSA-signed `.lic` files (one-time online activation)

## Requirements

- Windows 10/11 x64
- Python 3.12
- For builds: Visual Studio 2022 C++ build tools (MSVC) and Inno Setup 6

## Run from source

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt

# Secrets are not stored in this repository. Provide them via environment variables:
$env:KRIDWINN_CONFIG_KEY      = "<fernet key>"
$env:KRIDWINN_ACTIVATION_SALT = "<activation salt>"
$env:KRIDWINN_ADMIN_SALT      = "<admin salt>"
# Place the encrypted runtime config in secure_config\ (firebase_creds.enc, licensing_config.enc)

.\.venv\Scripts\python app.py
```

## Build the installer locally

```powershell
# Same environment variables as above, plus FIREBASE_CREDS_ENC_B64 / LICENSING_CONFIG_ENC_B64
# (or put the .enc files in secure_config\ yourself)
powershell -ExecutionPolicy Bypass -File .\build.ps1
```

Output: `dist\installer\KridwinnOrbitPro-Setup.exe`

## CI build and code signing

`.github/workflows/build.yml` builds the app with Nuitka and the installer with Inno Setup on
`windows-latest`. It runs on manual dispatch and on `v*` tags (tags also create a GitHub Release).

### Repository secrets

| Secret | Purpose |
|---|---|
| `KRIDWINN_CONFIG_KEY` | Fernet key that decrypts `secure_config/*.enc` |
| `KRIDWINN_ACTIVATION_SALT` | Salt for the local activation-data encryption key |
| `KRIDWINN_ADMIN_SALT` | Salt for the admin-password store encryption key |
| `FIREBASE_CREDS_ENC_B64` | Base64 of `secure_config/firebase_creds.enc` |
| `LICENSING_CONFIG_ENC_B64` | Base64 of `secure_config/licensing_config.enc` |
| `SIGNPATH_API_TOKEN` | SignPath CI user API token (signing only) |

### Repository variables (signing)

Signing runs only when `SIGNPATH_ORGANIZATION_ID` is set.

| Variable | Example |
|---|---|
| `SIGNPATH_ORGANIZATION_ID` | SignPath organization ID |
| `SIGNPATH_PROJECT_SLUG` | `kridwinn-orbit-pro` |
| `SIGNPATH_SIGNING_POLICY_SLUG` | `release-signing` |
| `SIGNPATH_ARTIFACT_CONFIGURATION_SLUG` | `default` |

The SignPath artifact configuration is in `.signpath/artifact-configuration.xml`.
Both the application EXE and the installer are Authenticode-signed.

## Licensing tools

- `tools/license_tool.py` – generate RSA key pairs and create/verify signed `.lic` files
  (keep the private key outside the repository)
- `backend/telegram_bot.py` – optional Telegram admin bot (configured via environment variables)

## Code signing policy

Free code signing provided by [SignPath.io](https://signpath.io), certificate by
[SignPath Foundation](https://signpath.org).

- Committers and reviewers: [repository members](../../graphs/contributors)
- Approvers: repository owner
- Signed artifacts are built only by the GitHub Actions workflow in this repository.

## Privacy

On first activation the application contacts Google Firebase once to register the license
to the machine ID. No other data is transmitted. Connections to GIS print servers are made
only to the servers configured by the user on the local network.

## License

[MIT](LICENSE)
