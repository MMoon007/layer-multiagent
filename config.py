"""
配置管理模块
用于读取和管理应用配置。
"""

import os
from typing import Any, Dict

import yaml


class Config:
    """配置管理类。"""

    _instance = None
    _config_data = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._config_data is None:
            self._load_config()

    def _load_config(self):
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "config.yaml",
        )

        if not os.path.exists(config_path):
            raise FileNotFoundError(
                f"配置文件不存在: {config_path}\n"
                "请创建 config.yaml 配置文件"
            )

        try:
            with open(config_path, "r", encoding="utf-8") as file:
                self._config_data = yaml.safe_load(file)
            print(f"✅ 配置文件加载成功: {config_path}")
        except Exception as exc:
            raise Exception(f"配置文件读取失败: {exc}")

    def get(self, key: str, default: Any = None) -> Any:
        if self._config_data is None:
            self._load_config()

        value = self._config_data
        for current_key in key.split("."):
            if isinstance(value, dict) and current_key in value:
                value = value[current_key]
            else:
                return default
        return value

    def get_openai_config(self) -> Dict[str, Any]:
        return {
            "api_base": self.get("openai.api_base"),
            "api_key": self.get("openai.api_key"),
            "model": self.get("openai.model"),
            "temperature": self.get("openai.temperature", 0.9),
        }

    def get_redis_config(self) -> Dict[str, Any]:
        return {
            "host": self.get("redis.host", "127.0.0.1"),
            "port": self.get("redis.port", 6379),
        }

    def get_rag_config(self) -> Dict[str, Any]:
        return {
            "folder_path": self.get("rag.folder_path", "./rag_data"),
            "index_path": self.get("rag.index_path", "./faiss_index"),
            "embedding_model": self.get("rag.embedding_model", "Qwen/Qwen3-Embedding-0.6B"),
            "rerank_model": self.get("rag.rerank_model", "BAAI/bge-reranker-base"),
            "bm25_k": self.get("rag.bm25_k", 5),
            "faiss_k": self.get("rag.faiss_k", 5),
            "top_n": self.get("rag.top_n", 1),
            "chunk_size": self.get("rag.chunk_size", 500),
            "chunk_overlap": self.get("rag.chunk_overlap", 50),
            "device": self.get("rag.device", "cpu"),
        }

    def reload(self):
        self._config_data = None
        self._load_config()


config = Config()


def get_config(key: str, default: Any = None) -> Any:
    return config.get(key, default)


def get_openai_config() -> Dict[str, Any]:
    return config.get_openai_config()


def get_redis_config() -> Dict[str, Any]:
    return config.get_redis_config()


def get_rag_config() -> Dict[str, Any]:
    return config.get_rag_config()


if __name__ == "__main__":
    print("=" * 60)
    print("测试配置读取")
    print("=" * 60)
    print("\n1. OpenAI 配置:")
    print(get_openai_config())
    print("\n2. Redis 配置:")
    print(get_redis_config())
    print("\n3. RAG 配置:")
    print(get_rag_config())
    print("\n4. 获取单个配置项:")
    print(f"OpenAI API Key: {get_config('openai.api_key')}")
    print(f"Redis Host: {get_config('redis.host')}")
