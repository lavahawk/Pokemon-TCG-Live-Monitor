"""Release edition, set by installer/build_installer.ps1 (-Edition ai|free).

  ai    AI deck detection works out of the box through the hosted proxy
        (HOSTED_AI_URL); the OpenAI key stays on the server, never here.
  free  no hosted AI: the local predictor, or the user's own model / key.

A dev checkout is "ai" but stays local until HOSTED_AI_URL is set.
"""

EDITION = "ai"
HOSTED_AI_URL = ""  # e.g. "https://ptcgl-monitor-ai.<account>.workers.dev/v1" (ai_proxy/README.md)
