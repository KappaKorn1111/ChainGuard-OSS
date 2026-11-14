import argparse
import json
import urllib.error
import urllib.request

BASE_URL = "http://127.0.0.1:8000/api/v1"
EMAIL = "persistence-check@example.com"
PASSWORD = "PersistenceCheck123"


def request(path: str, payload: dict) -> tuple[int, dict]:
    body = json.dumps(payload).encode()
    request_object = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request_object, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("create", "verify"))
    args = parser.parse_args()
    if args.action == "create":
        status, payload = request(
            "/auth/bootstrap",
            {
                "email": EMAIL,
                "password": PASSWORD,
                "display_name": "Persistence Check",
                "organization_name": "Persistence Check",
                "organization_slug": "persistence-check",
            },
        )
        if status != 201:
            raise SystemExit(f"bootstrap failed: {status} {payload}")
    else:
        status, payload = request(
            "/auth/login",
            {
                "email": EMAIL,
                "password": PASSWORD,
                "organization_slug": "persistence-check",
            },
        )
        if status != 200 or "access_token" not in payload:
            raise SystemExit(f"persisted login failed: {status} {payload}")
    print(f"persistence probe {args.action}: ok")


if __name__ == "__main__":
    main()
