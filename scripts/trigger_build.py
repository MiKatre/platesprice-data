"""Validate and publish an immutable data snapshot. Never log the secret hook URL."""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from plates.models import Snapshot


def validate_snapshot(path):
    snapshot = Snapshot.model_validate_json(Path(path).read_text())
    if not any(offer.sale_unit != "unknown" for s in snapshot.sources for offer in s.offers):
        raise ValueError("Snapshot contains no confirmed packs")
    return snapshot


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-only", metavar="SNAPSHOT")
    args = parser.parse_args(argv)
    try:
        validate_snapshot(args.validate_only or "data/latest.json")
    except (OSError, ValueError):
        print("Invalid plate snapshot; website rebuild not requested", file=sys.stderr)
        return 1
    if args.validate_only:
        print("Plate snapshot validated")
        return 0
    hook = os.environ.get("NETLIFY_BUILD_HOOK", "")
    url = urlsplit(hook)
    if (
        url.scheme != "https"
        or url.netloc != "api.netlify.com"
        or not re.fullmatch(r"/build_hooks/[a-f0-9]+", url.path)
        or url.query
        or url.fragment
    ):
        print("Missing or invalid NETLIFY_BUILD_HOOK repository secret", file=sys.stderr)
        return 1
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    if not re.fullmatch(r"[a-f0-9]{40}", commit):
        print("Invalid published data commit", file=sys.stderr)
        return 1
    payload = json.dumps({"plate_data_commit": commit}).encode()
    for attempt in range(3):
        try:
            request = urllib.request.Request(
                hook, data=payload, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                if not 200 <= response.status < 300:
                    raise ValueError("Unexpected build hook response")
            print(f"Netlify rebuild requested for plate data commit {commit}")
            return 0
        except (urllib.error.URLError, TimeoutError, ValueError):
            if attempt == 2:
                print("Netlify build hook failed after three attempts", file=sys.stderr)
                return 1
            time.sleep(2**attempt)
    return 1


if __name__ == "__main__":
    sys.exit(main())
