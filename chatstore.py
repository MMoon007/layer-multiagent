import redis.asyncio as redis
import json
import time
import asyncio
from typing import List, Dict, Optional, Tuple
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

class ChatStore:
    """
    Redis聊天存储管理器
    支持用户多会话管理，格式：user-conv1, user-conv2, ...
    """
    
    def __init__(self, host="127.0.0.1", port=6378):
        self.host = host
        self.port = port
        self.r = None
        self._initialized = False
        
        # 内存存储备用
        self._memory_store = {}
        self._memory_meta = {}

    async def _ensure_initialized(self):
        """确保Redis连接已初始化"""
        if not self._initialized:
            try:
                self.r = redis.Redis(host=self.host, port=self.port, decode_responses=True)
                await self.r.ping()  # 测试连接
                print(f"✅ Redis连接成功 ({self.host}:{self.port})")
            except (redis.ConnectionError, redis.RedisError) as e:
                print(f"⚠️ Redis连接失败，将使用内存模式: {e}")
                self.r = None
            self._initialized = True

    async def _is_redis_available(self) -> bool:
        """检查Redis是否可用"""
        await self._ensure_initialized()
        return self.r is not None

    def _chat_key(self, user_id: str, conv_id: str) -> str:
        """聊天消息存储键"""
        return f"chat:{user_id}:{conv_id}"

    def _user_convs_key(self, user_id: str) -> str:
        """用户会话列表键"""
        return f"user:{user_id}:convs"

    def _conv_meta_key(self, user_id: str, conv_id: str) -> str:
        """会话元数据键"""
        return f"conv:{user_id}:{conv_id}:meta"

    def _conv_counter_key(self, user_id: str) -> str:
        """用户会话计数器键"""
        return f"user:{user_id}:conv_counter"

    # =========================
    # 消息序列化/反序列化
    # =========================
    @staticmethod
    def serialize_message(msg: BaseMessage) -> str:
        """序列化消息对象"""
        if isinstance(msg, HumanMessage):
            return json.dumps({
                "type": "human", 
                "content": msg.content,
                "timestamp": time.time()
            })
        elif isinstance(msg, AIMessage):
            return json.dumps({
                "type": "ai", 
                "content": msg.content,
                "timestamp": time.time()
            })
        else:
            raise ValueError(f"不支持的消息类型: {type(msg)}")

    @staticmethod
    def deserialize_message(msg_json: str) -> BaseMessage:
        """反序列化消息对象"""
        data = json.loads(msg_json)
        msg_type = data.get("type", "")
        content = data.get("content", "")
        
        if msg_type == "human":
            return HumanMessage(content=content)
        elif msg_type == "ai":
            return AIMessage(content=content)
        else:
            raise ValueError(f"未知消息类型: {msg_type}")

    # =========================
    # 会话管理
    # =========================
    async def create_new_conversation(self, user_id: str, title: str = None) -> str:
        """为用户创建新会话，返回conv_id"""
        if await self._is_redis_available():
            try:
                # 获取下一个会话编号
                conv_num = await self.r.incr(self._conv_counter_key(user_id))
                conv_id = f"conv{conv_num}"
                
                # 添加到用户会话列表
                await self.r.sadd(self._user_convs_key(user_id), conv_id)
                
                # 创建会话元数据
                now = time.strftime("%Y-%m-%d %H:%M:%S")
                await self.r.hset(self._conv_meta_key(user_id, conv_id), mapping={
                    "title": title or f"会话 {conv_num}",
                    "created_at": now,
                    "updated_at": now,
                    "message_count": 0
                })
            except redis.RedisError as e:
                print(f"⚠️ Redis操作失败，切换到内存模式: {e}")
                self.r = None
                return await self.create_new_conversation(user_id, title)
        else:
            # 内存模式
            if user_id not in self._memory_store:
                self._memory_store[user_id] = {}
                self._memory_meta[user_id] = {}
            
            conv_num = len(self._memory_store[user_id]) + 1
            conv_id = f"conv{conv_num}"
            
            self._memory_store[user_id][conv_id] = []
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            self._memory_meta[user_id][conv_id] = {
                "title": title or f"会话 {conv_num}",
                "created_at": now,
                "updated_at": now,
                "message_count": 0
            }
        
        print(f"📝 创建新会话: {user_id}-{conv_id}")
        return conv_id

    async def get_user_conversations(self, user_id: str) -> Dict[str, Dict]:
        """获取用户的所有会话及其元数据"""
        if await self._is_redis_available():
            try:
                conv_ids = await self.r.smembers(self._user_convs_key(user_id))
                conversations = {}
                for conv_id in conv_ids:
                    meta = await self.r.hgetall(self._conv_meta_key(user_id, conv_id))
                    if meta:
                        conversations[conv_id] = meta
                return conversations
            except redis.RedisError:
                print("⚠️ Redis读取用户会话失败")
                return {}
        else:
            # 内存模式
            return self._memory_meta.get(user_id, {})

    async def delete_conversation(self, user_id: str, conv_id: str) -> bool:
        """删除指定会话"""
        if await self._is_redis_available():
            try:
                # 删除消息
                await self.r.delete(self._chat_key(user_id, conv_id))
                # 删除元数据
                await self.r.delete(self._conv_meta_key(user_id, conv_id))
                # 从用户会话列表中移除
                await self.r.srem(self._user_convs_key(user_id), conv_id)
                print(f"🗑️ 删除会话: {user_id}-{conv_id}")
                return True
            except redis.RedisError:
                print("⚠️ Redis删除会话失败")
                return False
        else:
            # 内存模式
            if user_id in self._memory_store and conv_id in self._memory_store[user_id]:
                del self._memory_store[user_id][conv_id]
                if user_id in self._memory_meta and conv_id in self._memory_meta[user_id]:
                    del self._memory_meta[user_id][conv_id]
                print(f"🗑️ 删除会话: {user_id}-{conv_id}")
                return True
            return False

    # =========================
    # 消息操作
    # =========================
    async def add_message(self, user_id: str, conv_id: str, message: BaseMessage):
        """添加消息到会话"""
        if await self._is_redis_available():
            try:
                # 序列化并存储消息
                msg_json = self.serialize_message(message)
                await self.r.rpush(self._chat_key(user_id, conv_id), msg_json)
                
                # 确保conv_id在用户会话列表中
                await self.r.sadd(self._user_convs_key(user_id), conv_id)
                
                # 更新会话元数据
                now = time.strftime("%Y-%m-%d %H:%M:%S")
                meta_key = self._conv_meta_key(user_id, conv_id)
                
                if not await self.r.exists(meta_key):
                    # 如果会话不存在，创建它
                    title = message.content[:20] + "..." if len(message.content) > 20 else message.content
                    await self.r.hset(meta_key, mapping={
                        "title": title,
                        "created_at": now,
                        "updated_at": now,
                        "message_count": 1
                    })
                else:
                    # 更新现有会话
                    await self.r.hset(meta_key, "updated_at", now)
                    await self.r.hincrby(meta_key, "message_count", 1)
                    
            except redis.RedisError:
                print("⚠️ Redis写入消息失败")
        else:
            # 内存模式
            if user_id not in self._memory_store:
                self._memory_store[user_id] = {}
                self._memory_meta[user_id] = {}
            
            if conv_id not in self._memory_store[user_id]:
                self._memory_store[user_id][conv_id] = []
                now = time.strftime("%Y-%m-%d %H:%M:%S")
                title = message.content[:20] + "..." if len(message.content) > 20 else message.content
                self._memory_meta[user_id][conv_id] = {
                    "title": title,
                    "created_at": now,
                    "updated_at": now,
                    "message_count": 0
                }
            
            self._memory_store[user_id][conv_id].append(message)
            now = time.strftime("%Y-%m-%d %H:%M:%S")
            self._memory_meta[user_id][conv_id]["updated_at"] = now
            self._memory_meta[user_id][conv_id]["message_count"] += 1

    async def get_messages(self, user_id: str, conv_id: str) -> List[BaseMessage]:
        """获取会话的所有消息"""
        if await self._is_redis_available():
            try:
                msgs_json = await self.r.lrange(self._chat_key(user_id, conv_id), 0, -1)
                return [self.deserialize_message(msg_json) for msg_json in msgs_json]
            except redis.RedisError:
                print("⚠️ Redis读取消息失败")
                return []
        else:
            # 内存模式
            return self._memory_store.get(user_id, {}).get(conv_id, [])

    async def get_recent_messages(self, user_id: str, conv_id: str, limit: int = 10) -> List[BaseMessage]:
        """获取会话的最近N条消息"""
        if await self._is_redis_available():
            try:
                msgs_json = await self.r.lrange(self._chat_key(user_id, conv_id), -limit, -1)
                return [self.deserialize_message(msg_json) for msg_json in msgs_json]
            except redis.RedisError:
                print("⚠️ Redis读取最近消息失败")
                return []
        else:
            # 内存模式
            messages = self._memory_store.get(user_id, {}).get(conv_id, [])
            return messages[-limit:] if messages else []

    async def clear_conversation(self, user_id: str, conv_id: str) -> bool:
        """清空会话消息（保留元数据）"""
        if await self._is_redis_available():
            try:
                await self.r.delete(self._chat_key(user_id, conv_id))
                # 重置消息计数
                meta_key = self._conv_meta_key(user_id, conv_id)
                if await self.r.exists(meta_key):
                    await self.r.hset(meta_key, "message_count", 0)
                    await self.r.hset(meta_key, "updated_at", time.strftime("%Y-%m-%d %H:%M:%S"))
                return True
            except redis.RedisError:
                print("⚠️ Redis清空会话失败")
                return False
        else:
            # 内存模式
            if user_id in self._memory_store and conv_id in self._memory_store[user_id]:
                self._memory_store[user_id][conv_id] = []
                if user_id in self._memory_meta and conv_id in self._memory_meta[user_id]:
                    self._memory_meta[user_id][conv_id]["message_count"] = 0
                    self._memory_meta[user_id][conv_id]["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                return True
            return False

    # =========================
    # 统计信息
    # =========================
    async def get_conversation_stats(self, user_id: str, conv_id: str) -> Dict:
        """获取会话统计信息"""
        if await self._is_redis_available():
            try:
                meta = await self.r.hgetall(self._conv_meta_key(user_id, conv_id))
                msg_count = await self.r.llen(self._chat_key(user_id, conv_id))
                meta["actual_message_count"] = msg_count
                return meta
            except redis.RedisError:
                return {}
        else:
            # 内存模式
            meta = self._memory_meta.get(user_id, {}).get(conv_id, {}).copy()
            messages = self._memory_store.get(user_id, {}).get(conv_id, [])
            meta["actual_message_count"] = len(messages)
            return meta


