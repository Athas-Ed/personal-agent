from __future__ import annotations

import json
import os
import ssl
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import certifi
import httpx
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from src.utils.cert_bundle import prepare_ca_bundle
from src.utils.sync import run_sync


@dataclass(frozen=True)
class AMapMcpConfig:
    name: str = "amap-maps-streamableHTTP"

    def url(self) -> str:
        key = (os.getenv("AMAP_KEY") or "").strip()
        if not key or key == "your_amap_key_here":
            raise RuntimeError("缺少 AMAP_KEY，请在 .env 中配置你的高德 Key。")
        return f"https://mcp.amap.com/mcp?key={key}"


class AMapWeatherMCPService:
    """
    高德地图 MCP（Streamable HTTP）客户端（单例 + tools 缓存）。

    这是第三方集成实现细节，因此放在 integrations 下。
    """

    _instance: "AMapWeatherMCPService | None" = None

    def __init__(self, tools_ttl_s: int = 300):
        self._tools_ttl_s = tools_ttl_s
        self._client: MultiServerMCPClient | None = None
        self._tools_cache: List[BaseTool] | None = None
        self._tools_cached_at: float | None = None

    @classmethod
    def get_instance(cls) -> "AMapWeatherMCPService":
        if cls._instance is None:
            cls._instance = AMapWeatherMCPService(tools_ttl_s=300)
        return cls._instance

    def _ensure_client(self) -> MultiServerMCPClient:
        if self._client is None:

            def _ensure_ca_bundle_path() -> str | None:
                ca_bundle = (os.getenv("SSL_CERT_FILE") or os.getenv("REQUESTS_CA_BUNDLE") or "").strip()
                if ca_bundle and os.path.exists(ca_bundle):
                    return ca_bundle

                watt = (os.getenv("WATT_CA_CERT") or "").strip()
                if not watt or (not os.path.exists(watt)):
                    return None

                repo = Path(__file__).resolve().parents[2]
                out_pem = repo / ".cache" / "watt-ca.pem"
                out_pem.parent.mkdir(parents=True, exist_ok=True)

                try:
                    ok = prepare_ca_bundle(src=Path(watt), dst=out_pem)
                    if ok and out_pem.exists():
                        return str(out_pem)
                except Exception:
                    pass

                # Fallback: use Windows certutil to convert DER -> PEM.
                try:
                    tmp = out_pem.with_suffix(".tmp.pem")
                    r2 = subprocess.run(
                        ["certutil", "-encode", watt, str(tmp)],
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if r2.returncode == 0 and tmp.exists():
                        text = tmp.read_text(encoding="utf-8", errors="ignore")
                        begin = "-----BEGIN CERTIFICATE-----"
                        end = "-----END CERTIFICATE-----"
                        blocks: list[str] = []
                        while True:
                            bi = text.find(begin)
                            if bi < 0:
                                break
                            ei = text.find(end, bi)
                            if ei < 0:
                                break
                            ei2 = ei + len(end)
                            blocks.append(text[bi:ei2].replace("\r\n", "\n").strip() + "\n")
                            text = text[ei2:]
                        if blocks:
                            out_pem.write_text("\n".join(blocks).strip() + "\n", encoding="utf-8", newline="\n")
                            tmp.unlink(missing_ok=True)
                            return str(out_pem)
                except Exception:
                    pass

                return None

            ca_bundle_path = _ensure_ca_bundle_path()

            def _httpx_client_factory(
                headers: dict[str, str] | None = None,
                timeout: httpx.Timeout | None = None,
                auth: httpx.Auth | None = None,
            ) -> httpx.AsyncClient:
                ctx = ssl.create_default_context(cafile=certifi.where())
                if ca_bundle_path and os.path.exists(ca_bundle_path):
                    ctx.load_verify_locations(cafile=ca_bundle_path)

                https_proxy = (os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or "").strip()
                http_proxy = (os.getenv("HTTP_PROXY") or os.getenv("http_proxy") or "").strip()
                all_proxy = (os.getenv("ALL_PROXY") or os.getenv("all_proxy") or "").strip()
                proxy = all_proxy or https_proxy or http_proxy or None

                return httpx.AsyncClient(
                    headers=headers,
                    timeout=timeout or httpx.Timeout(60.0, connect=60.0),
                    auth=auth,
                    proxy=proxy,
                    verify=ctx,
                    trust_env=True,
                )

            cfg: Dict[str, Dict[str, Any]] = {
                AMapMcpConfig().name: {
                    "url": AMapMcpConfig().url(),
                    "transport": "streamable_http",
                    "httpx_client_factory": _httpx_client_factory,
                }
            }
            self._client = MultiServerMCPClient(cfg)
        return self._client

    async def aget_tools(self, force_refresh: bool = False) -> List[BaseTool]:
        now = time.time()
        if (
            (not force_refresh)
            and self._tools_cache is not None
            and self._tools_cached_at is not None
            and (now - self._tools_cached_at) < self._tools_ttl_s
        ):
            return self._tools_cache
        tools = await self._ensure_client().get_tools()
        self._tools_cache = list(tools)
        self._tools_cached_at = now
        return self._tools_cache

    def get_tools(self, force_refresh: bool = False) -> List[BaseTool]:
        return run_sync(self.aget_tools(force_refresh=force_refresh))

    async def acall_tool(self, tool_name: str, args: Optional[Dict[str, Any]] = None) -> Any:
        tools = await self.aget_tools()
        for t in tools:
            if t.name == tool_name:
                result = await t.ainvoke(args or {})
                if isinstance(result, list) and result:
                    first = result[0]
                    if isinstance(first, dict) and first.get("type") == "text" and isinstance(first.get("text"), str):
                        text = first["text"].strip()
                        if text.startswith("{") and text.endswith("}"):
                            try:
                                return json.loads(text)
                            except Exception:
                                return result
                return result
        raise KeyError(f"未找到高德 MCP 工具：{tool_name}")

    def call_tool(self, tool_name: str, args: Optional[Dict[str, Any]] = None) -> Any:
        return run_sync(self.acall_tool(tool_name=tool_name, args=args))

    def guess_weather_tool_name(self) -> str:
        tools = self.get_tools()
        names = [t.name for t in tools]
        for n in names:
            if "weather" in n.lower():
                return n
        raise RuntimeError(f"未在高德 MCP 工具列表中找到 weather 相关工具。当前 tools: {names}")

