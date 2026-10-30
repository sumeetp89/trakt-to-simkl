#!/usr/bin/env python3
"""Trakt -> Simkl transfer, all in one. Uses only the free APIs and the Python standard library.

Moves: watched movies, watched shows (real episodes with original dates),
       ratings (movies + shows) and watchlist (-> Plan to Watch).

Needs: a Trakt development app Client ID (PKCE, no secret) and a Simkl app Client ID.
Run:   python3 trakt2simkl.py              full transfer
       python3 trakt2simkl.py --dry-run    only download from Trakt and save the backup

Limits: only the latest watch date per movie/episode is sent (Trakt rewatch history is not
kept; Simkl rewatches need PRO). Custom lists, collections and comments are not moved.
Safe to re-run: items Simkl already has are left alone on a free account.
Optional: set TRAKT_CLIENT_ID and SIMKL_CLIENT_ID in the environment to skip the prompts.
"""
import base64
import hashlib
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "trakt2simkl/2.1"
APP_NAME = "trakt-to-simkl"
APP_VERSION = "2.1"
TRAKT = "https://api.trakt.tv"
SIMKL = "https://api.simkl.com"
DRY = "--dry-run" in sys.argv


# ------------------------------------------------------------------ http
def http(method, url, headers=None, body=None, retries=4):
    data = json.dumps(body).encode() if body is not None else None
    h = {"User-Agent": UA, "Content-Type": "application/json"}
    h.update(headers or {})
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read().decode() or "null"
                return r.status, json.loads(raw)
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            if e.code in (429, 502, 503, 504) and attempt < retries - 1:
                try:
                    wait = int(e.headers.get("Retry-After", 3 * (attempt + 1)))
                except ValueError:
                    wait = 3 * (attempt + 1)
                time.sleep(wait)
                continue
            try:
                return e.code, json.loads(raw)
            except Exception:
                return e.code, raw
        except (urllib.error.URLError, TimeoutError):
            if attempt < retries - 1:
                time.sleep(3 * (attempt + 1))
                continue
            return 0, None
    return 0, None


def ask(env, prompt):
    return (os.environ.get(env) or input(prompt)).strip()


# ------------------------------------------------------------------ Trakt login (PKCE)
def trakt_login():
    cid = ask("TRAKT_CLIENT_ID", "Trakt Client ID: ")
    redirect = "http://localhost:8080/callback"
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    state = secrets.token_urlsafe(16)
    q = urllib.parse.urlencode({
        "response_type": "code", "client_id": cid, "redirect_uri": redirect,
        "code_challenge": challenge, "code_challenge_method": "S256", "state": state,
    })
    print("\n1) Open this link in a browser and approve access:\n")
    print(f"https://trakt.tv/oauth/authorize?{q}\n")
    print("2) The page will then fail to load (that's expected). Copy the full address")
    print("   from the browser bar; it starts with localhost:8080/callback?code=")
    pasted = input("\nPaste that address here: ").strip()
    parsed = urllib.parse.parse_qs(urllib.parse.urlparse(pasted).query)
    code = (parsed.get("code") or [pasted])[0]
    if parsed.get("state") and parsed["state"][0] != state:
        sys.exit("State mismatch. Run again.")
    st, tok = http("POST", f"{TRAKT}/oauth/token", body={
        "code": code, "client_id": cid, "redirect_uri": redirect,
        "grant_type": "authorization_code", "code_verifier": verifier,
    })
    if st != 200 or not isinstance(tok, dict) or "access_token" not in tok:
        sys.exit(f"Trakt login failed: {st} {str(tok)[:300]}")
    print("Trakt: logged in.")
    return {"trakt-api-version": "2", "trakt-api-key": cid,
            "Authorization": f"Bearer {tok['access_token']}"}


def trakt_get(h, path, limit=100):
    """Fetch every page of a Trakt list endpoint."""
    out, first_seen = [], None
    for page in range(1, 500):
        st, d = http("GET", f"{TRAKT}{path}?page={page}&limit={limit}", headers=h)
        if st != 200:
            print(f"  warning: {path} page {page} returned {st}")
            break
        if not d or not isinstance(d, list):
            break
        first = json.dumps(d[0], sort_keys=True)
        if first == first_seen:  # endpoint ignored paging and repeated itself
            break
        if page == 1:
            first_seen = first
        out.extend(d)
        time.sleep(0.3)
    return out


# ------------------------------------------------------------------ Simkl login (OAuth 2.0 device flow)
def simkl_login():
    cid = ask("SIMKL_CLIENT_ID", "Simkl Client ID: ")
    st, dc = http("POST", f"{SIMKL}/oauth2/device",
                  body={"client_id": cid, "scope": "media:read media:write"})
    if st != 200 or not isinstance(dc, dict) or "device_code" not in dc:
        sys.exit(f"Simkl device request failed: {st} {str(dc)[:300]}")
    link = dc.get("verification_uri_complete") or dc["verification_uri"]
    print(f"\nOpen this in a browser: {link}")
    print(f"If it asks for a code, enter: {dc['user_code']}  and approve everything.\n")
    interval = dc.get("interval", 5)
    deadline = time.time() + dc.get("expires_in", 900)
    while time.time() < deadline:
        time.sleep(interval)
        st, r = http("POST", f"{SIMKL}/oauth2/token", body={
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": dc["device_code"], "client_id": cid})
        if st == 200 and isinstance(r, dict) and r.get("access_token"):
            if "media:write" not in r.get("scope", ""):
                sys.exit("Simkl did not grant write access. Run again and approve all permissions.")
            print("Simkl: logged in.")
            return {"Authorization": f"Bearer {r['access_token']}", "simkl-api-key": cid}
        err = r.get("error") if isinstance(r, dict) else None
        if err == "slow_down":
            interval += 5
        elif err == "expired_token":
            break
        elif st not in (200, 400, 0):
            sys.exit(f"Simkl login failed: {st} {str(r)[:300]}")
    sys.exit("Simkl code expired. Run again.")


# ------------------------------------------------------------------ helpers
def ids_of(obj):
    i = (obj or {}).get("ids") or {}
    return {k: i[k] for k in ("imdb", "tmdb", "tvdb") if i.get(k)}


def base(obj, ids):
    d = {"ids": ids}
    if obj.get("title"):
        d["title"] = obj["title"]
    if obj.get("year"):
        d["year"] = obj["year"]
    return d


def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def label(item):
    return f"{item.get('title') or '?'} ({item.get('year') or '?'})"


def push(sh, path, payload, name):
    """POST to Simkl. Returns the response dict, or None on failure."""
    q = urllib.parse.urlencode({"client_id": sh.get("simkl-api-key", ""),
                                "app-name": APP_NAME, "app-version": APP_VERSION})
    st, r = http("POST", f"{SIMKL}{path}?{q}", headers=sh, body=payload)
    time.sleep(1.2)  # Simkl allows 1 POST per second
    if st not in (200, 201) or not isinstance(r, dict):
        print(f"  {name}: HTTP {st} {str(r)[:200]}")
        return None
    return r


def not_found(resp, kind):
    return ((resp or {}).get("not_found") or {}).get(kind, [])


def push_with_retry(sh, path, kind, items, size, name):
    """Push items; items Simkl can't match are retried by title+year. Returns still-unmatched."""
    missed = []
    for n, part in enumerate(chunks(items, size), 1):
        r = push(sh, path, {kind: part}, f"{name} batch {n}")
        if r is None:
            missed += part  # request failed: count as unmatched so it is reported
        else:
            missed += not_found(r, kind)
    print(f"  {name}: sent {len(items)}, {len(missed)} not matched by id")
    if not missed:
        return []
    retry = []
    for m in missed:
        m2 = {k: v for k, v in m.items() if k != "ids"}
        if m2.get("title"):
            retry.append(m2)
    still = []
    for part in chunks(retry, size):
        r = push(sh, path, {kind: part}, f"{name} retry by title")
        still += not_found(r, kind) if r is not None else part
    print(f"  {name}: {len(missed) - len(still)} recovered by title, {len(still)} still unmatched")
    return still


# ------------------------------------------------------------------ main
def main():
    th = trakt_login()

    print("\nDownloading from Trakt (this can take a minute)...")
    wm = trakt_get(th, "/sync/watched/movies")
    eps = trakt_get(th, "/sync/history/episodes")
    rm = trakt_get(th, "/sync/ratings/movies")
    rs = trakt_get(th, "/sync/ratings/shows")
    lm = trakt_get(th, "/sync/watchlist/movies")
    ls = trakt_get(th, "/sync/watchlist/shows")
    with open("trakt_backup.json", "w") as f:
        json.dump(dict(watched_movies=wm, episode_history=eps, rated_movies=rm, rated_shows=rs,
                       watchlist_movies=lm, watchlist_shows=ls), f)

    # Group episode plays by show -> unique episodes (latest watch date wins)
    grouped = {}
    for it in eps:
        show, ep = it.get("show") or {}, it.get("episode") or {}
        ids = ids_of(show)
        if not ids or ep.get("season") is None or ep.get("number") is None:
            continue
        g = grouped.setdefault(tuple(sorted(ids.items())), {"show": show, "ids": ids, "eps": {}})
        k = (ep["season"], ep["number"])
        when = it.get("watched_at") or ""
        if k not in g["eps"] or when > g["eps"][k]:
            g["eps"][k] = when
    n_eps = sum(len(g["eps"]) for g in grouped.values())

    print(f"  movies watched {len(wm)}, shows watched {len(grouped)} ({n_eps} unique episodes)")
    print(f"  ratings {len(rm)} movies / {len(rs)} shows, watchlist {len(lm)} movies / {len(ls)} shows")
    print("  saved trakt_backup.json (your full backup)")
    if DRY:
        print("\nDry run: nothing was sent to Simkl.")
        return

    sh = simkl_login()
    unmatched = []

    # ---- movies
    print("\nWatched movies...")
    movies = []
    for it in wm:
        m = it["movie"]
        ids = ids_of(m)
        d = base(m, ids) if ids else {"title": m.get("title"), "year": m.get("year")}
        d["watched_at"] = it.get("last_watched_at")
        movies.append(d)
    unmatched += [("movie", label(m)) for m in
                  push_with_retry(sh, "/sync/history", "movies", movies, 200, "movies")]

    # ---- shows (real episodes only)
    print("\nWatched shows...")
    shows = []
    for g in grouped.values():
        d = base(g["show"], g["ids"])
        d["use_tvdb_anime_seasons"] = True  # Trakt numbers anime per TVDB season
        by_season = {}
        for (sn, en), when in sorted(g["eps"].items()):
            by_season.setdefault(sn, []).append({"number": en, "watched_at": when or None})
        d["seasons"] = [{"number": sn, "episodes": e} for sn, e in sorted(by_season.items())]
        shows.append(d)
    unmatched += [("show", label(s)) for s in
                  push_with_retry(sh, "/sync/history", "shows", shows, 10, "shows")]

    # ---- ratings
    print("\nRatings...")

    def rated(items, key):
        out = []
        for it in items:
            ids = ids_of(it[key])
            if ids:
                d = base(it[key], ids)
                d["rating"] = it["rating"]
                d["rated_at"] = it.get("rated_at")
                out.append(d)
        return out

    unmatched += [("rated movie", label(m)) for m in
                  push_with_retry(sh, "/sync/ratings", "movies", rated(rm, "movie"), 200, "movie ratings")]
    unmatched += [("rated show", label(s)) for s in
                  push_with_retry(sh, "/sync/ratings", "shows", rated(rs, "show"), 200, "show ratings")]

    # ---- watchlist -> Plan to Watch
    print("\nWatchlist...")

    def wl(items, key):
        out = []
        for it in items:
            ids = ids_of(it[key])
            if ids:
                d = base(it[key], ids)
                d["to"] = "plantowatch"
                out.append(d)
        return out

    unmatched += [("watchlist movie", label(m)) for m in
                  push_with_retry(sh, "/sync/add-to-list", "movies", wl(lm, "movie"), 200, "watchlist movies")]
    unmatched += [("watchlist show", label(s)) for s in
                  push_with_retry(sh, "/sync/add-to-list", "shows", wl(ls, "show"), 200, "watchlist shows")]

    # ---- summary
    print("\n" + "=" * 50)
    print(f"Sent: {len(wm)} movies, {len(grouped)} shows / {n_eps} episodes, "
          f"{len(rm) + len(rs)} ratings, {len(lm) + len(ls)} watchlist items.")
    if unmatched:
        print(f"\nSimkl could not match {len(unmatched)} item(s). Add these by hand on simkl.com:")
        for kind, name in unmatched:
            print(f"  - [{kind}] {name}")
    else:
        print("Everything matched.")
    print("\nCheck your Simkl profile in a few minutes. Anime movies are counted under Anime,")
    print("so the Movies number can be a little lower than Trakt's.")


if __name__ == "__main__":
    main()
