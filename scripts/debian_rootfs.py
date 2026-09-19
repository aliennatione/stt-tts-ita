#!/usr/bin/env python3
"""Scarica ed estrae la rootfs di una immagine Docker (solo stdlib, no docker).

Tira i layer tar.gz di library/debian:<tag> dal Registry API v2 e li estrae in
una directory, per usarla come rootfs con proot/chroot.

Uso:
  python3 scripts/debian_rootfs.py                 # bookworm-slim -> /srv/debian-rootfs
  python3 scripts/debian_rootfs.py --tag bullseye-slim --dest /srv/debian-bullseye
"""
import argparse
import io
import json
import os
import tarfile
import urllib.request

REPO = "library/debian"
DEFAULT_TAG = "bookworm-slim"
DEFAULT_DEST = "/srv/debian-rootfs"
ACCEPT_LIST = "application/vnd.docker.distribution.manifest.list.v2+json, application/vnd.oci.image.index.v1+json, application/json"
ACCEPT_MANIFEST = "application/vnd.docker.distribution.manifest.v2+json, application/vnd.oci.image.manifest.v1+json, application/json"


def http_get(url, token=None, accept=None):
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    if accept:
        req.add_header("Accept", accept)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def token_for(pull_repo):
    url = (
        "https://auth.docker.io/token?service=registry.docker.io"
        f"&scope=repository:{pull_repo}:pull"
    )
    return json.loads(
        http_get(url).decode()
    )["token"]


def pick_amd64(manifests):
    for m in manifests:
        if m.get("platform", {}).get("architecture") == "amd64":
            return m["digest"]
    return manifests[0]["digest"]


def main():
    ap = argparse.ArgumentParser(description="Estrae la rootfs di debian:<tag>.")
    ap.add_argument("--tag", default=DEFAULT_TAG, help="Tag immagine (default: bookworm-slim)")
    ap.add_argument("--dest", default=DEFAULT_DEST, help="Cartella di destinazione (default: /srv/debian-rootfs)")
    args = ap.parse_args()
    dest = args.dest

    tok = token_for(REPO)
    base = "https://registry-1.docker.io/v2/" + REPO
    top = json.loads(http_get(f"{base}/manifests/{args.tag}", tok, ACCEPT_LIST))
    if "manifests" in top:
        digest = pick_amd64(top["manifests"])
        man = json.loads(http_get(f"{base}/manifests/{digest}", tok, ACCEPT_MANIFEST))
    else:
        man = top
    layers = man.get("layers") or man.get("fsLayers")
    print(f"digest layers: {len(layers)}")
    os.makedirs(dest, exist_ok=True)
    for i, layer in enumerate(layers):
        dg = layer["digest"]
        sz = layer.get("size", 0)
        print(f"[{i+1}/{len(layers)}] {dg[:24]}... ({sz/1048576:.1f} MiB)")
        data = http_get(f"{base}/blobs/{dg}", tok, ACCEPT_MANIFEST)
        f = tarfile.open(fileobj=io.BytesIO(data), mode="r:*")
        for member in f.getmembers():
            if member.name == ".wh..wh..opq" or member.name.startswith(".wh."):
                continue
            try:
                f.extract(member, dest, filter="fully_trusted")
            except (KeyError, OSError):
                pass
        f.close()
    print("fatto:", dest)


if __name__ == "__main__":
    main()