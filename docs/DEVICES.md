# One computer first, more when you need them

AIRI works on one computer. There is no requirement for two Macs, a particular Apple chip,
Thunderbolt, a NAS or a second account. The computer running the AIRI web app remains the
**coordinator**: it owns the UI, records, schedules, file tools, microphone and camera.

## Add another computer

1. Install this repository and its Python requirements on the other computer.
2. Install Ollama and a local model. Use the same model/version on both machines for failover.
3. On that computer run `.venv/bin/python run.py --device-worker`. On macOS,
   double-click **Start Worker.command** instead. Windows/Linux workers use their Python
   interpreter; the worker itself does not depend on the desktop's macOS integrations.
4. Keep the worker running. Copy its complete `airi-device-v1:…` connection code.
5. In the main AIRI window open **Settings → 기기 연결 → 기기 추가**, paste the code and click
   **연결하고 자동으로 사용**. You may give it a friendly name.

If the computer has several network interfaces, choose the reachable private IP explicitly:
`python run.py --device-worker --listen YOUR_PRIVATE_IP --device-name "Study PC"`.
Allow incoming connections to the worker port (default 8770) only on your trusted LAN.
Keep Ollama listening on loopback; it does not need to be exposed to the network.
No automatic network scan, remote software install or firewall change is performed.

## Automatic main selection

The **inference main** is selected separately for the requested local model. The router checks
installed model names/digests, device availability, reported RAM/CPU capacity, health round-trip
time and worker occupancy. This is a capacity heuristic, **not a GPU benchmark**. The display
shows the selected device and actual response device; model choice remains the user's choice.
Small score changes do not repeatedly switch the main device.

Up to 16 additional devices can be registered. A background health monitor checks every
15 seconds; a failed device receives a 30-second cooldown. If a request fails before output,
the same model weights can run on another available device. An interrupted streamed answer
is surfaced to the user instead of repeating partial output or replaying external actions.
Cloud providers remain explicit settings and are not automatic local-worker fallbacks.

The coordinator's stored records do not migrate when the inference main changes. If the
coordinator is powered off, its UI and scheduling stop. This feature is compute routing,
not a distributed database or full-host high availability. Workers can be stopped and
restarted with the same command; persistent worker services are not installed automatically.

## Privacy and pairing

Pairing is explicit. A connected worker can receive the prompt/context needed for the AI
request, including supplied images when an image-capable model is selected. It does not
receive an entire data directory or gain shell, filesystem or account access.

Traffic uses TLS with the exact certificate fingerprint from the pairing code. Requests use
HMAC authentication, timestamp validation and replay protection. Local pairings are stored
under `data/devices/` with restricted permissions; worker identities under `data/device-worker/`.
Both are excluded from Git. Do not share connection codes publicly.

**잠시 사용 안 함** excludes a device from routing; **연결 해제** removes its local registration.
To revoke a previously shared code at the worker, restart it with `--rotate-pairing` and
register the new code. Removing a registration does not erase either computer's records.

## Verification

Automated tests cover real loopback TLS worker requests, certificate mismatch, wrong key,
replay rejection, model filtering, persisted registration, disable/removal, single-device
operation, automatic selection, failover and avoiding retries after streamed output.
Multiple physical computers, every OS firewall and GPU performance have not been certified.

Model transport follows the [Ollama OpenAI-compatible API](https://docs.ollama.com/api/openai-compatibility)
and [installed-model inventory](https://docs.ollama.com/api/tags).
