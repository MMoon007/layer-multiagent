import json

import redis
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import START, StateGraph
from langgraph.prebuilt import create_react_agent
from langgraph.types import interrupt

from main.config import get_openai_config, get_redis_config
from main.prompt import (
    case_continuation_prompt,
    lawyer_analysis_prompt,
    paralegal_prompt,
    router_prompt,
    summary_prompt,
)
from main.rag import MultiDomainRetriever


_global_retriever: MultiDomainRetriever | None = None


def set_global_retriever(retriever: MultiDomainRetriever | None) -> None:
    global _global_retriever
    _global_retriever = retriever


def get_global_retriever() -> MultiDomainRetriever | None:
    return _global_retriever


class LegalWorkflow:
    def __init__(
        self,
        user_id: str,
        conv_id: str,
        redis_host=None,
        redis_port=None,
        retriever: MultiDomainRetriever | None = None,
    ):
        self.user_id = user_id
        self.conv_id = conv_id

        redis_config = get_redis_config()
        actual_redis_host = redis_host if redis_host is not None else redis_config["host"]
        actual_redis_port = redis_port if redis_port is not None else redis_config["port"]
        try:
            self.r = redis.Redis(host=actual_redis_host, port=actual_redis_port, decode_responses=True)
            self.r.ping()
        except redis.ConnectionError:
            print("⚠️ Redis 连接失败，将使用内存存储")
            self.r = None

        self.paralegal_rounds = 3
        self.lawyer_rounds = 3

        openai_config = get_openai_config()
        self.model = ChatOpenAI(
            openai_api_base=openai_config["api_base"],
            openai_api_key=openai_config["api_key"],
            model=openai_config["model"],
            temperature=openai_config["temperature"],
        )

        if retriever is not None:
            self.retriever = retriever
        elif get_global_retriever() is not None:
            self.retriever = get_global_retriever()
        else:
            raise RuntimeError("LegalWorkflow 初始化失败：未提供 retriever，且全局 retriever 未设置。")

        self.paralegal_agent = create_react_agent(model=self.model, tools=[], prompt=paralegal_prompt)
        self.router_agent = create_react_agent(model=self.model, tools=[], prompt=router_prompt)
        self.summary_agent = create_react_agent(model=self.model, tools=[], prompt=summary_prompt)
        self.lawyer_agent = create_react_agent(model=self.model, tools=[], prompt=lawyer_analysis_prompt)

        self.state = self._build_initial_state(user_id, conv_id)

        self.graph = StateGraph(dict, debug=True)
        self.graph.add_node("greet", self.greet)
        self.graph.add_node("client_input", self.client_input)
        self.graph.add_node("paralegal", self.paralegal)
        self.graph.add_node("router", self.router)
        self.graph.add_node("summary", self.summary)
        self.graph.add_node("lawyer", self.lawyer)

        self.graph.add_edge(START, "greet")
        self.graph.add_edge("greet", "client_input")
        self.graph.add_conditional_edges(
            "client_input",
            self.should_route_after_client_input,
            {"paralegal": "paralegal", "lawyer": "lawyer"},
        )
        self.graph.add_conditional_edges(
            "paralegal",
            self.should_continue_paralegal,
            {"client_input": "client_input", "router": "router"},
        )
        self.graph.add_edge("router", "summary")
        self.graph.add_edge("summary", "lawyer")
        self.graph.add_edge("lawyer", "client_input")

        self.compiled_graph = self.graph.compile()

    def _build_initial_state(self, user_id: str, conv_id: str) -> dict:
        return {
            "user_id": user_id,
            "conv_id": conv_id,
            "paralegal_state": {"conversation": [], "count": 0},
            "lawyer_state": {"conversation": [], "count": 0},
            "node_state": {
                "paralegal": False,
                "lawyer": False,
                "router": False,
                "summary": False,
                "greet": False,
                "client_input": False,
            },
            "current_output": "",
            "case_summary": "",
            "case_domain": "民法商法",
            "end": False,
            "latest_user_input": "",
            "next_step": "paralegal",
        }

    def _reset_case_flow(self, state: dict) -> None:
        state["paralegal_state"] = {"conversation": [], "count": 0}
        state["lawyer_state"] = {"conversation": [], "count": 0}
        state["node_state"]["paralegal"] = False
        state["node_state"]["lawyer"] = False
        state["node_state"]["router"] = False
        state["node_state"]["summary"] = False
        state["current_output"] = ""
        state["case_summary"] = ""
        state["case_domain"] = "民法商法"
        state["end"] = False
        state["next_step"] = "paralegal"

    async def _decide_case_continuation(self, state: dict, latest_user_input: str) -> str:
        if not state["node_state"]["lawyer"] or not state["case_summary"]:
            return "new_case"

        prompt = (
            f"当前案件领域：{state['case_domain']}\n\n"
            f"当前案件摘要：\n{state['case_summary']}\n\n"
            f"用户最新输入：\n{latest_user_input}\n"
        )
        messages = [
            SystemMessage(content=case_continuation_prompt),
            HumanMessage(content=prompt),
        ]

        try:
            response = await self.model.ainvoke(messages)
            content = response.content.strip()
            if content.startswith("```"):
                content = content.strip("`")
                content = content.replace("json", "", 1).strip()
            result = json.loads(content)
            decision = result.get("decision", "new_case")
            if decision in {"same_case_followup", "new_case"}:
                return decision
        except Exception as exc:
            print(f"⚠️ 案情延续判断失败，默认按新案处理: {exc}")

        return "new_case"

    def set_user_input(self, text: str):
        self.state["latest_user_input"] = text

    def greet(self, state: dict):
        if state["node_state"]["greet"]:
            return state
        state["system_message"] = "您好，欢迎来到智能法律咨询助手。我有什么能帮助到您的吗？"
        state["node_state"]["greet"] = True
        return state

    async def client_input(self, state: dict) -> dict:
        if not state.get("latest_user_input"):
            interrupt("请当事人描述案件情况：")
            return state

        user_input = state.pop("latest_user_input")
        print(f"👤 [Client] 用户输入: {user_input}")
        human_msg = HumanMessage(content=user_input)

        if state["node_state"]["lawyer"]:
            decision = await self._decide_case_continuation(state, user_input)
            if decision == "same_case_followup":
                state["lawyer_state"]["conversation"].append(human_msg)
                state["current_output"] = ""
                state["next_step"] = "lawyer"
                print("🔁 [Case Decision] 识别为同案追问，直接进入律师分析")
                return state

            self._reset_case_flow(state)
            print("🆕 [Case Decision] 识别为新案件，重新进入接案流程")

        state["paralegal_state"]["conversation"].append(human_msg)
        state["paralegal_state"]["count"] += 1
        state["current_output"] = ""
        state["next_step"] = "paralegal"
        return state

    async def paralegal(self, state: dict) -> dict:
        if state["node_state"]["paralegal"]:
            return state

        history = state["paralegal_state"]["conversation"]
        response = await self.paralegal_agent.ainvoke({"messages": history})
        ai_msg = AIMessage(content=response["messages"][-1].content)
        history.append(ai_msg)
        state["current_output"] = ai_msg.content
        return state

    async def router(self, state: dict) -> dict:
        if state["node_state"]["router"]:
            return state

        history = state["paralegal_state"]["conversation"]
        response = await self.router_agent.ainvoke({"messages": history})
        ai_msg = AIMessage(content=response["messages"][-1].content)

        try:
            content = ai_msg.content.strip()
            if content.startswith("```"):
                content = content.strip("`")
                content = content.replace("json", "", 1).strip()
            domain_json = json.loads(content)
            state["case_domain"] = domain_json.get("推荐领域", "民法商法")
        except Exception:
            state["case_domain"] = "民法商法"

        print(f"🧭 [Router] 案件分配至【{state['case_domain']}】知识库")
        state["node_state"]["router"] = True
        state["current_output"] = ""
        return state

    async def summary(self, state: dict) -> dict:
        if state["node_state"]["summary"]:
            return state

        history = state["paralegal_state"]["conversation"]
        response = await self.summary_agent.ainvoke({"messages": history})
        ai_msg = AIMessage(content=response["messages"][-1].content)
        state["case_summary"] = ai_msg.content
        state["node_state"]["summary"] = True
        state["current_output"] = ""
        return state

    async def lawyer(self, state: dict) -> dict:
        domain = state["case_domain"]
        user_input = (
            state["lawyer_state"]["conversation"][-1].content
            if state["lawyer_state"]["conversation"]
            else state["case_summary"]
        )

        print(f"⚖️ [Expert Lawyer] 正在针对【{domain}】领域进行检索与分析...")

        rag_results = await self.retriever.aquery(user_input, domain=domain)
        formatted_rag = ""
        if rag_results:
            rag_list = [
                f"文件: {meta.get('filename', '')}\n条款内容: {text}"
                for text, meta in rag_results
            ]
            formatted_rag = f"\n\n【检索到的相关法律规定】：\n{chr(10).join(rag_list)}"

        sys_content = f"案情摘要：\n{state['case_summary']}\n\n{formatted_rag}"
        system_msg = SystemMessage(content=sys_content)
        messages = [system_msg] + state["lawyer_state"]["conversation"]

        response = await self.lawyer_agent.ainvoke({"messages": messages})
        ai_msg = AIMessage(content=response["messages"][-1].content)

        state["lawyer_state"]["conversation"].append(ai_msg)
        state["current_output"] = ai_msg.content
        state["node_state"]["lawyer"] = True
        state["next_step"] = "paralegal"
        return state

    def should_route_after_client_input(self, state: dict) -> str:
        return state.get("next_step", "paralegal")

    def should_continue_paralegal(self, state: dict) -> str:
        if state["paralegal_state"]["count"] >= self.paralegal_rounds:
            state["node_state"]["paralegal"] = True
            return "router"
        return "client_input"
