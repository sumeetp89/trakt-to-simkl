# Trakt to Simkl transfer

Move your Trakt history to Simkl for free. Simkl's built-in Trakt importer is sometimes limited to paid supporters, but both services have free developer APIs, and this single script uses them.

It transfers:

- watched movies
- watched shows, as real episodes with their original watch dates
- ratings (movies and shows)
- your watchlist (it becomes Plan to Watch on Simkl)

It does not transfer custom lists, collections, comments or playback progress. Nothing on Trakt is changed or deleted, and a full backup is saved as `trakt_backup.json` before anything is sent to Simkl.

This is an independent tool and is not affiliated with Trakt or Simkl.

## What you need

- A Trakt account and a Simkl account (free plans work)
- A free GitHub account (Trakt's developer portal asks you to link one)
- Python 3 and a terminal on Windows, Mac or Linux
- A web browser on any device to approve the logins
- About 20 minutes

The script uses only Python's built-in libraries, so there is nothing to install.

## Step 1: Create a free Trakt app

1. Go to [developer.trakt.tv](https://developer.trakt.tv), sign in and open **My Apps**.
2. Tap **Connect GitHub** and approve. Trakt only reads your public GitHub username.
3. Create a new app named `simkl-transfer` with the **Development** app type.
4. Under **Redirect URIs**, enter exactly `http://localhost:8080/callback`.
5. Save the app and copy its **Client ID**.

The app page shows "Client Secret: Not issued". That is expected, because the script signs in with PKCE and needs only the Client ID.

## Step 2: Create a free Simkl app

1. Go to [simkl.com/settings/developer](https://simkl.com/settings/developer) and choose **Add**.
2. Pick the app type **Mobile, desktop & browser apps** (AUTH V2, Client ID only).
3. Name it `trakt-transfer`. If you put "Simkl" in the name, Simkl requires the form "Your App for Simkl".
4. Leave **Homepage URL** and **Description** empty.
5. Under **Sign-in settings**, set **Redirect URLs** to exactly `urn:ietf:wg:oauth:2.0:oob`.
6. Tap **Review app**, confirm, and copy the **Client ID**.

## Step 3: Run a dry run

Download `trakt2simkl.py`, open a terminal in the same folder and check Python is installed:

```
python3 --version
```

On Windows, use `py` in place of `python3` in every command. Then run the dry run, which only reads from Trakt and sends nothing to Simkl:

```
python3 trakt2simkl.py --dry-run
```

1. Paste your Trakt Client ID.
2. Open the `trakt.tv/oauth/authorize` link it prints in any browser and approve access.
3. The page then fails to load. That is expected. Copy the full address from the browser's address bar (it starts with `localhost:8080/callback?code=`) and paste it into the terminal.

It prints what it found and saves `trakt_backup.json`. Compare the counts with your Trakt profile stats.

## Step 4: Run the transfer

```
python3 trakt2simkl.py
```

1. Sign in to Trakt as in Step 3.
2. Paste your Simkl Client ID.
3. Open the `simkl.com/pin` link it prints and approve **all** permissions. Write access is required.
4. Wait while it sends movies, shows, ratings and the watchlist.

At the end it prints a summary and lists any titles Simkl could not match, so you can add them by hand. Titles Simkl cannot match by ID are retried by title and year first. It is safe to run again, because on a free Simkl account titles Simkl already has are left unchanged.

## Step 5: Check the result

Give Simkl a few minutes, then compare your profile with the summary:

- Episodes watched should equal the unique episode count the script printed.
- TV shows plus anime should roughly equal your Trakt show count, because Simkl files anime in its own category.
- Movies can be a little lower than on Trakt, because Simkl counts anime movies under Anime.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Trakt says development apps can only redirect to localhost | Use `http://localhost:8080/callback` for Trakt. The `urn:` address belongs only to the Simkl app. |
| `Trakt login failed` or `State mismatch` | You pasted an address from an earlier run. Each run makes a new link, so use the current one. |
| `Simkl did not grant write access` | Run again and approve every permission on the Simkl page. |
| `HTTP 429` or `HTTP 5xx` lines | The service is busy. The script retries by itself. If batches still fail, wait ten minutes and run again. |
| `python3: command not found` | Install Python 3. On Windows use `py` instead. |
| `No such file or directory` for the script | Your terminal is in a different folder. Use `cd` to the folder with `trakt2simkl.py`. |

## Privacy

The script talks only to `api.trakt.tv`, `trakt.tv` and `api.simkl.com`. It stores no credentials. Your access tokens live in memory for the length of the run. Do not share `trakt_backup.json`, because it contains your full watch history.
