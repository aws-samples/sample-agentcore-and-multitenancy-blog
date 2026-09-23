#!/bin/bash
#
# Build the AgentCore direct-code-deploy bundle and upload it to S3.
#
# This replaces the packaging half of `agentcore deploy` from the
# bedrock-agentcore-starter-toolkit. AgentCore Runtime's CodeConfiguration
# artifact is just a zip in S3 containing the agent source plus its
# dependencies, so the toolkit is not required to produce one.
#
# Dependencies must be linux/aarch64 wheels because AgentCore Runtime runs
# ARM64. This mirrors the pattern prereq.sh already uses for the API Gateway
# Lambda, which pins manylinux2014_x86_64 the same way.
#
# The object key embeds a hash of the bundle contents. CloudFormation only
# rolls a runtime to new code when the S3 key or version changes, so a fixed
# key such as "deployment.zip" would leave the runtime pinned to whatever
# bundle it first saw. The hashed key makes code changes deploy correctly.
#
# Usage:
#   scripts/package_agent.sh <s3-bucket>
#
# Writes progress to stderr and the resulting S3 key to stdout, so callers can
# capture it:  CODE_PREFIX=$(scripts/package_agent.sh "$BUCKET")

set -euo pipefail

BUCKET="${1:?usage: package_agent.sh <s3-bucket>}"
PYTHON_VERSION="${PYTHON_VERSION:-3.12}"
PLATFORM_TAG="${PLATFORM_TAG:-manylinux2014_aarch64}"

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="$PROJECT_ROOT/build/agent-package"
ZIP_PATH="$PROJECT_ROOT/build/deployment.zip"

log() { echo "$@" >&2; }

cd "$PROJECT_ROOT"

log "📦 Building AgentCore deployment bundle"
log "   python:   $PYTHON_VERSION"
log "   platform: $PLATFORM_TAG (AgentCore Runtime is ARM64)"

rm -rf "$BUILD_DIR" "$ZIP_PATH"
mkdir -p "$BUILD_DIR"

# ---- 1. Dependencies (runtime-only requirements) ----
# --only-binary=:all: is deliberate: a source distribution would be built for
# the host architecture and fail at runtime on ARM64. If a dependency has no
# aarch64 wheel this fails loudly here rather than silently shipping a broken
# bundle.
log "⬇️  Installing dependencies for $PLATFORM_TAG..."
pip3 install \
  -r requirements.txt \
  -t "$BUILD_DIR" \
  --platform "$PLATFORM_TAG" \
  --python-version "$PYTHON_VERSION" \
  --only-binary=:all: \
  --no-warn-conflicts \
  --quiet

# Report the resolved versions of the packages whose APIs the agent imports
# directly. An unpinned transitive bump here (mcp 2.0 renaming
# streamablehttp_client, for example) otherwise only shows up as an ImportError
# in CloudWatch after the runtime is already deployed.
log "🔎 Resolved versions of API-critical dependencies:"
for dist in mcp fastmcp strands_agents bedrock_agentcore; do
  found=$(find "$BUILD_DIR" -maxdepth 1 -name "${dist}-*.dist-info" -print -quit 2>/dev/null)
  if [ -n "$found" ]; then
    log "   $(basename "$found" .dist-info)"
  fi
done

# ---- 2. Agent source ----
# main.py imports both the `agent` package and `scripts.utils`, so all three
# ship. Everything else in the repo (Streamlit UI, CloudFormation, tests,
# generated documents) is build-time or operator tooling and stays out.
log "📄 Copying agent source..."
cp main.py "$BUILD_DIR/"
cp -R agent "$BUILD_DIR/"
mkdir -p "$BUILD_DIR/scripts"
cp scripts/__init__.py scripts/utils.py "$BUILD_DIR/scripts/"

# Drop caches so the content hash is stable across machines.
find "$BUILD_DIR" -name "__pycache__" -type d -prune -exec rm -rf {} + 2>/dev/null || true
find "$BUILD_DIR" -name "*.pyc" -delete 2>/dev/null || true

# ---- 3. Zip ----
log "🗜️  Creating zip..."
( cd "$BUILD_DIR" && zip -r -q -X "$ZIP_PATH" . )

BUNDLE_HASH="$(shasum -a 256 "$ZIP_PATH" | cut -c1-12)"
S3_KEY="agent/deployment-${BUNDLE_HASH}.zip"
BUNDLE_SIZE="$(du -h "$ZIP_PATH" | cut -f1)"

log "   bundle size: $BUNDLE_SIZE"
log "   content hash: $BUNDLE_HASH"

# ---- 4. Upload ----
# Both tiers share one bundle: the code is identical and the tier is resolved
# per request from the payload, so there is no reason to build or store it
# twice.
log "☁️  Uploading to s3://$BUCKET/$S3_KEY..."
aws s3 cp "$ZIP_PATH" "s3://$BUCKET/$S3_KEY" --only-show-errors

log "✅ Bundle published"

# Only the key goes to stdout.
echo "$S3_KEY"
