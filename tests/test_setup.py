from __future__ import annotations

from pathlib import Path

import pytest

from droidpilot.core.setup import (
    DEFAULT_SYSTEM_IMAGE,
    build_setup_commands,
    cmdline_tools_url,
    default_install_root,
)


@pytest.mark.parametrize(
    ("system", "tag"),
    [("Windows", "win"), ("Darwin", "mac"), ("Linux", "linux")],
)
def test_cmdline_tools_url_per_platform(system, tag):
    url = cmdline_tools_url(system, build="123")
    assert url == (
        f"https://dl.google.com/android/repository/commandlinetools-{tag}-123_latest.zip"
    )


def test_cmdline_tools_url_rejects_unknown_platform():
    with pytest.raises(ValueError):
        cmdline_tools_url("Plan9")


def test_default_install_root_windows_uses_localappdata():
    env = {"LOCALAPPDATA": r"C:\\Users\\me\\AppData\\Local"}
    root = default_install_root(env, system="Windows")
    assert root.name == "Sdk"
    assert "Android" in root.parts[-2]


def test_default_install_root_linux():
    root = default_install_root({"HOME": "/home/me"}, system="Linux")
    assert root == Path("/home/me/Android/Sdk")


def test_build_setup_commands_installs_and_creates_avd():
    root = Path("/opt/sdk")
    cmds = build_setup_commands(root, system="Linux", avd_name="droidpilot")
    assert len(cmds) == 2
    install, create = cmds

    assert install[0] == str(root / "cmdline-tools" / "latest" / "bin" / "sdkmanager")
    assert f"--sdk_root={root}" in install
    assert "platform-tools" in install and "emulator" in install
    assert DEFAULT_SYSTEM_IMAGE in install

    assert create[0] == str(root / "cmdline-tools" / "latest" / "bin" / "avdmanager")
    assert create[1:4] == ["create", "avd", "--force"]
    assert "droidpilot" in create
    assert DEFAULT_SYSTEM_IMAGE in create


def test_build_setup_commands_windows_uses_bat():
    cmds = build_setup_commands(Path("C:/sdk"), system="Windows")
    assert cmds[0][0].endswith("sdkmanager.bat")
    assert cmds[1][0].endswith("avdmanager.bat")
