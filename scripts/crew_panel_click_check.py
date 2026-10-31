"""Drive the crew page in a real browser and check the panel opens on a node click
and closes on a canvas click. Run with the crew graph service up.

    python3 scripts/crew_panel_click_check.py --card t_611c7f18

Uses Chrome headless over the DevTools protocol. No page code is stubbed: the same
handlers the owner clicks are exercised.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import crew_proof_board  # noqa: E402

CHROME = crew_proof_board.find_chrome()
PORT = 9333


def http_json(path):
    with urllib.request.urlopen("http://127.0.0.1:%d%s" % (PORT, path), timeout=10) as fh:
        return json.loads(fh.read().decode())


def wait_for_target(url_fragment, tries=40):
    for _ in range(tries):
        try:
            for t in http_json("/json/list"):
                if t.get("type") == "page" and url_fragment in (t.get("url") or ""):
                    return t
        except Exception:
            pass
        time.sleep(0.5)
    return None


def evaluate(ws_url, expression):
    """One CDP call over our own stdlib websocket client: no third-party module needed."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from crew_ws import WSClient
    ws = WSClient(ws_url)
    try:
        return ws.evaluate(expression)
    finally:
        ws.close()


def ws_client(ws_url):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from crew_ws import WSClient
    return WSClient(ws_url)


def rect(ws, selector):
    """Centre of the first element matching `selector` in CSS pixels, or None."""
    return ws.evaluate("""
      (function(){
        var e = document.querySelector(%s);
        if(!e) return null;
        var r = e.getBoundingClientRect();
        if(!r.width || !r.height) return null;
        return {x: r.x + r.width/2, y: r.y + r.height/2, w: r.width, h: r.height,
                left: r.x, top: r.y};
      })()
    """ % json.dumps(selector))


_CID = [1]


def cdp(ws, method, params=None):
    """One CDP command with its own id (WSClient.call wants (id, method, params))."""
    _CID[0] += 1
    return ws.call(_CID[0], method, params or {})


def click_at(ws, x, y):
    """A real mouse click through CDP: the handlers the owner's mouse triggers, not a synthetic event.

    The page is React and its graph listens on pointer/mouse input at the stage, so a dispatched
    MouseEvent from page script is not the same thing (measured 2026-10-29: the synthetic click left
    the panel shut while a real one opens it).
    """
    for kind in ("mousePressed", "mouseReleased"):
        cdp(ws, "Input.dispatchMouseEvent",
            {"type": kind, "x": x, "y": y, "button": "left", "clickCount": 1})


def esc(ws):
    for kind in ("keyDown", "keyUp"):
        cdp(ws, "Input.dispatchKeyEvent", {"type": kind, "key": "Escape", "code": "Escape",
                                           "windowsVirtualKeyCode": 27, "nativeVirtualKeyCode": 27})


def panel_open(ws):
    return ws.evaluate("document.getElementById('panel').classList.contains('open')")


def wait_panel(ws, want, secs=8):
    end = time.time() + secs
    while time.time() < end:
        if panel_open(ws) is want:
            return True
        time.sleep(0.2)
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--card", required=True)
    ap.add_argument("--host", default="127.0.0.1:8799")
    args = ap.parse_args()

    if not CHROME:
        print("no chrome binary found"); return 2

    url = "http://%s/card/%s" % (args.host, args.card)
    profile = crew_proof_board.chrome_scratch("crew-click-")
    chrome_env = dict(os.environ, TMPDIR=profile, XDG_CACHE_HOME=os.path.join(profile, "cache"))
    proc = subprocess.Popen(
        [CHROME, "--headless=new", "--password-store=basic", "--disable-gpu", "--no-sandbox",
         "--remote-debugging-port=%d" % PORT, "--user-data-dir=" + profile,
         "--window-size=1400,760", url],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=chrome_env)

    checks = []
    ws = None
    try:
        target = wait_for_target("/card/")
        if not target:
            print("page never loaded"); return 2
        ws = ws_client(target["webSocketDebuggerUrl"])

        # wait until the page has drawn the graph
        n = 0
        for _ in range(40):
            n = ws.evaluate("document.querySelectorAll('#nodes .node, .nodes .node').length")
            if n:
                break
            time.sleep(0.5)
        checks.append(("graph drawn (%s nodes)" % n, bool(n)))

        checks.append(("panel starts closed", panel_open(ws) is False))

        node = rect(ws, "#nodes .node, .nodes .node")
        if not node:
            checks.append(("the page exposes a node and a stage", False))
        else:
            click_at(ws, node["x"], node["y"])
            checks.append(("node click opens the panel", wait_panel(ws, True)))

            # the stage re-flows when the docked panel opens, so the empty point is measured now
            stage = rect(ws, "#stage, .stage")
            if not stage:
                checks.append(("the page exposes a stage to click", False))
            else:
                sx = stage["left"] + stage["w"] * 0.12
                sy = stage["top"] + stage["h"] * 0.88
                click_at(ws, sx, sy)
                checks.append(("canvas click closes it", wait_panel(ws, False)))

                click_at(ws, node["x"], node["y"])
                opened = wait_panel(ws, True)
                esc(ws)
                checks.append(("esc closes it too", opened and wait_panel(ws, False)))

                click_at(ws, node["x"], node["y"])
                opened = wait_panel(ws, True)
                stage = rect(ws, "#stage, .stage") or stage
                sx = stage["left"] + stage["w"] * 0.12
                sy = stage["top"] + stage["h"] * 0.88
                # a drag across the stage, then a plain click: the drag must not leave the stage deaf
                cdp(ws, "Input.dispatchMouseEvent", {"type": "mousePressed", "x": sx, "y": sy,
                                                     "button": "left", "clickCount": 1})
                cdp(ws, "Input.dispatchMouseEvent", {"type": "mouseMoved", "x": sx + 60, "y": sy,
                                                     "button": "left"})
                cdp(ws, "Input.dispatchMouseEvent", {"type": "mouseReleased", "x": sx + 60, "y": sy,
                                                     "button": "left", "clickCount": 1})
                time.sleep(0.3)
                click_at(ws, sx, sy)
                checks.append(("a click after a drag still closes it", opened and wait_panel(ws, False)))
    finally:
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        shutil.rmtree(profile, ignore_errors=True)

    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print("%-42s %s" % (name, "PASS" if ok else "FAIL"))
    print("%d checks, %d passed, %d failed" % (len(checks), len(checks) - len(failed), len(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
