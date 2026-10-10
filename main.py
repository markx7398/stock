# main.py — 安卓股票行情App
import os
import threading

import requests
from kivy.app import App
from kivy.clock import Clock
from kivy.core.text import LabelBase
from kivy.graphics import Color, Line, Rectangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

# 中文字体
for _fp in ("/system/fonts/NotoSansCJK-Regular.ttc",
            "/system/fonts/DroidSansFallback.ttf",
            "/system/fonts/NotoSansSC-Regular.otf"):
    if os.path.exists(_fp):
        LabelBase.register(name="Roboto", fn_regular=_fp)
        break

UP = (0.937, 0.325, 0.314, 1)
DOWN = (0.149, 0.651, 0.604, 1)
BG = (0.118, 0.118, 0.118, 1)


def to_sec(code: str) -> str:
    code = code.strip().lower()
    if code[:2] in ("sh", "sz", "bj"):
        return code
    if code[0] in "69":
        return "sh" + code
    if code[0] == "8" or code.startswith("43"):
        return "bj" + code
    return "sz" + code


def fetch_quote(sec: str) -> dict:
    r = requests.get(f"https://qt.gtimg.cn/q={sec}", timeout=10)
    r.encoding = "gbk"
    p = r.text.split("~")
    return {
        "name": p[1], "code": p[2],
        "price": float(p[3]), "high": float(p[33]), "low": float(p[34]),
        "chg": float(p[31]), "pct": float(p[32]), "turnover": float(p[38]),
    }


def fetch_kline(sec: str, count: int = 250) -> list:
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    r = requests.get(url, params={"param": f"{sec},day,,,{count},qfq"},
                     timeout=12, headers={"User-Agent": "Mozilla/5.0"})
    node = r.json()["data"][sec]
    rows = node.get("qfqday") or node.get("day") or []
    return [{"date": x[0], "open": float(x[1]), "close": float(x[2]),
             "high": float(x[3]), "low": float(x[4]), "vol": float(x[5])}
            for x in rows]


class KlineWidget(Widget):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.rows = []
        self.bind(pos=self.redraw, size=self.redraw)

    def set_data(self, rows):
        self.rows = rows
        self.redraw()

    def redraw(self, *args):
        self.canvas.clear()
        rows = self.rows
        W, H = self.width, self.height
        if not rows or W <= 0 or H <= 0:
            return

        pad_l, pad_r, pad_t, pad_b = dp(8), dp(52), dp(10), dp(26)
        inner_w = W - pad_l - pad_r
        chart_h = H - pad_t - pad_b
        price_h = chart_h * 0.72
        vol_h = chart_h * 0.22
        vol_top = pad_t + price_h + dp(8)

        n = len(rows)
        cw = inner_w / n
        bw = max(1.5, cw * 0.65)

        hi = max(r["high"] for r in rows)
        lo = min(r["low"] for r in rows)
        max_vol = max(r["vol"] for r in rows) or 1
        rng = (hi - lo) or 1

        def yp(p):
            return pad_t + (p - lo) / rng * price_h

        with self.canvas:
            # 网格
            Color(0.5, 0.5, 0.5, 0.15)
            for i in range(1, 4):
                y = pad_t + price_h * i / 4
                Line(points=[pad_l, y, W - pad_r, y], width=0.8)

            # K线 + 成交量
            for i, r in enumerate(rows):
                x = pad_l + i * cw + cw / 2
                up = r["close"] >= r["open"]
                Color(*(UP if up else DOWN))
                Line(points=[x, yp(r["low"]), x, yp(r["high"])], width=1)
                yo, yc = yp(r["open"]), yp(r["close"])
                Rectangle(pos=(x - bw / 2, min(yo, yc)),
                          size=(bw, max(1, abs(yc - yo))))
                vh = (r["vol"] / max_vol) * vol_h
                Rectangle(pos=(x - bw / 2, vol_top), size=(bw, vh))

            # 均线
            for period, col in [(5, (0.96, 0.65, 0.14, 1)),
                                (20, (0.29, 0.56, 0.85, 1)),
                                (60, (0.61, 0.35, 0.71, 1))]:
                if n < period:
                    continue
                Color(*col)
                pts = []
                for i in range(period - 1, n):
                    s = sum(rows[j]["close"] for j in range(i - period + 1, i + 1))
                    pts.extend([pad_l + i * cw + cw / 2, yp(s / period)])
                if len(pts) >= 4:
                    Line(points=pts, width=1.1)


class StockApp(App):
    def build(self):
        root = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(8))
        with root.canvas.before:
            Color(*BG)
            self._bg = Rectangle(pos=root.pos, size=root.size)
        root.bind(pos=self._sync, size=self._sync)

        bar = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        self.code = TextInput(text="600000", multiline=False, size_hint_x=0.6,
                              input_type="number", font_size=sp(18))
        btn = Button(text="查询", size_hint_x=0.4, font_size=sp(16))
        btn.bind(on_release=self.on_query)
        bar.add_widget(self.code)
        bar.add_widget(btn)
        root.add_widget(bar)

        self.info = Label(text="输入代码后点查询", size_hint_y=None,
                          height=dp(28), font_size=sp(13), color=(0.85, 0.85, 0.85, 1))
        root.add_widget(self.info)

        self.chart = KlineWidget()
        root.add_widget(self.chart)

        Clock.schedule_once(lambda *_: self.on_query(), 0.5)
        return root

    def _sync(self, inst, _):
        self._bg.pos, self._bg.size = inst.pos, inst.size

    def on_query(self, *_):
        code = self.code.text.strip()
        if not code:
            return
        self.info.text = "加载中…"
        threading.Thread(target=self._load, args=(code,), daemon=True).start()

    def _load(self, code):
        try:
            sec = to_sec(code)
            q = fetch_quote(sec)
            rows = fetch_kline(sec)
            Clock.schedule_once(lambda *_: self._show(q, rows), 0)
        except Exception as e:
            Clock.schedule_once(lambda *_: setattr(self.info, "text", f"失败:{e}"), 0)

    def _show(self, q, rows):
        sign = "+" if q["chg"] >= 0 else ""
        self.info.text = (f"{q['name']} {q['code']}  {q['price']:.2f}  "
                          f"{sign}{q['pct']:.2f}%  高{q['high']:.2f} 低{q['low']:.2f}")
        self.chart.set_data(rows)


if __name__ == "__main__":
    StockApp().run()