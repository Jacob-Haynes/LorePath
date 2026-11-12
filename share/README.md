# Share page

A small web page where players paste the codes `/lp share` gives them, with no GitHub account needed. It's live at https://lorepath-share.jacobhaynes49.workers.dev, on the maintainer's Cloudflare account. It's a Cloudflare Worker (`worker.js`) that serves the page and, for each code, opens a **Share quest text** issue labelled `quest-text`. From there the `Add shared quest text` workflow handles it exactly as it handles the issue form.

The worker:
- checks each code before passing it on: a version 1 code, numeric quest IDs, only known fields, sane lengths, at most 10 codes at a time;
- re-encodes each code from the parsed JSON, so only quest data reaches the issue;
- asks for a Cloudflare Turnstile check, so bots can't flood the repo with issues;
- stores nothing.

Issues it opens are authored by the account that owns the token.

## Cost

Free. The Workers free plan allows 100,000 requests a day and 10 ms of CPU time per request; waiting on GitHub doesn't count, and checking a code takes far less. Turnstile and the GitHub API are free too.

## Setting it up (once)

You need a free Cloudflare account and Node.js (for `wrangler`, Cloudflare's CLI).

1. **Turnstile widget:** in the Cloudflare dashboard, go to **Turnstile → Add widget**, name it `LorePath share`, and add the hostname `lorepath-share.<your-subdomain>.workers.dev`. Use mode **Managed**. Note the **site key** and **secret key**.
2. **GitHub token:** create a fine-grained personal access token under **GitHub → Settings → Developer settings → Fine-grained tokens**. Give it **Repository access: only Jacob-Haynes/LorePath** and **Permissions: Issues → Read and write**, nothing else. Set an expiry and note when it ends.
3. **Deploy**, from this folder:

   ```bash
   npx wrangler login
   npx wrangler secret put GITHUB_TOKEN
   npx wrangler secret put TURNSTILE_SECRET
   ```

   Put the Turnstile **site key** in `wrangler.toml` (`TURNSTILE_SITE_KEY`), then:

   ```bash
   npx wrangler deploy
   ```

   Wrangler prints the page's address.
4. **Point LorePath at it:** set `ns.SHARE_PAGE_URL` in `Share.lua` to that address, without `https://`, and mention it in `README.md` and `media/curseforge-description.md`.

If `wrangler login` opens the wrong browser (or one signed in to another Cloudflare account), run `npx wrangler login --browser=false` and open the link it prints in the right one. `npx wrangler whoami` shows which account you're on, and `npx wrangler secret list` shows which secrets are set (names only).

Until all the settings are in, the page tells players to use a GitHub issue instead.

When the token expires (GitHub emails a reminder beforehand), the page can't open issues until you make a new one and run `npx wrangler secret put GITHUB_TOKEN` again.

## Tests

`test_worker.js` checks the code handling. `python3 tools/test/run_tests.py` runs it with `node`, or with macOS's built-in `jsc` where Node isn't installed.
