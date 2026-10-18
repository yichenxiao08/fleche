# Oracle Cloud demo deployment

This profile runs the full Flèche web app, video-analysis worker, local Ollama fallback, and Caddy HTTPS proxy on one ARM VM. SQLite, uploaded videos, the Ollama model, and HTTPS certificates persist in Docker volumes. The app listens only inside the Compose network.

## Create the VM

In the Oracle Cloud console, create an Ubuntu ARM64 VM in your home region with shape `VM.Standard.A1.Flex`, 2 OCPUs, 12 GB memory, and a 50 GB boot volume. Assign a public IPv4 address and add your SSH public key during creation. The Always Free A1 allowance is up to 2 OCPUs and 12 GB RAM per month, subject to capacity in your home region.

In the VM's VCN security list, allow inbound TCP 22 only from your current public IP, and TCP 80 and 443 from `0.0.0.0/0`. Do not open port 8000. Keep the SSH private key on your own computer.

## Install and start

SSH to the VM, install Docker Engine with its Compose plugin using Docker's official Ubuntu instructions, then run:

```sh
git clone https://github.com/yichenxiao08/fleche.git
cd fleche
git switch codex/resume-demo
cp .env.oci.example .env.oci
```

Edit `.env.oci`: set `FENCECOACH_DOMAIN` to `<public-ip-with-dashes>.nip.io` (for example, `203-0-113-10.nip.io`) and add a Gemini API key. Keep `.env.oci` private. Then start the stack:

```sh
docker compose --env-file .env.oci -f compose.oci.yaml up -d --build
docker compose --env-file .env.oci -f compose.oci.yaml logs -f caddy fencecoach
```

The first build installs video-analysis dependencies and downloads the pose model; Ollama downloads `qwen2.5:3b` for fallback coaching. Once Caddy obtains its certificate, open `https://<FENCECOACH_DOMAIN>`. The VM must be reachable on ports 80 and 443 for certificate issuance.

To update after a new commit reaches the branch, run `git pull` followed by the same `docker compose ... up -d --build` command. Back up the `fencecoach-data` volume before replacing or deleting the VM. This is a single-instance demo; it has no user authentication, so avoid uploading private footage or personal information.
