"""
Desktop control module for the AI assistant.

Allows the assistant to interact with the user's desktop:
- Take screenshots
- Type on the keyboard
- Control windows and browser tabs
- Send messages to other Claude Code instances

On Linux: uses standard tools (xdotool, wmctrl, scrot, xclip).
On Windows: uses pyautogui, pyperclip, and PowerShell.
"""

import asyncio
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import structlog

from src.utils.platform import IS_WINDOWS

log = structlog.get_logger("assistant.desktop_control")


class DesktopControl:
    """Controls the desktop environment."""

    async def take_screenshot(self, region: str | None = None) -> str:
        """Capture screenshot, return path to PNG file.

        Args:
            region: Optional region "x,y,width,height" or None for full screen
        """
        fd, output = tempfile.mkstemp(suffix=".png", prefix="screenshot_")
        os.close(fd)

        if IS_WINDOWS:
            return await self._screenshot_windows(output)
        return await self._screenshot_linux(output)

    async def _screenshot_linux(self, output: str) -> str:
        """Linux screenshot using scrot/gnome-screenshot/import."""
        for tool, cmd in [
            ("scrot", ["scrot", output]),
            ("gnome-screenshot", ["gnome-screenshot", "-f", output]),
            ("import", ["import", "-window", "root", output]),
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

    async def _screenshot_windows(self, output: str) -> str:
        """Windows screenshot using pyautogui or PIL."""
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

    async def type_text(self, text: str, delay_ms: int = 50) -> None:
        """Type text using xdotool (Linux) or pyautogui (Windows)."""
        if IS_WINDOWS:
            self._require_module("pyautogui")
            import pyautogui
            await asyncio.to_thread(
                pyautogui.typewrite, text, interval=delay_ms / 1000.0
            )
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
        """Press key combination. E.g., press_keys("ctrl", "t") for new tab.

        Common keys: ctrl, alt, shift, super, Tab, Return, Escape,
        F1-F12, Left, Right, Up, Down, Home, End, Page_Up, Page_Down
        """
        if IS_WINDOWS:
            self._require_module("pyautogui")
            import pyautogui
            await asyncio.to_thread(pyautogui.hotkey, *keys)
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
        """List all open windows."""
        if IS_WINDOWS:
            return await self._list_windows_windows()
        return await self._list_windows_linux()

    async def _list_windows_linux(self) -> list[dict]:
        """List windows via wmctrl."""
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

    async def _list_windows_windows(self) -> list[dict]:
        """List windows via PowerShell."""
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
        """Bring a window to front by ID or title match."""
        if IS_WINDOWS:
            return await self._focus_window_windows(window_id, title_match)
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

    async def _focus_window_windows(self, window_id: str, title_match: str) -> bool:
        """Focus window via PowerShell."""
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
        """Switch browser tab. direction: 'next' or 'prev'."""
        if direction == "next":
            await self.press_keys("ctrl", "Tab")
        else:
            await self.press_keys("ctrl", "shift", "Tab")
        log.info("desktop.browser_tab", direction=direction)

    async def go_to_browser_tab(self, tab_number: int) -> None:
        """Go to specific browser tab by number (1-9)."""
        if 1 <= tab_number <= 9:
            await self.press_keys("ctrl", str(tab_number))
            log.info("desktop.browser_tab_number", tab=tab_number)

    async def list_browser_tabs_cdp(self, port: int = 9222) -> list[dict]:
        """List ALL browser tabs via Chrome DevTools Protocol (CDP).

        Requires Chrome/Chromium started with --remote-debugging-port=9222.
        Returns list of dicts with: id, title, url, type, active.
        Returns empty list if CDP is not available.
        """
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
        """Scan ALL open browser tabs by iterating Ctrl+Tab.

        Works for ALL browsers (Chrome, Firefox, Edge, etc.) without CDP.
        Reads window title at each step to capture tab title.
        Stops when a title repeats (full cycle) or max_tabs is reached.

        Returns list of dicts: {index, title, screenshot_path (optional)}.
        """
        if IS_WINDOWS:
            get_title_cmd = None  # use PowerShell fallback
        else:
            if not shutil.which("xdotool"):
                raise RuntimeError("xdotool no instalado. Ejecuta: sudo apt install xdotool")

        async def _get_window_title() -> str:
            """Get the active window title."""
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

        # Record the starting tab title
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

            # Detect full cycle: browser window title goes back to the start
            # (strip browser suffix like "- Chromium", "- Firefox", "- Google Chrome")
            def _strip_browser(t: str) -> str:
                for suffix in (" - Chromium", " - Google Chrome", " - Chrome",
                               " - Mozilla Firefox", " - Firefox", " - Microsoft Edge"):
                    if t.endswith(suffix):
                        return t[:-len(suffix)]
                return t

            stripped = _strip_browser(title)
            first_stripped = _strip_browser(seen_titles[0]) if seen_titles else ""

            # Cycle complete if we're back at the first tab
            if i > 0 and stripped == first_stripped:
                log.info("desktop.scan_tabs_cycle_complete", total=len(tabs))
                break

            tabs.append({"index": i, "title": title})
            seen_titles.append(title)

        log.info("desktop.scan_all_tabs", found=len(tabs))
        return tabs

    async def send_to_claude_code(self, message: str, window_title: str = "Claude") -> bool:
        """Send a message to another Claude Code CLI instance.

        Finds the window with Claude Code, focuses it, types the message,
        and presses Enter to send it.
        """
        # Find Claude Code window
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

        if not IS_WINDOWS:
            self._require("xdotool")
            # Save current active window to return to it later
            current_proc = await asyncio.create_subprocess_exec(
                "xdotool", "getactivewindow",
                stdout=asyncio.subprocess.PIPE,
            )
            current_stdout, _ = await current_proc.communicate()
            current_window = current_stdout.decode().strip()
        else:
            current_window = None

        # Focus Claude Code window
        await self.focus_window(window_id=target["id"])
        await asyncio.sleep(0.5)  # Wait for focus

        # Type the message and press Enter
        await self.type_text(message)
        await asyncio.sleep(0.2)
        await self.press_keys("Return")

        log.info("desktop.sent_to_claude", message_length=len(message), window=target["title"])

        # Return to previous window (Linux only — xdotool)
        await asyncio.sleep(0.3)
        if current_window and not IS_WINDOWS:
            await asyncio.create_subprocess_exec(
                "xdotool", "windowactivate", current_window,
                stdout=asyncio.subprocess.PIPE,
            )

        return True

    async def get_clipboard(self) -> str:
        """Get clipboard content."""
        if IS_WINDOWS:
            self._require_module("pyperclip")
            import pyperclip
            return await asyncio.to_thread(pyperclip.paste)

        self._require("xclip")
        proc = await asyncio.create_subprocess_exec(
            "xclip", "-selection", "clipboard", "-o",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        return stdout.decode()

    async def set_clipboard(self, text: str) -> None:
        """Set clipboard content."""
        if IS_WINDOWS:
            self._require_module("pyperclip")
            import pyperclip
            await asyncio.to_thread(pyperclip.copy, text)
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
        """Check which desktop control tools are available."""
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

        tools = {}
        for tool in ["xdotool", "wmctrl", "scrot", "xclip", "gnome-screenshot"]:
            tools[tool] = shutil.which(tool) is not None
        return tools

    async def install_tools(self) -> str:
        """Install missing desktop control tools."""
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
        """Require a system tool (Linux)."""
        if not shutil.which(tool):
            raise RuntimeError(
                f"'{tool}' not installed. Run: sudo apt install {tool}"
            )

    @staticmethod
    def _require_module(module: str) -> None:
        """Require a Python module (Windows)."""
        try:
            __import__(module)
        except ImportError:
            raise RuntimeError(
                f"'{module}' not installed. Run: pip install {module}"
            )
