def parse_manifest(manifest_json: dict) -> list:
    return manifest_json.get("reportKeys", [])
