
# =====================================================
# ESP32 MicroPython GitHub OTA 管理系統
# 版本：1.0.4
# 功能：Wi-Fi、登入、GitHub 版本檢查、自動定時檢查
# =====================================================

import network
import socket
import time
import gc
import json
import machine
import ubinascii
import os

try:
    import requests
except ImportError:
    import urequests as requests

# -----------------------------
# 1. Wi-Fi 設定
# -----------------------------

HOST = "esp32"
SSID = "labor"
PASSWORD = "98668800"

# -----------------------------
# 2. OTA 版本設定
# -----------------------------

CURRENT_VERSION = "1.0.4"

BASE_URL = (
    "https://mjcky.github.io/"
    "OTAWebUpdater_1019-mjcky/"
)

VERSION_URL = BASE_URL + "version.json"

OTA_CHECK_INTERVAL = 6 * 60 * 60 * 1000
last_ota_check = time.ticks_ms()

# 網頁登入帳號
LOGIN_USER = "admin"
LOGIN_PASSWORD = "admin"

# 每次開機產生一個簡單的工作階段識別碼
try:
    SESSION_TOKEN = ubinascii.hexlify(
        os.urandom(16)
    ).decode()
except Exception:
    SESSION_TOKEN = ubinascii.hexlify(
        machine.unique_id()
    ).decode()

# -----------------------------
# 3. Wi-Fi 連線
# -----------------------------

wifi = network.WLAN(network.STA_IF)
wifi.active(True)


def connect_wifi():
    if wifi.isconnected():
        return True

    print("正在連接 Wi-Fi：", SSID)
    wifi.connect(SSID, PASSWORD)

    start = time.ticks_ms()

    while not wifi.isconnected():
        if time.ticks_diff(
            time.ticks_ms(), start
        ) >= 30000:
            print("Wi-Fi 連線逾時")
            return False

        time.sleep(1)

    print("Wi-Fi 連線成功")
    print("IP 位址：", wifi.ifconfig()[0])
    return True


# -----------------------------
# 4. 版本號比較
# -----------------------------

def parse_version(version):
    version = str(version).strip()

    if version[:1].lower() == "v":
        version = version[1:]

    parts = version.split(".")

    if len(parts) != 3:
        return None

    values = []

    for part in parts:
        if not part or not part.isdigit():
            return None

        values.append(int(part))

    return tuple(values)


def is_newer_version(remote, current):
    r = parse_version(remote)
    c = parse_version(current)

    if r is None or c is None:
        return False

    return r > c


# -----------------------------
# 5. 取得 GitHub version.json
# -----------------------------

def fetch_remote_version():
    if not wifi.isconnected():
        print("[OTA] Wi-Fi 未連線")
        return None

    response = None

    try:
        print("[OTA] 正在讀取 version.json")

        response = requests.get(VERSION_URL)

        if response.status_code != 200:
            print(
                "[OTA] HTTP 錯誤：",
                response.status_code
            )
            return None

        data = response.json()

        remote_version = data.get("version")
        firmware_url = data.get("firmware")

        if not isinstance(remote_version, str):
            print("[OTA] 缺少 version")
            return None

        if not isinstance(firmware_url, str):
            print("[OTA] 缺少 firmware")
            return None

        if parse_version(remote_version) is None:
            print("[OTA] 版本格式錯誤")
            return None

        # 限制韌體網址必須位於指定 GitHub Pages 路徑
        if not firmware_url.startswith(BASE_URL):
            print("[OTA] 韌體網址不符合允許的路徑")
            return None

        print("[OTA] GitHub 版本：", remote_version)

        return {
            "version": remote_version,
            "firmware": firmware_url
        }

    except Exception as e:
        print("[OTA] 讀取版本失敗：", e)
        return None

    finally:
        if response is not None:
            try:
                response.close()
            except Exception:
                pass

        gc.collect()


# -----------------------------
# 6. 檢查是否有新版本
# -----------------------------

def check_for_update():
    if not wifi.isconnected():
        return "Wi-Fi 未連線，無法檢查更新"

    print("[OTA] 開始檢查 GitHub 版本")

    data = fetch_remote_version()

    if data is None:
        return "讀取 version.json 失敗"

    remote_version = data["version"]
    firmware_url = data["firmware"]

    print("[OTA] 本機版本：", CURRENT_VERSION)
    print("[OTA] 遠端版本：", remote_version)
    print("[OTA] 韌體網址：", firmware_url)

    if is_newer_version(
        remote_version, CURRENT_VERSION
    ):
        return (
            "發現新版本：" + remote_version +
            "。目前僅完成版本檢查，尚未燒錄韌體。"
        )

    return "目前已是最新版本：" + CURRENT_VERSION


# -----------------------------
# 7. 登入頁面
# -----------------------------

LOGIN_PAGE = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport"
 content="width=device-width, initial-scale=1">
<title>ESP32 登入</title>
</head>
<body>
<h2>ESP32 GitHub OTA 登入</h2>

<form action="/login" method="POST">
帳號：<input name="userid" required><br><br>
密碼：<input name="pwd" type="password" required><br><br>
<button type="submit">登入</button>
</form>
</body>
</html>
"""

# -----------------------------
# 8. OTA 管理頁面
# -----------------------------

ADMIN_PAGE = """<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport"
 content="width=device-width, initial-scale=1">
<title>ESP32 OTA 管理</title>
</head>
<body>
<h2>ESP32 GitHub OTA 管理</h2>

<p id="version">讀取版本中...</p>

<button onclick="getVersion()">重新讀取版本</button>
<button onclick="checkUpdate()">檢查 GitHub 更新</button>

<p id="result"></p>

<hr>
<p>目前為 MicroPython 版本檢查測試版。</p>
<p>真正的韌體 OTA 尚未啟用。</p>

<script>
async function getVersion() {
  try {
    const r = await fetch('/status');
    const d = await r.json();

    document.getElementById('version').textContent =
      '本機版本：' + d.local +
      '；GitHub 版本：' + (d.remote || '讀取失敗');
  } catch(e) {
    document.getElementById('version').textContent =
      '讀取版本失敗';
  }
}

async function checkUpdate() {
  document.getElementById('result').textContent =
    '正在檢查更新...';

  try {
    const r = await fetch('/check', {
      method: 'POST'
    });

    document.getElementById('result').textContent =
      await r.text();

    getVersion();
  } catch(e) {
    document.getElementById('result').textContent =
      '連線失敗';
  }
}

getVersion();
</script>
</body>
</html>
"""


# -----------------------------
# 9. HTTP 回應工具
# -----------------------------

def send_response(
    client, status, content_type, body, extra_headers=""
):
    if isinstance(body, str):
        body = body.encode("utf-8")

    header = (
        "HTTP/1.1 " + status + "\r\n"
        "Content-Type: " + content_type + "\r\n"
        "Content-Length: " + str(len(body)) + "\r\n"
        "Connection: close\r\n"
        "Cache-Control: no-store\r\n"
        + extra_headers +
        "\r\n"
    )

    client.sendall(
        header.encode("utf-8") + body
    )


def url_decode(value):
    value = value.replace("+", " ")
    result = bytearray()
    i = 0

    while i < len(value):
        if (
            value[i] == "%"
            and i + 2 < len(value)
        ):
            try:
                result.append(
                    int(value[i + 1:i + 3], 16)
                )
                i += 3
                continue
            except ValueError:
                pass

        result.extend(value[i].encode("utf-8"))
        i += 1

    return result.decode("utf-8", "replace")


def parse_form(body):
    data = {}

    for item in body.split("&"):
        pair = item.split("=", 1)

        if len(pair) == 2:
            data[url_decode(pair[0])] = url_decode(
                pair[1]
            )

    return data


# -----------------------------
# 10. HTTP 伺服器
# -----------------------------

def start_server():
    address = socket.getaddrinfo(
        "0.0.0.0", 80
    )[0][-1]

    server = socket.socket()
    server.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1
    )
    server.bind(address)
    server.listen(3)

    print("網頁伺服器已啟動")
    print("網址：http://" + wifi.ifconfig()[0])

    return server


# -----------------------------
# 11. 處理瀏覽器請求
# -----------------------------

def handle_client(client):
    client.settimeout(3)

    # 讀取 HTTP 標頭
    raw = b""

    while b"\r\n\r\n" not in raw:
        chunk = client.recv(1024)

        if not chunk:
            return

        raw += chunk

        if len(raw) > 8192:
            send_response(
                client, "413 Payload Too Large",
                "text/plain", "請求太大"
            )
            return

    header_bytes, body = raw.split(
        b"\r\n\r\n", 1
    )

    headers = header_bytes.decode(
        "utf-8", "ignore"
    )

    lines = headers.split("\r\n")
    first = lines[0].split(" ")

    if len(first) < 2:
        return

    method = first[0]
    path = first[1].split("?", 1)[0]

    content_length = 0
    cookie = ""

    for line in lines[1:]:
        if ":" not in line:
            continue

        name, value = line.split(":", 1)
        name = name.strip().lower()
        value = value.strip()

        if name == "content-length":
            try:
                content_length = int(value)
            except ValueError:
                content_length = 0

        elif name == "cookie":
            cookie = value

    # 讀取完整 POST 內容
    while len(body) < content_length:
        chunk = client.recv(1024)

        if not chunk:
            break

        body += chunk

    body_text = body[:content_length].decode(
        "utf-8", "ignore"
    )

    # 登入處理
    if path == "/login" and method == "POST":
        form = parse_form(body_text)

        if (
            form.get("userid") == LOGIN_USER
            and form.get("pwd") == LOGIN_PASSWORD
        ):
            send_response(
                client, "303 See Other",
                "text/plain", "登入成功",
                "Location: /serverIndex\r\n"
                "Set-Cookie: session=" +
                SESSION_TOKEN +
                "; HttpOnly; SameSite=Strict; Path=/\r\n"
            )
        else:
            send_response(
                client, "401 Unauthorized",
                "text/plain; charset=utf-8",
                "帳號或密碼錯誤"
            )

        return

    # 驗證管理頁面的工作階段
    authorized = (
        "session=" + SESSION_TOKEN
    ) in cookie

    protected = (
        path == "/serverIndex"
        or path == "/status"
        or path == "/check"
    )

    if protected and not authorized:
        send_response(
            client, "401 Unauthorized",
            "text/plain; charset=utf-8",
            "請先登入"
        )
        return

    if path == "/":
        send_response(
            client, "200 OK",
            "text/html; charset=utf-8",
            LOGIN_PAGE
        )

    elif path == "/serverIndex":
        send_response(
            client, "200 OK",
            "text/html; charset=utf-8",
            ADMIN_PAGE
        )

    elif path == "/status":
        data = fetch_remote_version()

        result = {
            "local": CURRENT_VERSION,
            "remote": (
                data["version"] if data else ""
            )
        }

        send_response(
            client, "200 OK",
            "application/json; charset=utf-8",
            json.dumps(result)
        )

    elif path == "/check" and method == "POST":
        send_response(
            client, "200 OK",
            "text/plain; charset=utf-8",
            check_for_update()
        )

    else:
        send_response(
            client, "404 Not Found",
            "text/plain; charset=utf-8",
            "找不到此頁面"
        )


# -----------------------------
# 12. 主程式
# -----------------------------

if not connect_wifi():
    raise RuntimeError("Wi-Fi 連線失敗")

server = start_server()

# 開機時檢查一次
print(check_for_update())
last_ota_check = time.ticks_ms()

while True:
    client = None

    try:
        if not wifi.isconnected():
            connect_wifi()

        now = time.ticks_ms()

        # 每六小時檢查一次
        if time.ticks_diff(
            now, last_ota_check
        ) >= OTA_CHECK_INTERVAL:
            last_ota_check = now
            print(check_for_update())

        client, remote = server.accept()
        handle_client(client)

    except Exception as e:
        print("處理請求時發生錯誤：", e)

    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

        gc.collect()
