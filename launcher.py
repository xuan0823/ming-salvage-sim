"""桌面打包入口：起 uvicorn 子线程 → 用 pywebview 套壳渲染 React UI。

PyInstaller 入口（spec 里的 entry_script）即此文件。

退出策略：webview 关窗 → webview.start() 返回 → 进程结束 → uvicorn daemon 线程随之销毁。

调试用 env：
  MING_DEBUG=1            打开 webview devtools + uvicorn info 日志
  MING_USE_BROWSER=1      不开 webview，回退到系统浏览器（pywebview 行为异常时用）
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.parse
import webbrowser

# Windows windowed (--noconsole) 下 sys.stdout/stderr = None。uvicorn 的
# DefaultFormatter.__init__ 调 sys.stdout.isatty() 判颜色 → AttributeError 崩。
# 先给 None 的标准流兜一个假写流（带 isatty()→False），再 reconfigure。
import io


class _NullStream(io.TextIOBase):
    @property
    def encoding(self) -> str:
        return "utf-8"

    def isatty(self) -> bool:
        return False

    def write(self, s: str) -> int:
        return len(s)

    def flush(self) -> None:
        pass


if sys.stdout is None:
    sys.stdout = _NullStream()  # type: ignore[assignment]
if sys.stderr is None:
    sys.stderr = _NullStream()  # type: ignore[assignment]

# 强制 unbuffered，PyInstaller 包内 print 否则可能丢
try:
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    sys.stderr.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
except Exception:
    pass


def _log(msg: str) -> None:
    """同时写 stdout + ~/.ming_sim/launcher.log，方便 .app 双击模式 debug。"""
    line = f"[launcher] {msg}"
    print(line, flush=True)
    try:
        from ming_sim.paths import user_data_dir
        log_path = user_data_dir() / "launcher.log"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


WINDOW_TITLE = "明末力挽狂澜"
WINDOW_WIDTH = 1366
WINDOW_HEIGHT = 880
WINDOW_MIN_WIDTH = 1024
WINDOW_MIN_HEIGHT = 720


def _find_free_port(preferred: int | None = 8010) -> int:
    """preferred 可用就用；传 None/0 则直接让系统分配。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if not preferred:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]
        try:
            s.bind(("127.0.0.1", preferred))
            return preferred
        except OSError:
            _log(f"端口 {preferred} 已被占用，改用系统随机端口。")
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]
    finally:
        s.close()


def _launcher_port_preference() -> int | None:
    raw = os.environ.get("MING_PORT", "").strip() or os.environ.get("PORT", "").strip()
    if not raw:
        return 8010
    try:
        port = int(raw)
    except ValueError:
        _log(f"MING_PORT/PORT={raw!r} 非法，改用随机端口。")
        return None
    return port if port > 0 else None


def _wait_server_ready(url: str, timeout: float = 15.0) -> bool:
    """轮询 / 直到返回任意 HTTP 状态（包括 404）。
    只要 server 有响应说明 uvicorn 已 listen；urlopen 对 4xx/5xx 会抛 HTTPError，
    那也算就绪——区分是 connection error 还是 HTTP 响应。"""
    import urllib.error
    import urllib.request
    proxy_handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler)
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            opener.open(url, timeout=0.5)
            return True
        except urllib.error.HTTPError:
            # 有 HTTP 响应（如 404）= server 已就绪
            return True
        except Exception:
            time.sleep(0.15)
    return False


_server_error: str = ""


def _read_launcher_log(max_bytes: int = 120_000) -> dict[str, object]:
    from ming_sim.paths import user_data_dir
    data_dir = user_data_dir()
    log_path = data_dir / "launcher.log"
    if not log_path.exists():
        return {
            "data_dir": str(data_dir),
            "log_path": str(log_path),
            "exists": False,
            "content": "",
        }
    with open(log_path, "rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        if size > max_bytes:
            f.seek(-max_bytes, os.SEEK_END)
            raw = f.read()
            content = raw.decode("utf-8", errors="replace")
            content = f"（仅显示最近 {max_bytes} 字节，完整日志见文件）\n\n{content}"
        else:
            f.seek(0)
            content = f.read().decode("utf-8", errors="replace")
    return {
        "data_dir": str(data_dir),
        "log_path": str(log_path),
        "exists": True,
        "content": content,
    }


def _open_user_data_dir() -> str:
    from ming_sim.paths import user_data_dir
    data_dir = user_data_dir()
    if os.name == "nt":
        os.startfile(str(data_dir))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(data_dir)])
    else:
        subprocess.Popen(["xdg-open", str(data_dir)])
    return str(data_dir)


class LauncherDebugApi:
    def get_launcher_log(self) -> dict[str, object]:
        return _read_launcher_log()

    def open_data_dir(self) -> dict[str, object]:
        return {"ok": True, "data_dir": _open_user_data_dir()}


def _debug_html(title: str, message: str) -> str:
    import html
    safe_title = html.escape(title)
    safe_message = html.escape(message)
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>{safe_title}</title>
  <style>
    body {{ margin: 0; background: #160f0a; color: #f3e6c4; font: 14px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    main {{ max-width: 920px; margin: 0 auto; padding: 36px 28px; }}
    h1 {{ margin: 0 0 10px; color: #f3d88b; font-size: 24px; }}
    p {{ margin: 8px 0 18px; color: #d8c590; }}
    button {{ margin-right: 10px; padding: 8px 16px; border-radius: 6px; border: 1px solid rgba(226,180,86,.45); background: rgba(255,245,215,.1); color: #f3e6c4; cursor: pointer; }}
    pre {{ min-height: 360px; max-height: 58vh; overflow: auto; white-space: pre-wrap; word-break: break-word; padding: 14px; border: 1px solid rgba(226,180,86,.25); border-radius: 6px; background: rgba(0,0,0,.34); }}
  </style>
</head>
<body>
  <main>
    <h1>{safe_title}</h1>
    <p>{safe_message}</p>
    <p id="paths">读取日志中...</p>
    <button onclick="openDir()">打开存档目录</button>
    <button onclick="loadLog()">刷新日志</button>
    <pre id="log">读取中...</pre>
  </main>
  <script>
    async function loadLog() {{
      try {{
        const info = await window.pywebview.api.get_launcher_log();
        document.getElementById('paths').textContent = '存档目录：' + info.data_dir + ' | 日志：' + info.log_path;
        document.getElementById('log').textContent = info.exists ? (info.content || 'launcher.log 为空。') : '尚未找到 launcher.log。';
      }} catch (err) {{
        document.getElementById('log').textContent = String(err);
      }}
    }}
    async function openDir() {{
      await window.pywebview.api.open_data_dir();
    }}
    window.addEventListener('pywebviewready', loadLog);
  </script>
</body>
</html>"""


def _show_debug_window(title: str, message: str, debug: bool) -> None:
    try:
        import webview
        webview.create_window(
            title,
            html=_debug_html(title, message),
            width=980,
            height=720,
            min_size=(760, 520),
            js_api=LauncherDebugApi(),
            confirm_close=False,
        )
        webview.start(debug=debug, http_server=False)
    except Exception:
        try:
            _open_user_data_dir()
        except Exception:
            pass


def _start_server(port: int, debug: bool) -> None:
    """uvicorn 子线程入口。listen 全 loopback：localhost 解析可能走 IPv6 ::1。
    子线程内崩溃会被 daemon 吞掉，主线程只见超时——故全程兜异常写日志，
    并把错误存 _server_error 供主线程展示。"""
    global _server_error
    try:
        # Agno initializes asyncio primitives at import time. In a non-main
        # launcher thread Python may not have a current loop, especially in
        # frozen pywebview builds, so create one before importing web_app.
        import asyncio
        try:
            asyncio.get_event_loop()
        except RuntimeError:
            asyncio.set_event_loop(asyncio.new_event_loop())
        import uvicorn
        from web_app import app
        _log("web_app 导入成功，uvicorn.run 启动中...")
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=port,
            log_level="info",  # 强制 info 确保看到 GET 行
        )
    except Exception as e:
        import traceback
        _server_error = f"{e!r}\n{traceback.format_exc()}"
        _log(f"uvicorn 子线程崩溃：{_server_error}")


def _open_browser_fallback(url: str) -> None:
    """pywebview 不可用 / 用户主动选浏览器模式时走这条。"""
    print(f"[launcher] 浏览器模式：{url}")
    print("[launcher] 关闭本窗口即停服。")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    # 阻塞主线程让 uvicorn daemon 不退
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


def main() -> None:
    debug = bool(os.environ.get("MING_DEBUG"))
    use_browser = bool(os.environ.get("MING_USE_BROWSER"))

    _log(f"启动：frozen={getattr(sys,'frozen',False)} platform={sys.platform} py={sys.version.split()[0]}")

    port = _find_free_port(_launcher_port_preference())
    # WKWebView 对 IP 偶有 bug；用 localhost 域名走 DNS 解析更稳
    api_base = f"http://127.0.0.1:{port}"
    url = f"http://localhost:{port}?api={urllib.parse.quote(api_base, safe=':/')}"
    _log(f"分配端口 {port} url={url}")

    # uvicorn 跑 daemon 线程，主线程留给 pywebview / 浏览器 fallback
    server_thread = threading.Thread(target=_start_server, args=(port, debug), daemon=True)
    server_thread.start()
    _log("uvicorn 子线程已启动，等待就绪...")

    if not _wait_server_ready(url):
        if _server_error:
            message = f"服务启动超时（>15s）——子线程已崩，根因：\n{_server_error}"
        else:
            message = "服务启动超时（>15s）——子线程未崩但 15s 内未 listen（可能首次冷启过慢/被防火墙拦）。"
        _log(message)
        _show_debug_window("启动失败 · 调试", message, debug)
        return
    _log(f"服务已就绪：{url}")

    if use_browser:
        _log("MING_USE_BROWSER=1，走系统浏览器。")
        _open_browser_fallback(url)
        return

    try:
        import webview  # pywebview
        _log(f"pywebview 导入成功")
    except Exception as e:
        _log(f"pywebview 导入失败：{e!r}，回退浏览器。")
        _open_browser_fallback(url)
        return

    try:
        webview.create_window(
            WINDOW_TITLE,
            url,
            width=WINDOW_WIDTH,
            height=WINDOW_HEIGHT,
            min_size=(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT),
            js_api=LauncherDebugApi(),
            confirm_close=False,
        )
        _log("create_window 完成，调用 webview.start()...")
        # debug=True 打开 devtools（Mac 右键 Inspect Element）；http_server=False 因 server 已自起
        webview.start(debug=debug, http_server=False)
        _log("webview 已关闭，正常退出。")
    except Exception as e:
        _log(f"webview 启动崩溃：{e!r}")
        import traceback
        tb = traceback.format_exc()
        _log(tb)
        _log("回退浏览器模式。")
        _open_browser_fallback(url)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[launcher] 已停。")
    except Exception:
        import traceback
        traceback.print_exc()
        try:
            input("\n出错了，按 Enter 关闭窗口…")
        except Exception:
            pass
        sys.exit(1)
