"""Thin, read-only client for the metering service's admin API."""

import httpx


class AdminClient:
    def __init__(self, base_url: str, admin_key: str, transport: httpx.BaseTransport | None = None):
        self._http = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"X-Admin-Key": admin_key},
            timeout=10.0,
            transport=transport,
        )

    def list_clients(self) -> list[str]:
        return self._get("/admin/clients")

    def usage(self, client_id: str, minutes: int) -> dict:
        return self._get(f"/admin/usage/{client_id}", params={"minutes": minutes})

    def _get(self, path: str, params: dict | None = None):
        response = self._http.get(path, params=params)
        if response.status_code == 401:
            raise RuntimeError("Admin API rejected the key (401). Check --admin-key.")
        if response.status_code == 503:
            raise RuntimeError("Admin API is disabled (503). Set ADMIN_API_KEY on the service.")
        response.raise_for_status()
        return response.json()
