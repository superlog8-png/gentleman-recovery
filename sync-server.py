from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
STATE_FILE = DATA_DIR / "sync-state.json"

ORDER_STATUSES = ["已確認", "收單", "按摩中", "已結束"]

DEFAULT_STATE = {
    "orders": [
        {
            "id": "#GR-1027",
            "customer": "會員顧客",
            "service": "紳士舒壓",
            "area": "高雄市鼓山區",
            "address": "高雄市鼓山區美術東二路 100 號 8 樓",
            "time": "今晚 20:30",
            "price": "$1,500",
            "status": "已確認",
            "therapist": "阿杰",
            "note": "肩頸、腰背放鬆",
        },
        {
            "id": "#GR-1028",
            "customer": "林先生",
            "service": "深層修復",
            "area": "高雄市三民區",
            "address": "高雄市三民區建國一路 220 號 5 樓",
            "time": "今晚 22:00",
            "price": "$2,000",
            "status": "收單",
            "therapist": "Leo",
            "note": "久坐肩背痠痛",
        },
    ]
}

STATUS_MAP = {
    "待確認": "已確認",
    "已接單": "收單",
    "進行中": "按摩中",
    "已完成": "已結束",
}


def load_state():
    if not STATE_FILE.exists():
        save_state(DEFAULT_STATE)
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    changed = False
    for order in state.get("orders", []):
        status = order.get("status")
        if status in STATUS_MAP:
            order["status"] = STATUS_MAP[status]
            changed = True
        elif status not in ORDER_STATUSES:
            order["status"] = "已確認"
            changed = True
    if changed:
        save_state(state)
    return state


def save_state(state):
    DATA_DIR.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def next_order_id(orders):
    numbers = []
    for order in orders:
        match = re.search(r"(\d+)$", order.get("id", ""))
        if match:
            numbers.append(int(match.group(1)))
    return f"#GR-{(max(numbers) if numbers else 1029) + 1}"


class SyncHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/orders":
            self.write_json(load_state()["orders"])
            return
        if path == "/api/state":
            self.write_json(load_state())
            return
        self.write_json({"ok": True, "message": "Gentleman Recovery sync server"})

    def do_POST(self):
        if urlparse(self.path).path != "/api/orders":
            self.send_error(404)
            return
        payload = self.read_json()
        state = load_state()
        order = {
            "id": next_order_id(state["orders"]),
            "customer": payload.get("customer") or "會員顧客",
            "service": payload.get("service") or "",
            "area": payload.get("area") or "",
            "address": payload.get("address") or "",
            "time": payload.get("time") or "",
            "price": payload.get("price") or "",
            "status": "已確認",
            "therapist": "未指派",
            "note": payload.get("note") or "",
        }
        state["orders"].insert(0, order)
        save_state(state)
        self.write_json(order, 201)

    def do_PATCH(self):
        match = re.match(r"^/api/orders/([^/]+)$", urlparse(self.path).path)
        if not match:
            self.send_error(404)
            return
        order_id = "#" + match.group(1).lstrip("#")
        payload = self.read_json()
        state = load_state()
        for order in state["orders"]:
            if order.get("id") == order_id:
                order.update({key: value for key, value in payload.items() if key in order})
                save_state(state)
                self.write_json(order)
                return
        self.send_error(404)

    def read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def write_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", 4180), SyncHandler)
    print("Sync server running at http://127.0.0.1:4180")
    server.serve_forever()
