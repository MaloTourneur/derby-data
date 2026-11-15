"""Builds derby.json (format v2, read by both Derby counter devices) from football-data.org.

Run by GitHub Actions every 6 h. Needs the env var FOOTBALL_DATA_TOKEN (free key).
Standard library only. Writes derby.json only if the data changed.

Contents: last 5 derbies + next derby, and per club (Lens, Lille) the next Ligue 1
match and the last 5 league results, plus the Ligue 1 table.
"""
import json, os, re, sys, urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

LENS, LILLE = 546, 521  # football-data.org team ids
NAMES = {LENS: "Lens", LILLE: "Lille"}
STADIUMS = {LENS: "Stade Bollaert-Delelis", LILLE: "Stade Pierre-Mauroy"}
PARIS = ZoneInfo("Europe/Paris")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "derby.json")


def get(path):
    req = urllib.request.Request("https://api.football-data.org/v4" + path,
                                 headers={"X-Auth-Token": os.environ["FOOTBALL_DATA_TOKEN"]})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def name(team):
    """Short display name that fits the screen: "Lens", "Marseille", "PSG"..."""
    if team["id"] in NAMES:
        return NAMES[team["id"]]
    n = team.get("shortName") or team["name"]
    n = re.sub(r"^(Olympique( de)?|Stade|AS|OGC|RC|FC|AJ|SCO|SM|ESTAC|Racing Club de|Havre AC)\s+", "", n)
    n = re.sub(r"\s+(FC|AC|HAC|SCO|Foot|Olympique)$", "", n)
    return {"Paris Saint-Germain": "PSG", "Paris": "Paris FC", "Rennais": "Rennes", "Brestois 29": "Brest", "Brestois": "Brest"}.get(n, n)[:15]


def is_derby(m):
    return {m["homeTeam"]["id"], m["awayTeam"]["id"]} == {LENS, LILLE}


def local(m):
    return datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00")).astimezone(PARIS)


def when(m):
    """date + kickoff time ("" while the time isn't fixed)."""
    t = local(m)
    return t.strftime("%Y-%m-%d"), t.strftime("%Hh%M") if m["status"] == "TIMED" else ""


def upcoming(matches):
    return sorted((m for m in matches if m["status"] in ("SCHEDULED", "TIMED")), key=lambda m: m["utcDate"])


def finished(matches):
    return sorted((m for m in matches if m["status"] == "FINISHED"), key=lambda m: m["utcDate"])


def derby(lens_matches):
    matches = [m for m in lens_matches if is_derby(m)]
    nxt, played = upcoming(matches), finished(matches)
    anchor = (nxt or played[::-1] or [None])[0]
    if anchor is None:
        sys.exit("no Lens-Lille match found this season")
    # Last 5 meetings, all seasons (head2head looks back further than this season).
    h2h = get(f"/matches/{anchor['id']}/head2head?limit=10")["matches"]
    done = {m["id"]: m for m in h2h + played if m["status"] == "FINISHED" and is_derby(m)}
    last = sorted(done.values(), key=lambda m: m["utcDate"], reverse=True)[:5]
    if not last:
        sys.exit("no finished derby found")
    out = {
        "last": [{
            "date": when(m)[0],
            "home": NAMES[m["homeTeam"]["id"]],
            "hg": m["score"]["fullTime"]["home"],
            "ag": m["score"]["fullTime"]["away"],
            "away": NAMES[m["awayTeam"]["id"]],
        } for m in last],
        "next": None,
    }
    if nxt:
        n = nxt[0]
        date, time = when(n)
        out["next"] = {"date": date, "time": time, "home": NAMES[n["homeTeam"]["id"]],
                       "away": NAMES[n["awayTeam"]["id"]], "stadium": STADIUMS[n["homeTeam"]["id"]]}
    return out


def club(team_id, matches):
    """Next Ligue 1 or Champions League match + last 5 league results (V/N/D, oldest first)."""
    league = [m for m in matches if m["competition"]["code"] == "FL1"]
    form = ""
    for m in finished(league)[-5:]:
        hg, ag = m["score"]["fullTime"]["home"], m["score"]["fullTime"]["away"]
        mine, theirs = (hg, ag) if m["homeTeam"]["id"] == team_id else (ag, hg)
        form += "V" if mine > theirs else "N" if mine == theirs else "D"
    nxt = upcoming([m for m in matches if m["competition"]["code"] in ("FL1", "CL")])
    out = {"form": form, "next": None}
    if nxt:
        n = nxt[0]
        date, time = when(n)
        out["next"] = {"date": date, "time": time, "home": name(n["homeTeam"]),
                       "away": name(n["awayTeam"]), "matchday": n.get("matchday") or 0,
                       "competition": "LDC" if n["competition"]["code"] == "CL" else "L1"}
    return out


def table():
    s = get("/competitions/FL1/standings")
    total = next(t for t in s["standings"] if t["type"] == "TOTAL")["table"]
    return {
        "matchday": max((r["playedGames"] for r in total), default=0),  # journées played
        "rows": [{"team": name(r["team"]), "played": r["playedGames"], "pts": r["points"],
                  "diff": r["goalDifference"]} for r in total],
    }


def main():
    lens = get(f"/teams/{LENS}/matches?limit=100")["matches"]
    lille = get(f"/teams/{LILLE}/matches?limit=100")["matches"]
    data = {"v": 2, **derby(lens),
            "clubs": {"Lens": club(LENS, lens), "Lille": club(LILLE, lille)},
            "table": table()}

    text = json.dumps(data, ensure_ascii=False, indent=1) + "\n"
    old = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""
    if text != old:
        open(OUT, "w", encoding="utf-8", newline="\n").write(text)
        print("derby.json updated")
    else:
        print("no change")
    print(text)


if __name__ == "__main__":
    main()
