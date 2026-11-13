import io
import re
import pandas as pd
from pypdf import PdfReader
import streamlit as st


class UHISEngine:
    def calculate(self, metrics):
        if not metrics:
            return 0.0
        return round(sum(metrics.values()) / len(metrics), 2)


class ProbabilityEngine:
    def calculate(self, uhis, total_uhis):
        if total_uhis <= 0:
            return 0.0
        return round((uhis / total_uhis) * 100, 2)


class FairOddsEngine:
    def calculate(self, prob):
        if prob <= 0:
            return 0.0
        return round(100 / prob, 2)


class OverlayEngine:
    def calculate(self, fair, market):
        if fair <= 0:
            return 0.0
        return round(((market - fair) / fair) * 100, 2)


class EESEngine:
    def calculate(self, uhis, conf, opp):
        return round((uhis * 0.50) + (opp * 0.30) + (conf * 0.20), 2)


class RecommendationEngine:
    def generate(self, ees, overlay):
        if ees >= 92:
            return "BEST_BET"
        if overlay >= 25:
            return "VALUE_BET"
        if ees >= 85:
            return "PLACE_BET"
        return "WATCH"


class GoldCircleParser:
    RACE_RE = re.compile(r"(?i)\bRACE\s+(\d+)\b[^\n]*?(\d{3,4})\s*M\b")
    RUNNER_RE = re.compile(
        r"^\s*(?P<num>\d{1,2})\s+(?:\((?P<d1>\d{1,2})\)\s+)?"
        r"(?P<horse>[A-Z][A-Z\s\'\-\.]{2,28}?)\s+(?:\((?P<d2>\d{1,2})\)\s+)?"
        r"(?P<wt>\d{2}\.\d)\s+(?P<jockey>[A-Za-z\.\s\'\-]{3,22}?)\s{2,}"
        r"(?P<trainer>[A-Za-z\.\s\'\-]{3,22}?)(?:\s+(?P<odds>\d+(?:/\d+|\.\d+)?))?\s*$",
        re.MULTILINE,
    )
    SIMPLE_RE = re.compile(
        r"^\s*(?P<num>\d{1,2})\s+\(?(?P<draw>\d{1,2})\)?\s+"
        r"(?P<horse>[A-Z][A-Z\s\'\-]{2,25})\s+(?P<wt>\d{2}\.\d)",
        re.MULTILINE,
    )

    @staticmethod
    def to_decimal(odds_str):
        if not odds_str:
            return 6.00
        s = odds_str.strip()
        try:
            if "/" in s:
                n, d = s.split("/")
                return round((float(n) / float(d)) + 1.0, 2)
            val = float(s)
            return round(val if val > 1.0 else val + 1.0, 2)
        except ValueError:
            return 6.00

    def parse(self, text):
        races = {}
        headers = list(self.RACE_RE.finditer(text))
        if not headers:
            return {}
        for i, match in enumerate(headers):
            r_num = match.group(1)
            dist = int(match.group(2))
            title = f"Race {r_num} - {dist}m"
            start = match.end()
            end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
            runners = self.extract_runners(text[start:end], dist)
            if runners:
                races[title] = runners
        return races

    def extract_runners(self, block, dist):
        runners = []
        seen = set()
        for m in self.RUNNER_RE.finditer(block):
            horse = m.group("horse").strip().title()
            if horse in seen or len(horse) < 3:
                continue
            seen.add(horse)
            draw = int(m.group("d1") or m.group("d2") or 5)
            wt = float(m.group("wt"))
            jockey = m.group("jockey").strip()
            trainer = m.group("trainer").strip()
            odds = self.to_decimal(m.group("odds"))
            runners.append(self.score_runner(horse, draw, wt, jockey, trainer, odds, dist))

        if runners:
            return runners

        for m in self.SIMPLE_RE.finditer(block):
            horse = m.group("horse").strip().title()
            if horse in seen or len(horse) < 3:
                continue
            seen.add(horse)
            draw = int(m.group("draw"))
            wt = float(m.group("wt"))
            runners.append(self.score_runner(horse, draw, wt, "Extracted", "Extracted", 5.00, dist))
        return runners

    def score_runner(self, horse, draw, wt, jockey, trainer, odds, dist):
        mkt = max(60.0, min(96.0, 100.0 - (odds * 2.2)))
        pen = (draw - 1) * (2.0 if dist <= 1400 else 1.2)
        drw = max(62.0, min(95.0, 92.0 - pen))
        wgt = max(65.0, min(94.0, 85.0 + ((wt - 57.0) * 1.5)))
        metrics = {
            "form": round((mkt * 0.6) + (wgt * 0.4), 1),
            "speed": round((mkt * 0.5) + (wgt * 0.5), 1),
            "trainer": 82.0,
            "jockey": 83.0,
            "distance": 84.0,
            "track": 83.0,
            "going": 82.0,
            "draw": round(drw, 1),
            "market": round(mkt, 1),
            "pace": round((drw + mkt) / 2, 1),
        }
        uhis = UHISEngine().calculate(metrics)
        conf = round((mkt + wgt) / 2, 1)
        opp = round((drw + mkt) / 2, 1)
        return {
            "horse": horse, "jockey": jockey, "trainer": trainer,
            "draw": draw, "weight": wt, "market_odds": odds,
            "uhis": uhis, "conf": conf, "opp": opp,
        }


def detect_provider(text):
    up = text.upper()
    sa = ["GOLD CIRCLE", "GREYVILLE", "SCOTTSVILLE", "KENILWORTH", "TURFFONTEIN", "VAAL"]
    if any(t in up for t in sa):
        return "GOLDCIRCLE / SA RACING"
    if "HONG KONG JOCKEY CLUB" in up:
        return "HKJC"
    return "GENERIC / UNKNOWN"


def fallback_races():
    return {
        "Sample Race 1 - 1200m (Demo Fallback)": [
            {"horse": "Cape Crusader", "jockey": "R. Fourie", "trainer": "J. Snaith", "draw": 2, "weight": 60.0, "market_odds": 2.80, "uhis": 91.20, "conf": 94, "opp": 92},
            {"horse": "Highveld Star", "jockey": "G. Lerena", "trainer": "M. de Kock", "draw": 5, "weight": 58.5, "market_odds": 5.50, "uhis": 85.40, "conf": 85, "opp": 89},
            {"horse": "Durban Dash", "jockey": "K. de Melo", "trainer": "D. Kannemeyer", "draw": 7, "weight": 57.0, "market_odds": 4.00, "uhis": 83.00, "conf": 84, "opp": 81},
            {"horse": "Karoo Breeze", "jockey": "C. Zackey", "trainer": "A. Fortune", "draw": 10, "weight": 54.5, "market_odds": 15.00, "uhis": 74.50, "conf": 72, "opp": 76},
        ]
    }


def analyze_meeting(text):
    parsed = GoldCircleParser().parse(text)
    used_fallback = False
    if not parsed:
        parsed = fallback_races()
        used_fallback = True

    results = {}
    for race_name, runners in parsed.items():
        total_uhis = sum(r["uhis"] for r in runners)
        rows = []
        for r in runners:
            prob = ProbabilityEngine().calculate(r["uhis"], total_uhis)
            fair = FairOddsEngine().calculate(prob)
            over = OverlayEngine().calculate(fair, r["market_odds"])
            ees = EESEngine().calculate(r["uhis"], r["conf"], r["opp"])
            sig = RecommendationEngine().generate(ees, over)
            rows.append({
                "Horse": r["horse"], "Draw": r["draw"], "Weight": r.get("weight", 58.0),
                "Jockey": r["jockey"], "Trainer": r["trainer"], "UHIS": r["uhis"],
                "EES": ees, "Win Prob (%)": prob, "Fair Odds": fair,
                "Market Odds": r["market_odds"], "Overlay (%)": over, "Signal": sig,
            })
        df = pd.DataFrame(rows).sort_values(by="EES", ascending=False).reset_index(drop=True)
        df.index = df.index + 1
        results[race_name] = df
    return results, used_fallback


def render_top_card(col, medal, row):
    box = col.container(border=True)
    box.markdown(f"### {medal}")
    box.markdown(f"#### **{row['Horse']}** (Draw {row['Draw']})")
    box.caption(f"Wt: {row['Weight']}kg | J: {row['Jockey']} | T: {row['Trainer']}")
    m1, m2 = box.columns(2)
    m1.metric("EES", row["EES"])
    m2.metric("Win Prob", f"{row['Win Prob (%)']}%")
    m3, m4 = box.columns(2)
    m3.metric("Mkt / Fair", f"{row['Market Odds']} / {row['Fair Odds']}")
    m4.metric("Overlay", f"{row['Overlay (%)']}%")
    box.info(f"**Signal:** {row['Signal']}")


def render_upload_tab(tab):
    uploaded = tab.file_uploader("Upload Racecard PDF", type=["pdf"])
    if uploaded is None:
        tab.info("Upload a PDF racecard above to generate your Top 3 selections.")
        return

    reader = PdfReader(io.BytesIO(uploaded.read()))
    raw_text = "\n".join([p.extract_text() or "" for p in reader.pages])
    provider = detect_provider(raw_text)

    c1, c2 = tab.columns(2)
    c1.info(f"**File:** {uploaded.name} ({len(reader.pages)} pages)")
    c2.success(f"**Provider:** {provider}")

    races, fallback = analyze_meeting(raw_text)
    if fallback:
        tab.warning("Could not match standard Gold Circle lines. Showing sample data.")
    else:
        tab.success(f"Parsed {len(races)} races from PDF!")

    selected = tab.selectbox("Select Race:", list(races.keys()))
    df = races[selected]

    tab.subheader(f"🏆 Top 3 Selections — {selected}")
    medals = ["🥇 1st Pick", "🥈 2nd Pick", "🥉 3rd Pick"]
    cols = tab.columns(3)
    for idx, (_, row) in enumerate(df.head(3).iterrows()):
        render_top_card(cols[idx], medals[idx], row)

    tab.subheader("📊 Full Race Analysis")
    tab.dataframe(df, use_container_width=True)

    exp = tab.expander("🔍 View Raw PDF Text")
    exp.text_area("Extracted Text", raw_text[:4000], height=250)


def render_sim_tab(tab):
    tab.subheader("Test Individual Runner Metrics")
    c1, c2, c3 = tab.columns(3)
    h_name = c1.text_input("Horse Name", value="Thunder Strike")
    form = c1.slider("Form", 0, 100, 91)
    speed = c1.slider("Speed", 0, 100, 89)
    trainer = c1.slider("Trainer", 0, 100, 84)

    jockey = c2.slider("Jockey", 0, 100, 81)
    dist = c2.slider("Distance", 0, 100, 90)
    track = c2.slider("Track", 0, 100, 88)
    going = c2.slider("Going", 0, 100, 80)

    draw = c3.slider("Draw", 0, 100, 76)
    market = c3.slider("Market", 0, 100, 83)
    pace = c3.slider("Pace", 0, 100, 87)

    r1, r2, r3, r4 = tab.columns(4)
    tot_uhis = r1.number_input("Total Race UHIS", value=320.0, step=10.0)
    mkt_odds = r2.number_input("Market Odds", value=4.50, step=0.10)
    conf = r3.slider("Confidence", 0, 100, 91)
    opp = r4.slider("Opportunity", 0, 100, 87) 
