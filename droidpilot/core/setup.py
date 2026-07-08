"""Bootstrap an Android SDK so DroidPilot can run on a fresh machine.

The heavy lifting (network download, unzip, running ``sdkmanager``) lives in
:func:`run_setup`, but the decision-making pieces are split into small pure
helpers (:func:`cmdline_tools_url`, :func:`default_install_root`,
:func:`build_setup_commands`) so they can be unit tested without touching the
network or the filesystem.
"""

from __future__ import annotations

import os
import platform
from pathlib import Path

# Google's command-line tools bundle. The build number is pinned but can be
# overridden via the ``DROIDPILOT_CMDLINE_TOOLS_BUILD`` environment variable.
_DEFAULT_CMDLINE_TOOLS_BUILD = "11076708"

# A Play Store enabled image so users can actually install games/apps.
DEFAULT_SYSTEM_IMAGE = "system-images;android-34;google_apis_playstore;x86_64"
DEFAULT_AVD_NAME = "droidpilot"
DEFAULT_DEVICE = "pixel_6"


def cmdline_tools_url(
    system: str | None = None,
    build: str | None = None,
) -> str:
    """Return the download URL for the command-line tools on ``system``.

    Args:
        system: ``platform.system()`` style value (``Windows``/``Darwin``/``Linux``).
        build: The build number to pin. Defaults to the module constant or the
            ``DROIDPILOT_CMDLINE_TOOLS_BUILD`` env var.
    """
    system = system or platform.system()
    build = build or os.environ.get("DROIDPILOT_CMDLINE_TOOLS_BUILD", _DEFAULT_CMDLINE_TOOLS_BUILD)
    platform_tag = {
        "Windows": "win",
        "Darwin": "mac",
        "Linux": "linux",
    }.get(system)
    if platform_tag is None:
        raise ValueError(f"Unsupported platform for SDK setup: {system!r}")
    return (
        "https://dl.google.com/android/repository/"
        f"commandlinetools-{platform_tag}-{build}_latest.zip"
    )


def default_install_root(
    environ: dict[str, str] | None = None,
    system: str | None = None,
) -> Path:
    """Return the directory the SDK should be installed into."""
    env = dict(os.environ if environ is None else environ)
    system = system or platform.system()
    if system == "Windows":
        local = env.get("LOCALAPPDATA")
        if local:
            return Path(local) / "Android" / "Sdk"
    if system == "Darwin":
        home = Path(env.get("HOME") or "~").expanduser()
        return home / "Library" / "Android" / "sdk"
    home = Path(env.get("HOME") or env.get("USERPROFILE") or "~").expanduser()
    return home / "Android" / "Sdk"


def _bin_suffix(system: str) -> str:
    return ".bat" if system == "Windows" else ""


def build_setup_commands(
    sdk_root: Path,
    *,
    system: str | None = None,
    system_image: str = DEFAULT_SYSTEM_IMAGE,
    avd_name: str = DEFAULT_AVD_NAME,
    device: str = DEFAULT_DEVICE,
) -> list[list[str]]:
    """Return the ordered commands that install packages and create the AVD.

    The command-line tools zip is assumed to already be unpacked into
    ``sdk_root/cmdline-tools/latest``.
    """
    system = system or platform.system()
    suffix = _bin_suffix(system)
    bin_dir = sdk_root / "cmdline-tools" / "latest" / "bin"
    sdkmanager = str(bin_dir / f"sdkmanager{suffix}")
    avdmanager = str(bin_dir / f"avdmanager{suffix}")
    sdk_flag = f"--sdk_root={sdk_root}"
    return [
        [sdkmanager, sdk_flag, "platform-tools", "emulator", "platforms;android-34", system_image],
        [avdmanager, "create", "avd", "--force", "--name", avd_name,
         "--package", system_image, "--device", device],
    ]


def _accept_licenses_input() -> bytes:
    """Bytes fed to ``sdkmanager --licenses`` to accept all prompts."""
    return b"y\n" * 100


def run_setup(
    sdk_root: Path | None = None,
    *,
    system_image: str = DEFAULT_SYSTEM_IMAGE,
    avd_name: str = DEFAULT_AVD_NAME,
    log=print,
) -> Path:  # pragma: no cover - performs real network + subprocess I/O
    """Download the command-line tools and install a runnable SDK + AVD.

    Returns the SDK root that was set up.
    """
    import io
    import subprocess
    import urllib.request
    import zipfile

    system = platform.system()
    root = Path(sdk_root) if sdk_root is not None else default_install_root()
    root.mkdir(parents=True, exist_ok=True)

    latest = root / "cmdline-tools" / "latest"
    if not (latest / "bin").exists():
        url = cmdline_tools_url(system)
        log(f"Downloading Android command-line tools from {url} …")
        with urllib.request.urlopen(url) as resp:  # noqa: S310 - trusted Google URL
            data = resp.read()
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            tmp = root / "cmdline-tools"
            tmp.mkdir(parents=True, exist_ok=True)
            zf.extractall(tmp)
            # The zip contains a top-level "cmdline-tools" dir; move it to "latest".
            extracted = tmp / "cmdline-tools"
            if extracted.exists():
                extracted.rename(latest)

    suffix = _bin_suffix(system)
    sdkmanager = str(latest / "bin" / f"sdkmanager{suffix}")
    log("Accepting SDK licenses …")
    subprocess.run(
        [sdkmanager, f"--sdk_root={root}", "--licenses"],
        input=_accept_licenses_input(),
        check=False,
    )
    for cmd in build_setup_commands(
        root, system=system, system_image=system_image, avd_name=avd_name
    ):
        log("Running: " + " ".join(cmd))
        subprocess.run(cmd, check=True)

    log(f"Done. SDK installed at {root} with AVD {avd_name!r}.")
    return root
