"""Bundles collection.json (and config.json, if present) into site/data.json for the static site."""

import json
import os


def main():
    with open("collection.json") as f:
        collection = json.load(f)

    payload = {"collection": collection}

    if os.path.exists("config.json"):
        with open("config.json") as f:
            payload["config"] = json.load(f)
        print("Bundling config.json into site data")

    data = json.dumps(payload, ensure_ascii=False)

    with open("site/data.json", "w") as f:
        f.write(data)

    print(f"Wrote {len(data.encode())} bytes -> site/data.json")


if __name__ == "__main__":
    main()
