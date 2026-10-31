# iPhone enrollment

Army Hub is tailnet-only. Perform these steps on each iPhone.

## 1. Connect Tailscale

1. Open Tailscale and sign in to Mo's tailnet.
2. Connect Tailscale.
3. Do not enable an exit node merely to reach Army Hub; ordinary tailnet access is sufficient.
4. If Sing-box and Tailscale conflict, resolve that first rather than exposing Matrix publicly.

## 2. Install Element and sign in

1. Install **Element** from the App Store.
2. Choose the option to use a custom/self-hosted homeserver.
3. Enter:

   ```text
   https://moatazs-mac-mini.tailef80eb.ts.net:8444/
   ```

4. Sign in as `@mo:army.local` using the temporary password stored locally on the mini at:

   ```text
   /Users/immortalist/Documents/Kimi/Workspaces/MacServer/army-hub/.runtime/credentials.json
   ```

5. Do not copy any agent access token onto a phone.
6. Change Mo's temporary password after successful enrollment and record it in the normal password manager. Existing sessions remain usable; the runtime file is only initial provisioning material.

## 3. Verify

Open `Army Lab`, `Army Hub`, and `Approvals`, then verify:

- A plain message without an agent mention receives no agent reply.
- `@hermes-mini` receives a Hermes Mini response in a thread.
- `@dsh-mini` receives a DSH Mini response in a thread.
- An image and a small file can be sent.
- A GitHub PR link opens correctly.
- Repeat over cellular with Wi-Fi off.

Hosted Element Web is also available at `https://moatazs-mac-mini.tailef80eb.ts.net:8445/` on tailnet devices.

The server-side mention and threading behavior in the first three checks passed on 2026-10-31. Physical iPhone login, attachments, cellular access, and closed-app delivery have not been tested yet.

## If it does not connect

1. Confirm Tailscale is connected on the phone and the Mac mini is online in the tailnet.
2. Open the Element Web URL above in Safari. If that fails too, the problem is tailnet/service reachability rather than the Element app.
3. Keep the `https` scheme, exact tailnet hostname, and port (`8444` for Matrix, `8445` for Element Web). Do not substitute the older Hermes replica port.
4. Do not change exit-node, Sing-box, DNS, or proxy settings as part of Army Hub troubleshooting.
5. On the mini, check `docker compose ps` from the project directory. Matrix, PostgreSQL, Element, and backup should be running.
6. If chat loads but agents do not answer, run `sh scripts/install_bridges.sh` once from the Documents-authorized desktop session, then check the connector PID files and logs under `.runtime/`.
7. After a Mac reboot or logout, connector auto-start is not yet available; run the same install command once. Docker services have their own restart policy.

## Account and data recovery

- Keep Mo's Matrix password in the normal password manager after changing the temporary provisioning password.
- Do not use agent access tokens for phone recovery.
- Nightly local archives are in `.runtime/backups/`. The restore procedure and latest restore-drill result are in `docs/operations.md`.
- Off-Mac encrypted backup is still pending; a lost Mac cannot yet be treated as fully recoverable.

## Notifications

Message synchronization works through the homeserver, but iOS background push requires a working push gateway and Apple delivery path. Test a message while Element is closed. Do not treat background push as operational until that test passes; opening Element manually remains the fallback.
