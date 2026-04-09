from __future__ import annotations

import os

import certifi
import httpx
import ssl
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from .config import Settings


def _sanitize_ssl_env() -> None:
    """
    某些代理/抓包工具会设置 SSL_CERT_FILE / REQUESTS_CA_BUNDLE，
    但如果路径失效，会导致 httpx 初始化直接抛 FileNotFoundError([Errno 2])。
    这里做一次兜底清理，避免影响正常对话。
    """
    for key in ("SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        v = (os.getenv(key) or "").strip()
        if v and (v.startswith("$") or (not os.path.exists(v))):
            os.environ.pop(key, None)


def _build_http_client() -> httpx.Client:
    _sanitize_ssl_env()

    https_proxy = (os.getenv("HTTPS_PROXY") or os.getenv("https_proxy") or "").strip()
    http_proxy = (os.getenv("HTTP_PROXY") or os.getenv("http_proxy") or "").strip()
    all_proxy = (os.getenv("ALL_PROXY") or os.getenv("all_proxy") or "").strip()

    verify_ssl_raw = (os.getenv("OPENAI_SSL_VERIFY") or os.getenv("SSL_VERIFY") or "").strip().lower()
    ca_bundle = (os.getenv("SSL_CERT_FILE") or os.getenv("REQUESTS_CA_BUNDLE") or "").strip()

    # 证书策略（更贴近 Windows 用户环境）：
    # - 默认使用系统证书库（ssl.create_default_context），兼容企业代理/自签根证书已安装到系统的情况
    # - 若存在自定义 CA bundle，则追加加载
    # - 若显式关闭校验，则直接 verify=False
    verify: bool | ssl.SSLContext
    if verify_ssl_raw in {"0", "false", "no", "off"}:
        verify = False
    else:
        ctx = ssl.create_default_context()
        try:
            # 确保公共站点也可校验（某些精简 Python 环境系统证书可能不完整）
            ctx.load_verify_locations(cafile=certifi.where())
        except Exception:
            pass
        if ca_bundle and os.path.exists(ca_bundle):
            try:
                ctx.load_verify_locations(cafile=ca_bundle)
            except Exception:
                pass
        verify = ctx

    proxy = None
    if all_proxy:
        proxy = all_proxy
    elif https_proxy:
        proxy = https_proxy
    elif http_proxy:
        proxy = http_proxy

    return httpx.Client(
        proxy=proxy,
        verify=verify,
        timeout=httpx.Timeout(60.0, connect=60.0),
        trust_env=True,
    )


def build_chat_llm(settings: Settings) -> ChatOpenAI:
    return ChatOpenAI(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.chat_model,
        temperature=0.2,
        http_client=_build_http_client(),
    )


def build_embeddings(settings: Settings) -> OpenAIEmbeddings:
    provider = (getattr(settings, "embeddings_provider", "") or "").strip().lower()
    if provider in {"local", "hf", "huggingface", "sentence-transformers", "sentence_transformers"}:
        # Optional dependency: sentence-transformers
        from langchain_community.embeddings import HuggingFaceEmbeddings

        model_name = (getattr(settings, "local_embeddings_model", "") or "").strip() or "BAAI/bge-small-zh-v1.5"
        device = (getattr(settings, "local_embeddings_device", "") or "").strip() or "cpu"

        # bge 系列常见推荐：normalize_embeddings=True（便于用 cosine / inner product）
        return HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={"device": device},
            encode_kwargs={"normalize_embeddings": True},
        )

    # Default: OpenAI-compatible embeddings via API (DeepSeek compatible)
    return OpenAIEmbeddings(
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url,
        model=settings.embed_model,
        http_client=_build_http_client(),
    )

