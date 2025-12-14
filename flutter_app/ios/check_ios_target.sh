#!/usr/bin/env bash
set -euo pipefail

required="13.0"
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
podfile="$repo_root/ios/Podfile"
pbxproj="$repo_root/ios/Runner.xcodeproj/project.pbxproj"

check_minimum() {
  local current="$1"
  python3 - "$required" "$current" <<'PY'
import sys

def normalize(v: str):
    return tuple(int(x) for x in v.split('.'))

req, cur = map(normalize, sys.argv[1:3])
if cur < req:
    sys.exit(1)
PY
}

echo "Checking Podfile platform…"
platform=$(python3 - "$podfile" <<'PY'
import re, sys, pathlib
podfile = pathlib.Path(sys.argv[1]).read_text()
match = re.search(r"platform\s*:ios,\s*['\"](\d+\.\d+)['\"]", podfile)
if not match:
    sys.exit(2)
print(match.group(1))
PY
) || { echo "Unable to read platform from Podfile"; exit 1; }

check_minimum "$platform" || { echo "Podfile platform $platform is below required $required"; exit 1; }

echo "Checking project deployment targets…"
python3 - "$required" "$pbxproj" <<'PY'
import re, sys, pathlib
req = sys.argv[1]
text = pathlib.Path(sys.argv[2]).read_text()
pattern = re.compile(r"IPHONEOS_DEPLOYMENT_TARGET\s*=\s*(\d+\.\d+)")
values = pattern.findall(text)
if not values:
    sys.exit(3)
def normalize(v: str):
    return tuple(int(x) for x in v.split('.'))

req_v = normalize(req)
failures = [v for v in values if normalize(v) < req_v]
if failures:
    print("Targets below required version:", ", ".join(sorted(set(failures))))
    sys.exit(1)
PY

if [[ $? -eq 0 ]]; then
  echo "All deployment targets are at least $required"
fi
