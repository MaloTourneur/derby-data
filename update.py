"""Builds derby.json (format v2, read by both Derby counter devices) from football-data.org.

Run by GitHub Actions every 6 h. Needs the env var FOOTBALL_DATA_TOKEN (free key).
Standard library only. Writes derby.json only if the data changed.
"""
import json, os, sys, urllib.request
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


def is_derby(m):
    return {m["homeTeam"]["id"], m["awayTeam"]["id"]} == {LENS, LILLE}


def local(m):
    return datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00")).astimezone(PARIS)


def main():
    matches = [m for m in get(f"/teams/{LENS}/matches?limit=100")["matches"] if is_derby(m)]
    upcoming = sorted((m for m in matches if m["status"] in ("SCHEDULED", "TIMED", "POSTPONED")), key=lambda m: m["utcDate"])
    played = sorted((m for m in matches if m["status"] == "FINISHED"), key=lambda m: m["utcDate"])
    anchor = (upcoming or played[::-1] or [None])[0]
    if anchor is None:
        sys.exit("no Lens-Lille match found this season")

    # Last 5 meetings, all seasons (head2head looks back further than this season).
    h2h = get(f"/matches/{anchor['id']}/head2head?limit=10")["matches"]
    finished = {m["id"]: m for m in h2h + played if m["status"] == "FINISHED" and is_derby(m)}
    last = sorted(finished.values(), key=lambda m: m["utcDate"], reverse=True)[:5]
    if not last:
        sys.exit("no finished derby found")

    data = {
        "v": 2,
        "last": [{
            "date": local(m).strftime("%Y-%m-%d"),
            "home": NAMES[m["homeTeam"]["id"]],
            "hg": m["score"]["fullTime"]["home"],
            "ag": m["score"]["fullTime"]["away"],
            "away": NAMES[m["awayTeam"]["id"]],
        } for m in last],
        "next": None,
    }
    if upcoming and upcoming[0]["status"] != "POSTPONED":
        n = upcoming[0]
        t = local(n)
        data["next"] = {
            "date": t.strftime("%Y-%m-%d"),
            # SCHEDULED = kickoff time not fixed yet
            "time": t.strftime("%Hh%M") if n["status"] == "TIMED" else "",
            "home": NAMES[n["homeTeam"]["id"]],
            "away": NAMES[n["awayTeam"]["id"]],
            "stadium": STADIUMS[n["homeTeam"]["id"]],
        }

    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    old = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""
    if text != old:
        open(OUT, "w", encoding="utf-8", newline="\n").write(text)
        print("derby.json updated")
    else:
        print("no change")
    print(text)


if __name__ == "__main__":
    main()
