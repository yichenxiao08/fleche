# Oracle Cloud demo deployment

This profile runs the full Flèche web app, video-analysis worker, and Caddy HTTPS proxy on one ARM VM. It uses the new Groq-then-Gemini coach core, with the existing free-tier provider keys. Caddy requires HTTP Basic Authentication over HTTPS before proxying to the app. SQLite, uploaded videos, and HTTPS certificates persist in Docker volumes. The app listens only inside the Compose network.

## Create the VM

In the Oracle Cloud console, create an Ubuntu ARM64 VM in your home region with shape `VM.Standard.A1.Flex`, 2 OCPUs, 12 GB memory, and a 50 GB boot volume. Assign a public IPv4 address and add your SSH public key during creation. The Always Free A1 allowance is up to 2 OCPUs and 12 GB RAM per month, subject to capacity in your home region.

In the VM's VCN security list, allow inbound TCP 22 only from your current public IP, and TCP 80 and 443 from `0.0.0.0/0` so Caddy can obtain and renew its certificate. Do not open port 8000. Keep the SSH private key on your own computer. Caddy's HTTP Basic Authentication protects the app, but do not reuse a password from another service.

## Install and start

SSH to the VM, install Docker Engine with its Compose plugin using Docker's official Ubuntu instructions, then run:

```sh
git clone https://github.com/yichenxiao08/fleche.git
cd fleche
git switch main
cp .env.oci.example .env.oci
```

Edit `.env.oci`: set `FENCECOACH_DOMAIN` to `<public-ip-with-dashes>.nip.io` (for example, `203-0-113-10.nip.io`), set the existing Groq and Gemini API keys, and choose an authentication username. Generate a password hash with `docker run -it --rm caddy:2-alpine caddy hash-password`; Caddy reads the password without echoing it. Paste the output into `FENCECOACH_BASIC_AUTH_HASH` and keep `.env.oci` private. Then start the stack:

```sh
docker compose --env-file .env.oci -f compose.oci.yaml up -d --build
docker compose --env-file .env.oci -f compose.oci.yaml logs -f caddy fencecoach
```

The first build installs video-analysis dependencies and downloads the pose model. The coach tries Groq Qwen first, Gemini second, then returns its plain failure message; no local model is loaded. Once Caddy obtains its certificate, open `https://<FENCECOACH_DOMAIN>` and sign in with the Basic Auth credentials. The VM must be reachable on ports 80 and 443 for certificate issuance.

To update after a new commit reaches `main`, run `git pull` followed by the same `docker compose ... up -d --build` command. Back up the `fencecoach-data` volume before replacing or deleting the VM. The instance is a single-user demo; Basic Auth protects access, and the single-instance SQLite setup should not be scaled horizontally.

## Keep Checkmate online too

Checkmate runs as a separate `systemd` service from its own checkout; it needs outbound HTTPS only and no inbound port. The local Checkmate checkout has an Oracle/Lichess guide and the unit file under `deploy/lichess`. It accepts one game at a time and shares the VM's CPU with Flèche, so video analysis may run slower while Checkmate is searching.
