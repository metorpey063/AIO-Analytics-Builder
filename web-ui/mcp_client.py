"""
AIO Analytics Builder — MCP HTTP Client
Directly calls the Tableau Next MCP server over Streamable HTTP transport.
Authenticates with the MCP ECA OAuth credentials (mcp_api scope).
"""

import json
import os
import sys
import uuid
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

MCP_ENDPOINT = "https://api.salesforce.com/platform/mcp/v1/analytics/tableau-next-pilot"


class MCPClient:
    """Lightweight MCP client that communicates directly with the Tableau Next MCP server."""

    def __init__(self, config=None):
        from connections import load_config
        self.config = config or load_config()
        self.sf = self.config.get("salesforce", {})
        self.mcp_client_id = self.sf.get("mcp_client_id", "")
        self.mcp_client_secret = self.sf.get("mcp_client_secret", "")
        self.sf_login_url = self.sf.get("sf_login_url", "https://login.salesforce.com")
        self.access_token = None
        self.session_id = None

    @property
    def available(self):
        """Check if MCP credentials are configured."""
        return bool(self.mcp_client_id)

    def authenticate(self):
        """Get an OAuth access token using the MCP ECA credentials."""
        if not self.mcp_client_id:
            raise RuntimeError("MCP client_id not configured. Set up the MCP ECA in Setup.")

        # Use the MCP-specific refresh token (from separate OAuth flow)
        refresh_token = self.sf.get("mcp_refresh_token", "")
        if not refresh_token:
            raise RuntimeError("No MCP refresh token. Click 'Authorize MCP' in Setup to authenticate.")

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": self.mcp_client_id,
        }

        r = requests.post(f"{self.sf_login_url}/services/oauth2/token", data=data)
        if r.status_code != 200:
            raise RuntimeError(f"MCP auth failed: {r.status_code} {r.text[:300]}")

        body = r.json()
        self.access_token = body["access_token"]

        # Save rotated refresh token if one was returned
        new_refresh = body.get("refresh_token")
        if new_refresh and new_refresh != refresh_token:
            try:
                from connections import load_full_config, save_full_config
                full = load_full_config()
                key = full.get("active_profile")
                if key and key in full.get("profiles", {}):
                    full["profiles"][key]["salesforce"]["mcp_refresh_token"] = new_refresh
                    save_full_config(full)
                    self.sf["mcp_refresh_token"] = new_refresh
            except Exception:
                pass

        return self.access_token

    def _headers(self):
        """Build request headers with auth token."""
        if not self.access_token:
            self.authenticate()
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }

    def initialize(self):
        """Send MCP initialize handshake."""
        msg = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "aio-web-ui", "version": "2.3.0"},
            },
        }
        r = requests.post(MCP_ENDPOINT, headers=self._headers(), json=msg)
        if r.status_code != 200:
            raise RuntimeError(f"MCP initialize failed: {r.status_code} {r.text[:300]}")

        result = self._parse_response(r)
        self.session_id = r.headers.get("Mcp-Session-Id", "")

        # Send required initialized notification
        notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        headers = self._headers()
        headers["Mcp-Session-Id"] = self.session_id
        requests.post(MCP_ENDPOINT, headers=headers, json=notif)

        return result

    def call_tool(self, tool_name, arguments):
        """Call an MCP tool and return the result."""
        if not self.session_id:
            self.initialize()

        msg = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        }

        headers = self._headers()
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id

        r = requests.post(MCP_ENDPOINT, headers=headers, json=msg)
        if r.status_code != 200:
            raise RuntimeError(f"MCP tool call failed: {r.status_code} {r.text[:300]}")

        return self._parse_response(r)

    def _parse_response(self, response):
        """Parse MCP response — handles both JSON and SSE formats."""
        content_type = response.headers.get("Content-Type", "")

        if "text/event-stream" in content_type:
            # SSE response — parse events
            result = None
            for line in response.text.splitlines():
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[6:])
                        if "result" in data:
                            result = data["result"]
                        elif "error" in data:
                            raise RuntimeError(f"MCP error: {data['error']}")
                    except json.JSONDecodeError:
                        pass
            return result
        else:
            # Direct JSON response
            body = response.json()
            if "result" in body:
                return body["result"]
            elif "error" in body:
                raise RuntimeError(f"MCP error: {body['error']}")
            return body

    def list_tools(self):
        """List available MCP tools."""
        if not self.session_id:
            self.initialize()

        msg = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/list",
            "params": {},
        }

        headers = self._headers()
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id

        r = requests.post(MCP_ENDPOINT, headers=headers, json=msg)
        return self._parse_response(r)

    # ----- Convenience methods for common operations -----

    def create_visualization(self, **kwargs):
        return self.call_tool("create_visualization", kwargs)

    def create_dashboard(self, **kwargs):
        return self.call_tool("create_dashboard", kwargs)

    def edit_dashboard(self, **kwargs):
        return self.call_tool("edit_dashboard", kwargs)

    def create_semantic_model(self, **kwargs):
        return self.call_tool("create_semantic_model", kwargs)

    def update_semantic_model(self, **kwargs):
        return self.call_tool("update_semantic_model", kwargs)

    def add_semantic_model_metric(self, **kwargs):
        return self.call_tool("add_semantic_model_metric", kwargs)

    def create_workspace(self, **kwargs):
        return self.call_tool("create_workspace", kwargs)

    def add_workspace_asset(self, **kwargs):
        return self.call_tool("add_workspace_asset", kwargs)

    def list_workspaces(self):
        return self.call_tool("list_workspaces", {})

    def get_semantic_model(self, **kwargs):
        return self.call_tool("get_semantic_model", kwargs)

    def generate_business_preference(self, **kwargs):
        return self.call_tool("generate_business_preference", kwargs)

    def analyze_data(self, **kwargs):
        return self.call_tool("analyze_data", kwargs)


def test_mcp_connection(config=None):
    """Quick test — try to list workspaces via MCP."""
    try:
        client = MCPClient(config)
        if not client.available:
            return {"ok": False, "error": "MCP client_id not configured"}

        client.authenticate()
        client.initialize()
        result = client.list_workspaces()
        return {"ok": True, "workspaces": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


if __name__ == "__main__":
    result = test_mcp_connection()
    print(json.dumps(result, indent=2, default=str))
