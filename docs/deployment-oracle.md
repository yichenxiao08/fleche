# Oracle Cloud demo deployment

This deployment runs Flèche and Checkmate on the existing Toronto tenancy using an Always Free `VM.Standard.E2.1.Micro` instance. Oracle Run Command provides administration; SSH and the app's port 8000 stay closed. The subnet accepts inbound TCP 80 and 443 for Caddy's HTTPS certificate and public site. The instance dynamic group is restricted to the exact replacement VM.

## Flèche

`compose.oci.yaml` runs the full video-enabled Flèche app with `COACH_CORE=new`, the Groq Qwen provider first, Gemini second, and Caddy in front. Caddy protects the site with HTTP Basic Auth and obtains HTTPS certificates for the VM's `<public-ip-with-dashes>.nip.io` hostname. The app port is exposed only to the Compose network. SQLite data, videos, and Caddy certificates persist in named volumes.

The provider keys are optional at initial startup so the login and saved-session UI can be demonstrated before live chat is configured. Replace the `PENDING` values in the `FlecheGroqApiKey` and `FlecheGeminiApiKey` OCI secrets to enable live model replies. The VM loads them into the app's private environment and restarts the app. The application tries Groq, then Gemini, and returns its normal failure message if neither provider is available. Both providers use free tiers and have daily limits.

## Checkmate

Checkmate runs as a separate `systemd` service and needs outbound HTTPS only. It does not need a public port. Replace the `PENDING` value in `CheckmateLichessBotToken` with a Lichess bot token using the `bot:play` scope; the VM then loads it and starts the service. Test casual games first. Flèche video analysis and Checkmate share the VM's limited CPU and memory, so both can run slowly at the same time.

## Secrets and maintenance

Provider API keys and the Lichess token belong in the three named OCI secrets for this deployment. Enter or rotate their values in the Oracle Console's Secret Management page. The instance can read only those secret IDs through its instance identity. Do not put secret values in Run Command text, shell history, source control, or `.env.oci.example`.

Oracle Run Command is the supported administrative path for this VM. Keep the dynamic group matched to the exact instance ID. Keep public ingress limited to TCP 80 and 443; do not open 22 or 8000. After a code update reaches `codex/resume-demo`, an administrator can use Run Command to update `/opt/fleche` and restart the Compose stack. Back up the persistent Docker volumes before replacing or deleting the VM.
