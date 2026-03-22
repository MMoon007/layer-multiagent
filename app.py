import asyncio
import json
import os
import uuid
from typing import Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from main.config import get_rag_config
from main.legal_workflow import (
    LegalWorkflow,
    set_global_retriever as set_workflow_global_retriever,
)
from main.rag import MultiDomainRetriever


app = FastAPI()

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
templates = Jinja2Templates(directory=os.path.join(base_dir, "main", "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(base_dir, "main", "static")), name="static")

state_lock = asyncio.Lock()
legal_workflow_instances: Dict[str, LegalWorkflow] = {}


@app.on_event("startup")
async def startup_event():
    print("✅ 智能法律咨询工作流(Multi-Agent) 已准备就绪")

    try:
        rag_config = get_rag_config()
        shared_retriever = MultiDomainRetriever(
            base_folder_path=rag_config["folder_path"],
            index_base_path=rag_config["index_path"],
            embedding_model=rag_config["embedding_model"],
            rerank_model=rag_config["rerank_model"],
            chunk_size=rag_config["chunk_size"],
            chunk_overlap=rag_config["chunk_overlap"],
            bm25_k=rag_config["bm25_k"],
            faiss_k=rag_config["faiss_k"],
            top_n=rag_config["top_n"],
            device=rag_config["device"],
            lazy_init=True,
        )
        app.state.retriever = shared_retriever
        set_workflow_global_retriever(shared_retriever)
        print("✅ 全局 retriever 已设置到 legal_workflow 模块")
        print("⏱️ 知识库预热已关闭，当前为按需加载模式")
    except Exception as exc:
        print(f"⚠️ 知识库初始化失败: {exc}")


def get_or_create_legal_workflow(
    user_id: Optional[str] = None,
    task_id: Optional[str] = None,
) -> LegalWorkflow:
    actual_user_id = user_id or "anonymous_user"
    actual_conv_id = task_id or f"conv_{uuid.uuid4().hex[:8]}"
    instance_key = f"{actual_user_id}:{actual_conv_id}"

    if instance_key not in legal_workflow_instances:
        legal_workflow_instances[instance_key] = LegalWorkflow(
            user_id=actual_user_id,
            conv_id=actual_conv_id,
            retriever=getattr(app.state, "retriever", None),
        )
        print(
            "✅ 创建新的法律工作流实例: "
            f"user_id={actual_user_id}, conv_id={actual_conv_id}"
        )

    return legal_workflow_instances[instance_key]


class MessageRequest(BaseModel):
    message: str
    mode: Optional[str] = "workflow"
    user_id: Optional[str] = None
    task_id: Optional[str] = None
    rag_enabled: Optional[bool] = None


@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/admin")
async def admin(request: Request):
    return templates.TemplateResponse("admin.html", {"request": request})


@app.post("/send_message")
async def send_message(req: MessageRequest):
    user_input = req.message
    user_id = req.user_id
    task_id = req.task_id

    async with state_lock:
        workflow_instance = get_or_create_legal_workflow(user_id, task_id)
        workflow_instance.set_user_input(user_input)

        ai_response = ""
        awaiting_input = False
        ended = False

        try:
            async for event in workflow_instance.compiled_graph.astream(workflow_instance.state):
                current_node = None
                for key in event.keys():
                    if key not in ("__end__", "__interrupt__"):
                        current_node = key
                        break

                if current_node in ["paralegal", "lawyer"]:
                    new_state = event[current_node]
                    if new_state.get("current_output"):
                        ai_response = new_state["current_output"]

                for key, value in event.items():
                    if key not in ("__end__", "__interrupt__"):
                        workflow_instance.state = value

                if "__end__" in event:
                    workflow_instance.state = event["__end__"]
                if "__interrupt__" in event:
                    awaiting_input = True
                    break
                if workflow_instance.state.get("end", False):
                    ended = True
                    break

            if isinstance(ai_response, list):
                ai_response = "\n".join(map(str, ai_response))
            ended = workflow_instance.state.get("end", False)
        except Exception as exc:
            return JSONResponse(content={"error": str(exc)}, status_code=500)

        return {"response": ai_response, "awaiting_input": awaiting_input, "ended": ended}


@app.post("/send_message_stream")
async def send_message_stream(req: MessageRequest):
    user_input = req.message
    user_id = req.user_id
    task_id = req.task_id

    async def event_generator():
        try:
            workflow_instance = get_or_create_legal_workflow(user_id, task_id)
            workflow_instance.set_user_input(user_input)

            ai_response = ""
            final_output = ""
            awaiting_input = False
            ended = False
            current_node = None
            status_sent = False
            streamed_model_content = False
            valid_nodes = ["paralegal", "lawyer"]

            async for event in workflow_instance.compiled_graph.astream_events(
                workflow_instance.state,
                version="v2",
            ):
                kind = event.get("event")
                name = event.get("name", "")
                metadata = event.get("metadata", {})
                langgraph_node = metadata.get("langgraph_node", "")

                if kind == "on_chain_start":
                    node_name = langgraph_node or name
                    if node_name in valid_nodes:
                        if current_node is None:
                            ai_response = ""
                            yield f"data: {json.dumps({'type': 'clear', 'node': node_name})}\n\n"
                        current_node = node_name

                        if node_name == "lawyer" and not status_sent:
                            try:
                                domain = workflow_instance.state.get("case_domain")
                                shared = getattr(app.state, "retriever", None)
                                if domain and shared is not None:
                                    retrievers = getattr(shared, "domain_retrievers", {})
                                    if domain in shared.available_domains() and domain not in retrievers:
                                        msg = f"正在查询【{domain}】相关资料，请稍候...\n\n"
                                        ai_response += msg
                                        status_sent = True
                                        yield f"data: {json.dumps({'type': 'token', 'content': msg})}\n\n"
                            except Exception:
                                pass

                elif kind == "on_chain_end":
                    node_name = langgraph_node or name
                    if node_name in valid_nodes:
                        if current_node == node_name:
                            yield f"data: {json.dumps({'type': 'node', 'node': node_name})}\n\n"
                        current_node = None

                if kind == "on_chat_model_stream" and langgraph_node in valid_nodes:
                    content = event["data"]["chunk"].content
                    if content:
                        streamed_model_content = True
                        ai_response += content
                        yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"

                if kind == "on_chain_end" and name == "LangGraph":
                    output = event.get("data", {}).get("output", {})
                    if output:
                        workflow_instance.state.update(output)
                        if output.get("current_output"):
                            final_output = output["current_output"]
                            if not streamed_model_content:
                                ai_response = final_output
                        if output.get("end"):
                            ended = True
                        if output.get("__interrupt__") is not None:
                            awaiting_input = True

            if final_output and not ai_response:
                ai_response = final_output

            if not ai_response and not ended:
                awaiting_input = True

            payload = {
                "type": "done",
                "response": ai_response,
                "awaiting_input": awaiting_input,
                "ended": ended,
            }
            yield f"data: {json.dumps(payload)}\n\n"

        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/reset")
async def reset(request: Request):
    try:
        data = await request.json()
        user_id = data.get("user_id")
        task_id = data.get("task_id")
    except Exception:
        user_id = None
        task_id = None

    async with state_lock:
        if user_id and task_id:
            instance_key = f"{user_id}:{task_id}"
            if instance_key in legal_workflow_instances:
                del legal_workflow_instances[instance_key]
        else:
            legal_workflow_instances.clear()

    print("[系统]: 会话已重置 -> workflow")
    return {"status": "ok", "mode": "workflow"}
