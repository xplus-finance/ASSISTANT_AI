"""Desktop control: screenshots, keyboard, windows, clipboard."""

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import structlog

from src.utils.platform import IS_MACOS, IS_WINDOWS

log = structlog.get_logger("assistant.desktop_control")


class DesktopControl:


    async def take_screenshot(self, region: str | None = None) -> str:
        fd, output = tempfile.mkstemp(suffix=".png", prefix="screenshot_")
        os.close(fd)

        if IS_WINDOWS:
            return await self._screenshot_windows(output)
        elif IS_MACOS:
            return await self._screenshot_macos(output)
        return await self._screenshot_linux(output)

    async def _clear_selection(self) -> None:
        """Release stuck modifiers and deselect text in key windows before screenshot."""
        if not shutil.which("xdotool"):
            return
        try:
            # 1. Release ALL modifier keys that might be stuck
            for key in ("shift", "ctrl", "alt", "super", "Meta_L", "Meta_R"):
                proc = await asyncio.create_subprocess_exec(
                    "xdotool", "keyup", key,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(proc.communicate(), timeout=2)

            await asyncio.sleep(0.1)

            # 2. Remember current active window to restore focus later
            original_window = None
            try:
                proc = await asyncio.create_subprocess_exec(
                    "xdotool", "getactivewindow",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3)
                original_window = stdout.decode().strip()
            except Exception:
                pass

            # 3. Find VS Code / editors / browsers and send Escape to deselect
            #    These are the apps most likely to have text selected (blue highlight)
            if shutil.which("wmctrl"):
                proc = await asyncio.create_subprocess_exec(
                    "wmctrl", "-l",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
                for line in stdout.decode().strip().split("\n"):
                    parts = line.split(None, 3)
                    if len(parts) < 4:
                        continue
                    wid, title = parts[0], parts[3].lower()
                    # Only clear selection in editors and browsers
                    if any(k in title for k in ("visual studio code", "code - ",
                                                 "sublime", "gedit", "kate",
                                                 "firefox", "chrome", "chromium")):
                        try:
                            proc = await asyncio.create_subprocess_exec(
                                "xdotool", "windowactivate", "--sync", wid,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE,
                            )
                            await asyncio.wait_for(proc.communicate(), timeout=2)
                            await asyncio.sleep(0.1)
                            for _ in range(2):
                                proc = await asyncio.create_subprocess_exec(
                                    "xdotool", "key", "--clearmodifiers", "Escape",
                                    stdout=asyncio.subprocess.PIPE,
                                    stderr=asyncio.subprocess.PIPE,
                                )
                                await asyncio.wait_for(proc.communicate(), timeout=2)
                                await asyncio.sleep(0.1)
                        except Exception:
                            continue

            # 4. Restore original window focus
            if original_window:
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "xdotool", "windowactivate", original_window,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await asyncio.wait_for(proc.communicate(), timeout=2)
                except Exception:
                    pass

            await asyncio.sleep(0.3)
        except Exception:
            pass

    async def _screenshot_linux(self, output: str) -> str:
        # Clear any selection/highlight before capturing
        await self._clear_selection()

        # Prefer import (ImageMagick) — silent, no overlay/flash
        # Then scrot, then gnome-screenshot (last: it can cause blue flash)
        for tool, cmd in [
            ("import", ["import", "-window", "root", output]),
            ("scrot", ["scrot", "-o", output]),
            ("gnome-screenshot", ["gnome-screenshot", "-f", output]),
        ]:
            if shutil.which(tool):
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(proc.communicate(), timeout=10)
                if proc.returncode == 0 and Path(output).exists():
                    log.info("desktop.screenshot", tool=tool, path=output)
                    return output

        raise RuntimeError(
            "No screenshot tool available. Install one: sudo apt install scrot"
        )

    async def _screenshot_macos(self, output: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "screencapture", "-x", output,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode == 0 and Path(output).exists():
            log.info("desktop.screenshot", tool="screencapture", path=output)
            return output
        raise RuntimeError(
            "screencapture failed. This is a built-in macOS tool and should always be available."
        )

    async def _screenshot_windows(self, output: str) -> str:
        try:
            import pyautogui
            img = pyautogui.screenshot()
            img.save(output)
            log.info("desktop.screenshot", tool="pyautogui", path=output)
            return output
        except ImportError:
            pass

        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            img.save(output)
            log.info("desktop.screenshot", tool="PIL.ImageGrab", path=output)
            return output
        except ImportError:
            pass

        raise RuntimeError(
            "No screenshot tool available. Install: pip install pyautogui"
        )

    async def take_screenshots_per_monitor(self) -> list[tuple[str, str]]:
        """Take separate screenshots for each monitor on Linux.

        Returns list of (path, caption) tuples.
        Uses xrandr to detect monitors and scrot -a for per-monitor capture.
        """
        if IS_WINDOWS or IS_MACOS:
            path = await self.take_screenshot()
            return [(path, "Captura de pantalla")]

        await self._clear_selection()

        # Parse xrandr for connected monitors
        monitors: list[tuple[str, int, int, int, int]] = []  # name, w, h, x, y
        if shutil.which("xrandr"):
            proc = await asyncio.create_subprocess_exec(
                "xrandr", "--query",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            import re
            for line in stdout.decode().splitlines():
                m = re.search(r"(\S+)\s+connected.*?(\d+)x(\d+)\+(\d+)\+(\d+)", line)
                if m:
                    monitors.append((
                        m.group(1),
                        int(m.group(2)), int(m.group(3)),
                        int(m.group(4)), int(m.group(5)),
                    ))

        if not monitors:
            path = await self.take_screenshot()
            return [(path, "Captura de pantalla")]

        # Sort by X offset (left to right)
        monitors.sort(key=lambda m: m[3])
        results: list[tuple[str, str]] = []
        labels = ["izquierdo", "derecho", "tercero", "cuarto"]

        # Strategy: capture full desktop ONCE (silent, no overlay), then crop per monitor
        fd_full, full_path = tempfile.mkstemp(suffix=".png", prefix="screenshot_full_")
        os.close(fd_full)

        captured_full = False
        # Prefer import (silent) over scrot over gnome-screenshot
        for tool, cmd in [
            ("import", ["import", "-window", "root", full_path]),
            ("scrot", ["scrot", "-o", full_path]),
            ("gnome-screenshot", ["gnome-screenshot", "-f", full_path]),
        ]:
            if shutil.which(tool):
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(proc.communicate(), timeout=10)
                if proc.returncode == 0 and Path(full_path).exists() and Path(full_path).stat().st_size > 0:
                    captured_full = True
                    log.info("desktop.screenshot_full", tool=tool, path=full_path)
                    break

        if not captured_full:
            try:
                Path(full_path).unlink(missing_ok=True)
            except Exception:
                pass
            path = await self.take_screenshot()
            return [(path, "Captura de pantalla")]

        # Crop each monitor from the full image using convert (ImageMagick)
        for i, (name, w, h, x, y) in enumerate(monitors):
            fd, output = tempfile.mkstemp(suffix=".png", prefix=f"screenshot_mon{i}_")
            os.close(fd)
            label = labels[i] if i < len(labels) else f"monitor {i+1}"

            if shutil.which("convert"):
                proc = await asyncio.create_subprocess_exec(
                    "convert", full_path, "-crop", f"{w}x{h}+{x}+{y}", "+repage", output,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(proc.communicate(), timeout=10)
                if proc.returncode == 0 and Path(output).exists() and Path(output).stat().st_size > 0:
                    results.append((output, f"Monitor {label} ({name})"))
                    log.info("desktop.screenshot_monitor", monitor=name, label=label, path=output)
                    continue

            # Fallback if convert not available: use ffmpeg to crop
            if shutil.which("ffmpeg"):
                proc = await asyncio.create_subprocess_exec(
                    "ffmpeg", "-y", "-i", full_path,
                    "-vf", f"crop={w}:{h}:{x}:{y}",
                    output,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(proc.communicate(), timeout=10)
                if proc.returncode == 0 and Path(output).exists() and Path(output).stat().st_size > 0:
                    results.append((output, f"Monitor {label} ({name})"))
                    log.info("desktop.screenshot_monitor", monitor=name, label=label, path=output)
                    continue

            # Last resort: send the full screenshot
            results.append((full_path, f"Monitor {label} ({name}) — completo"))
            break

        # Clean up full screenshot
        try:
            Path(full_path).unlink(missing_ok=True)
        except Exception:
            pass

        return results if results else [(await self.take_screenshot(), "Captura de pantalla")]

    async def type_text(self, text: str, delay_ms: int = 50) -> None:
        if IS_WINDOWS:
            self._require_module("pyautogui")
            import pyautogui
            await asyncio.to_thread(
                pyautogui.typewrite, text, interval=delay_ms / 1000.0
            )
        elif IS_MACOS:
            escaped = text.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
            script = f'tell application "System Events" to keystroke "{escaped}"'
            proc = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=30)
        else:
            self._require("xdotool")
            proc = await asyncio.create_subprocess_exec(
                "xdotool", "type", "--delay", str(delay_ms), "--clearmodifiers", text,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=30)
        log.info("desktop.typed", length=len(text))

    async def press_keys(self, *keys: str) -> None:
        if IS_WINDOWS:
            self._require_module("pyautogui")
            import pyautogui
            await asyncio.to_thread(pyautogui.hotkey, *keys)
        elif IS_MACOS:
            modifier_map = {
                "ctrl": "command down",  # macOS convention: Ctrl → Cmd
                "alt": "option down",
                "shift": "shift down",
                "super": "command down",
                "command": "command down",
                "cmd": "command down",
                "option": "option down",
            }
            modifiers = []
            keystroke = None
            for k in keys:
                lower = k.lower()
                if lower in modifier_map:
                    mod = modifier_map[lower]
                    if mod not in modifiers:
                        modifiers.append(mod)
                else:
                    keystroke = k
            if keystroke:
                if modifiers:
                    mods = ", ".join(modifiers)
                    script = f'tell application "System Events" to keystroke "{keystroke}" using {{{mods}}}'
                else:
                    script = f'tell application "System Events" to keystroke "{keystroke}"'
                proc = await asyncio.create_subprocess_exec(
                    "osascript", "-e", script,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await asyncio.wait_for(proc.communicate(), timeout=10)
        else:
            self._require("xdotool")
            combo = "+".join(keys)
            proc = await asyncio.create_subprocess_exec(
                "xdotool", "key", "--clearmodifiers", combo,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await asyncio.wait_for(proc.communicate(), timeout=10)
        log.info("desktop.key_press", keys="+".join(keys))

    async def list_windows(self) -> list[dict]:
        if IS_WINDOWS:
            return await self._list_windows_windows()
        elif IS_MACOS:
            return await self._list_windows_macos()
        return await self._list_windows_linux()

    async def _list_windows_linux(self) -> list[dict]:
        self._require("wmctrl")
        proc = await asyncio.create_subprocess_exec(
            "wmctrl", "-l",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)

        windows = []
        for line in stdout.decode().strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split(None, 3)
            if len(parts) >= 4:
                windows.append({
                    "id": parts[0],
                    "desktop": parts[1],
                    "host": parts[2],
                    "title": parts[3],
                })
        return windows

    async def _list_windows_macos(self) -> list[dict]:
        script = 'tell application "System Events" to get name of every process whose visible is true'
        proc = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)

        windows = []
        output = stdout.decode().strip()
        if output:
            for i, name in enumerate(output.split(", ")):
                name = name.strip()
                if name:
                    windows.append({
                        "id": str(i),
                        "desktop": "0",
                        "host": "localhost",
                        "title": name,
                    })
        return windows

    async def _list_windows_windows(self) -> list[dict]:
        ps_cmd = (
            "Get-Process | Where-Object {$_.MainWindowTitle -ne ''} "
            "| Select-Object Id, MainWindowTitle "
            "| ForEach-Object { \"$($_.Id)|$($_.MainWindowTitle)\" }"
        )
        proc = await asyncio.create_subprocess_exec(
            "powershell", "-Command", ps_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)

        windows = []
        for line in stdout.decode().strip().split("\n"):
            line = line.strip()
            if not line or "|" not in line:
                continue
            pid, title = line.split("|", 1)
            windows.append({
                "id": pid.strip(),
                "desktop": "0",
                "host": "localhost",
                "title": title.strip(),
            })
        return windows

    async def focus_window(self, window_id: str = "", title_match: str = "") -> bool:
        if IS_WINDOWS:
            return await self._focus_window_windows(window_id, title_match)
        elif IS_MACOS:
            return await self._focus_window_macos(window_id, title_match)
        return await self._focus_window_linux(window_id, title_match)

    async def _focus_window_linux(self, window_id: str, title_match: str) -> bool:
        self._require("wmctrl")
        if window_id:
            cmd = ["wmctrl", "-i", "-a", window_id]
        elif title_match:
            cmd = ["wmctrl", "-a", title_match]
        else:
            return False

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=10)
        log.info("desktop.focus_window", id=window_id, title=title_match)
        return proc.returncode == 0

    async def _focus_window_macos(self, window_id: str, title_match: str) -> bool:
        app_name = title_match if title_match else None

        if not app_name and window_id:
            windows = await self._list_windows_macos()
            for w in windows:
                if w["id"] == window_id:
                    app_name = w["title"]
                    break

        if not app_name:
            return False

        escaped = app_name.replace('"', '\\"')
        script = f'tell application "{escaped}" to activate'
        proc = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=10)
        log.info("desktop.focus_window", id=window_id, title=title_match)
        return proc.returncode == 0

    async def _focus_window_windows(self, window_id: str, title_match: str) -> bool:
        if window_id:
            window_id = str(int(window_id))  # Sanitize: raises ValueError if not numeric
            ps_cmd = (
                f"$p = Get-Process -Id {window_id} -ErrorAction SilentlyContinue; "
                "if ($p) { "
                "[void][System.Reflection.Assembly]::LoadWithPartialName('Microsoft.VisualBasic'); "
                "[Microsoft.VisualBasic.Interaction]::AppActivate($p.Id) }"
            )
        elif title_match:
            title_match = title_match.replace("'", "''")  # PowerShell single-quote escape
            ps_cmd = (
                "[void][System.Reflection.Assembly]::LoadWithPartialName('Microsoft.VisualBasic'); "
                f"[Microsoft.VisualBasic.Interaction]::AppActivate('{title_match}')"
            )
        else:
            return False

        proc = await asyncio.create_subprocess_exec(
            "powershell", "-Command", ps_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=10)
        log.info("desktop.focus_window", id=window_id, title=title_match)
        return proc.returncode == 0

    async def switch_browser_tab(self, direction: str = "next") -> None:
        if direction == "next":
            await self.press_keys("ctrl", "Tab")
        else:
            await self.press_keys("ctrl", "shift", "Tab")
        log.info("desktop.browser_tab", direction=direction)

    async def go_to_browser_tab(self, tab_number: int) -> None:
        if 1 <= tab_number <= 9:
            await self.press_keys("ctrl", str(tab_number))
            log.info("desktop.browser_tab_number", tab=tab_number)

    async def list_browser_tabs_cdp(self, port: int = 9222) -> list[dict]:
        try:
            import urllib.request
            url = f"http://localhost:{port}/json/list"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=2) as resp:
                import json
                data = json.loads(resp.read().decode())
            tabs = []
            for i, item in enumerate(data):
                if item.get("type") in ("page", "tab", None):
                    tabs.append({
                        "index": i,
                        "id": item.get("id", ""),
                        "title": item.get("title", "(sin título)"),
                        "url": item.get("url", ""),
                        "active": False,  # CDP no expone cual es la activa directamente
                        "type": item.get("type", "page"),
                    })
            log.info("desktop.cdp_tabs", count=len(tabs), port=port)
            return tabs
        except Exception as e:
            log.debug("desktop.cdp_not_available", port=port, error=str(e))
            return []

    async def scan_all_tabs(self, max_tabs: int = 60, delay_ms: int = 400) -> list[dict]:
        if IS_WINDOWS:
            get_title_cmd = None  # use PowerShell fallback
        elif IS_MACOS:
            pass  # osascript is always available
        else:
            if not shutil.which("xdotool"):
                raise RuntimeError("xdotool no instalado. Ejecuta: sudo apt install xdotool")

        async def _get_window_title() -> str:
            if IS_WINDOWS:
                ps = (
                    "Add-Type -AssemblyName System.Windows.Forms; "
                    "[System.Windows.Forms.Screen]::PrimaryScreen | Out-Null; "
                    "$wnd = [System.Runtime.InteropServices.Marshal]::GetForegroundWindow(); "
                    "$buf = [System.Text.StringBuilder]::new(256); "
                    "[void][System.Runtime.InteropServices.Marshal]::; "
                    "Get-Process | Where-Object {$_.MainWindowHandle -eq $wnd} "
                    "| Select-Object -ExpandProperty MainWindowTitle"
                )
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "powershell", "-Command", ps,
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                    )
                    out, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
                    return out.decode().strip()
                except Exception:
                    return ""
            elif IS_MACOS:
                script = (
                    'tell application "System Events"\n'
                    '    set frontApp to name of first application process whose frontmost is true\n'
                    '    return frontApp\n'
                    'end tell'
                )
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "osascript", "-e", script,
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                    )
                    out, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
                    return out.decode().strip()
                except Exception:
                    return ""
            else:
                try:
                    proc = await asyncio.create_subprocess_exec(
                        "xdotool", "getactivewindow", "getwindowname",
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
                    )
                    out, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
                    return out.decode().strip()
                except Exception:
                    return ""

        tabs = []
        seen_titles: list[str] = []

        first_title = await _get_window_title()
        if first_title:
            tabs.append({"index": 0, "title": first_title})
            seen_titles.append(first_title)

        for i in range(1, max_tabs):
            await self.switch_browser_tab("next")
            await asyncio.sleep(delay_ms / 1000.0)

            title = await _get_window_title()
            if not title:
                continue

            def _strip_browser(t: str) -> str:
                for suffix in (" - Chromium", " - Google Chrome", " - Chrome",
                               " - Mozilla Firefox", " - Firefox", " - Microsoft Edge"):
                    if t.endswith(suffix):
                        return t[:-len(suffix)]
                return t

            stripped = _strip_browser(title)
            first_stripped = _strip_browser(seen_titles[0]) if seen_titles else ""

            if i > 0 and stripped == first_stripped:
                log.info("desktop.scan_tabs_cycle_complete", total=len(tabs))
                break

            tabs.append({"index": i, "title": title})
            seen_titles.append(title)

        log.info("desktop.scan_all_tabs", found=len(tabs))
        return tabs

    async def send_to_claude_code(self, message: str, window_title: str = "Claude") -> bool:
        windows = await self.list_windows()
        target = None
        for w in windows:
            title_lower = w["title"].lower()
            if window_title.lower() in title_lower or "claude" in title_lower:
                target = w
                break

        if not target:
            log.warning("desktop.claude_window_not_found", search=window_title)
            return False

        if IS_MACOS:
            script = (
                'tell application "System Events" to get name of first '
                'application process whose frontmost is true'
            )
            proc = await asyncio.create_subprocess_exec(
                "osascript", "-e", script,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await proc.communicate()
            current_window = out.decode().strip() or None
        elif not IS_WINDOWS:
            self._require("xdotool")
            current_proc = await asyncio.create_subprocess_exec(
                "xdotool", "getactivewindow",
                stdout=asyncio.subprocess.PIPE,
            )
            current_stdout, _ = await current_proc.communicate()
            current_window = current_stdout.decode().strip()
        else:
            current_window = None

        await self.focus_window(window_id=target["id"])
        await asyncio.sleep(0.5)  # Wait for focus

        await self.type_text(message)
        await asyncio.sleep(0.2)
        await self.press_keys("Return")

        log.info("desktop.sent_to_claude", message_length=len(message), window=target["title"])

        await asyncio.sleep(0.3)
        if current_window and IS_MACOS:
            escaped = current_window.replace('"', '\\"')
            await asyncio.create_subprocess_exec(
                "osascript", "-e", f'tell application "{escaped}" to activate',
                stdout=asyncio.subprocess.PIPE,
            )
        elif current_window and not IS_WINDOWS:
            await asyncio.create_subprocess_exec(
                "xdotool", "windowactivate", current_window,
                stdout=asyncio.subprocess.PIPE,
            )

        return True

    async def get_clipboard(self) -> str:
        if IS_WINDOWS:
            self._require_module("pyperclip")
            import pyperclip
            return await asyncio.to_thread(pyperclip.paste)

        if IS_MACOS:
            proc = await asyncio.create_subprocess_exec(
                "pbpaste",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            return stdout.decode()

        self._require("xclip")
        proc = await asyncio.create_subprocess_exec(
            "xclip", "-selection", "clipboard", "-o",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        return stdout.decode()

    async def set_clipboard(self, text: str) -> None:
        if IS_WINDOWS:
            self._require_module("pyperclip")
            import pyperclip
            await asyncio.to_thread(pyperclip.copy, text)
            return

        if IS_MACOS:
            proc = await asyncio.create_subprocess_exec(
                "pbcopy",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
            )
            proc.stdin.write(text.encode())
            proc.stdin.close()
            await asyncio.wait_for(proc.wait(), timeout=5)
            return

        self._require("xclip")
        proc = await asyncio.create_subprocess_exec(
            "xclip", "-selection", "clipboard",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
        )
        proc.stdin.write(text.encode())
        proc.stdin.close()
        await asyncio.wait_for(proc.wait(), timeout=5)

    async def check_tools(self) -> dict[str, bool]:
        if IS_WINDOWS:
            tools = {}
            for mod in ["pyautogui", "pyperclip"]:
                try:
                    __import__(mod)
                    tools[mod] = True
                except ImportError:
                    tools[mod] = False
            tools["powershell"] = shutil.which("powershell") is not None
            return tools

        if IS_MACOS:
            tools = {}
            for tool in ["screencapture", "osascript", "pbcopy", "pbpaste"]:
                tools[tool] = shutil.which(tool) is not None
            return tools

        tools = {}
        for tool in ["xdotool", "wmctrl", "scrot", "xclip", "gnome-screenshot"]:
            tools[tool] = shutil.which(tool) is not None
        return tools

    async def install_tools(self) -> str:
        if IS_WINDOWS:
            missing = []
            for mod in ["pyautogui", "pyperclip"]:
                try:
                    __import__(mod)
                except ImportError:
                    missing.append(mod)

            if not missing:
                return "All desktop control tools are already installed."

            return (
                f"Missing Python packages: {', '.join(missing)}\n"
                f"Install with: pip install {' '.join(missing)}"
            )

        if IS_MACOS:
            optional_missing = []
            for tool in ["cliclick"]:
                if not shutil.which(tool):
                    optional_missing.append(tool)

            if not optional_missing:
                return "All desktop control tools are already installed (macOS native tools included)."

            if shutil.which("brew"):
                proc = await asyncio.create_subprocess_exec(
                    "brew", "install", *optional_missing,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
                if proc.returncode == 0:
                    return f"Installed optional tools: {', '.join(optional_missing)}"
                else:
                    return f"Failed to install: {stderr.decode()[:200]}"
            else:
                return (
                    "macOS native tools (screencapture, osascript, pbcopy, pbpaste) are available.\n"
                    f"Optional tools not found: {', '.join(optional_missing)}\n"
                    "Install Homebrew first (https://brew.sh), then: brew install "
                    + " ".join(optional_missing)
                )

        # Linux
        missing = []
        for tool in ["xdotool", "wmctrl", "scrot", "xclip"]:
            if not shutil.which(tool):
                missing.append(tool)

        if not missing:
            return "All desktop control tools are already installed."

        proc = await asyncio.create_subprocess_exec(
            "sudo", "apt", "install", "-y", *missing,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)

        if proc.returncode == 0:
            return f"Installed: {', '.join(missing)}"
        else:
            return f"Failed to install: {stderr.decode()[:200]}"

    @staticmethod
    def _require(tool: str) -> None:
        if not shutil.which(tool):
            raise RuntimeError(
                f"'{tool}' not installed. Run: sudo apt install {tool}"
            )

    @staticmethod
    def _require_module(module: str) -> None:
        try:
            __import__(module)
        except ImportError:
            raise RuntimeError(
                f"'{module}' not installed. Run: pip install {module}"
            )
