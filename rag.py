import os
import asyncio
import json
import zipfile
import shutil
import uuid
from xml.etree import ElementTree as ET

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.retrievers import BM25Retriever
from langchain.retrievers import EnsembleRetriever, ContextualCompressionRetriever
from langchain.retrievers.document_compressors import CrossEncoderReranker
from langchain_community.cross_encoders import HuggingFaceCrossEncoder
from langchain_core.documents import Document

class MultiDomainRetriever:
    def __init__(
        self,
        base_folder_path: str,
        index_base_path: str = "./faiss_index",
        embedding_model: str = "Qwen/Qwen3-Embedding-0.6B",
        rerank_model: str = "BAAI/bge-reranker-base",
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        bm25_k: int = 5,
        faiss_k: int = 5,
        top_n: int = 3,
        device: str = "cpu",
        lazy_init: bool = True,
    ):
        self.base_folder_path = os.path.abspath(base_folder_path)
        self.index_base_path = os.path.abspath(index_base_path)
        
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.bm25_k = bm25_k
        self.faiss_k = faiss_k
        self.top_n = top_n
        self.lazy_init = lazy_init

        os.makedirs(self.base_folder_path, exist_ok=True)
        os.makedirs(self.index_base_path, exist_ok=True)

        self.embeddings = HuggingFaceEmbeddings(
            model_name=embedding_model,
            encode_kwargs={"normalize_embeddings": True},
            model_kwargs={"device": device}
        )
        self.rerank_model = HuggingFaceCrossEncoder(model_name=rerank_model)
        self.compressor = CrossEncoderReranker(model=self.rerank_model, top_n=top_n)

        self.domain_retrievers: dict[str, ContextualCompressionRetriever] = {}
        self._domain_init_tasks: dict[str, asyncio.Task] = {}

        if not self.lazy_init:
            self._init_all_domains()

    def available_domains(self) -> list[str]:
        try:
            domains = [
                d
                for d in os.listdir(self.base_folder_path)
                if os.path.isdir(os.path.join(self.base_folder_path, d))
            ]
            return sorted(domains)
        except Exception:
            return sorted(self.domain_retrievers.keys())

    def _init_all_domains(self):
        domains = [d for d in os.listdir(self.base_folder_path) if os.path.isdir(os.path.join(self.base_folder_path, d))]
        for domain in domains:
            domain_folder = os.path.join(self.base_folder_path, domain)
            domain_index = os.path.join(self.index_base_path, domain)
            self._setup_domain_retriever(domain, domain_folder, domain_index)

    def _setup_domain_retriever(self, domain_name, folder_path, index_path):
        def _current_manifest() -> dict:
            items = []
            try:
                for fn in sorted(os.listdir(folder_path)):
                    fp = os.path.join(folder_path, fn)
                    if not os.path.isfile(fp):
                        continue
                    ext = os.path.splitext(fn)[-1].lower()
                    if ext not in {".pdf", ".txt", ".docx", ".doc"}:
                        continue
                    try:
                        st = os.stat(fp)
                        items.append({
                            "filename": fn,
                            "size": int(st.st_size),
                            "mtime": int(st.st_mtime),
                        })
                    except OSError:
                        continue
            except FileNotFoundError:
                items = []
            return {
                "domain": domain_name,
                "files": items, 
            }

        def _load_manifest(path: str) -> dict | None:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None

        def _save_manifest(path: str, manifest: dict) -> None:
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            os.replace(tmp, path)

        os.makedirs(index_path, exist_ok=True)
        manifest_path = os.path.join(index_path, "manifest.json")
        index_file = os.path.join(index_path, "index.faiss")

        current_manifest = _current_manifest()
        previous_manifest = _load_manifest(manifest_path) if os.path.exists(manifest_path) else None

        should_rebuild = False
        reason = ""
        if not os.path.exists(index_file):
            should_rebuild = True
            reason = "首次构建，本地无索引"
        elif previous_manifest is None or previous_manifest.get("files") != current_manifest.get("files"):
            should_rebuild = True
            reason = "检测到领域内文件有新增/修改/删除"

        docs = []
        if should_rebuild:
            print(f"🚀 [{domain_name}] {reason} -> 正在读取文件并进行【深度向量化】...")
            documents = self._load_documents(folder_path)
            if not documents:
                print(f"  - [{domain_name}] 目录下没有有效文档，跳过。")
                return

            text_splitter = RecursiveCharacterTextSplitter(chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap)
            docs = text_splitter.split_documents(documents)

            vectorstore = FAISS.from_documents(docs, self.embeddings)
            
            
            safe_temp_dir = os.path.join(self.index_base_path, f"temp_{uuid.uuid4().hex[:8]}")
            os.makedirs(safe_temp_dir, exist_ok=True)
            try:
                
                vectorstore.save_local(safe_temp_dir)
                shutil.copyfile(os.path.join(safe_temp_dir, "index.faiss"), os.path.join(index_path, "index.faiss"))
                shutil.copyfile(os.path.join(safe_temp_dir, "index.pkl"), os.path.join(index_path, "index.pkl"))
            finally:
                shutil.rmtree(safe_temp_dir, ignore_errors=True)
                
            _save_manifest(manifest_path, current_manifest)
            print(f"✅ [{domain_name}] 向量化完成并已生成本地索引！")
        else:
            try:
                print(f"⚡ [{domain_name}] 检测到文件未变动 -> 正在【秒级复用】本地已有索引...")
                
                safe_temp_dir = os.path.join(self.index_base_path, f"temp_{uuid.uuid4().hex[:8]}")
                os.makedirs(safe_temp_dir, exist_ok=True)
                try:
                    shutil.copyfile(os.path.join(index_path, "index.faiss"), os.path.join(safe_temp_dir, "index.faiss"))
                    shutil.copyfile(os.path.join(index_path, "index.pkl"), os.path.join(safe_temp_dir, "index.pkl"))
                    vectorstore = FAISS.load_local(safe_temp_dir, self.embeddings, allow_dangerous_deserialization=True)
                    docs = list(vectorstore.docstore._dict.values()) 
                finally:
                    shutil.rmtree(safe_temp_dir, ignore_errors=True)
                    
            except Exception as e:
                print(f"⚠️ [{domain_name}] 本地索引损坏 ({e})，正在兜底重建向量化...")
                documents = self._load_documents(folder_path)
                if not documents: 
                    print(f"  - [{domain_name}] 目录下没有有效文档，跳过。")
                    return
                text_splitter = RecursiveCharacterTextSplitter(chunk_size=self.chunk_size, chunk_overlap=self.chunk_overlap)
                docs = text_splitter.split_documents(documents)
                vectorstore = FAISS.from_documents(docs, self.embeddings)
                
                safe_temp_dir = os.path.join(self.index_base_path, f"temp_{uuid.uuid4().hex[:8]}")
                os.makedirs(safe_temp_dir, exist_ok=True)
                try:
                    vectorstore.save_local(safe_temp_dir)
                    shutil.copyfile(os.path.join(safe_temp_dir, "index.faiss"), os.path.join(index_path, "index.faiss"))
                    shutil.copyfile(os.path.join(safe_temp_dir, "index.pkl"), os.path.join(index_path, "index.pkl"))
                finally:
                    shutil.rmtree(safe_temp_dir, ignore_errors=True)
                    
                _save_manifest(manifest_path, current_manifest)

        if not docs:
            print(f"  - [{domain_name}] 没有可用的文档组块，无法构建检索器。")
            return

        faiss_retriever = vectorstore.as_retriever(search_kwargs={"k": self.faiss_k})

        texts = [doc.page_content for doc in docs]
        bm25_retriever = BM25Retriever.from_texts(texts, metadatas=[doc.metadata for doc in docs])
        bm25_retriever.k = self.bm25_k

        ensemble_retriever = EnsembleRetriever(retrievers=[bm25_retriever, faiss_retriever], weights=[0.5, 0.5])

        self.domain_retrievers[domain_name] = ContextualCompressionRetriever(
            base_compressor=self.compressor,
            base_retriever=ensemble_retriever
        )
        print(f"🎯 [{domain_name}] 领域检索器装载完毕！")

    async def _aensure_domain(self, domain: str) -> bool:
        if domain in self.domain_retrievers:
            return True

        domain_folder = os.path.join(self.base_folder_path, domain)
        domain_index = os.path.join(self.index_base_path, domain)
        if not os.path.isdir(domain_folder):
            return False

        task = self._domain_init_tasks.get(domain)
        if task is None:
            async def _build():
                await asyncio.to_thread(self._setup_domain_retriever, domain, domain_folder, domain_index)
                return True

            task = asyncio.create_task(_build())
            self._domain_init_tasks[domain] = task

        try:
            await task
        finally:
            if domain in self._domain_init_tasks and self._domain_init_tasks[domain].done():
                self._domain_init_tasks.pop(domain, None)

        return domain in self.domain_retrievers

    def _load_documents(self, folder_path):
        def _load_docx_without_deps(path: str) -> list[Document]:
            try:
                with zipfile.ZipFile(path) as zf:
                    xml_bytes = zf.read("word/document.xml")
                root = ET.fromstring(xml_bytes)
                ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                paragraphs = []
                for p in root.findall(".//w:p", ns):
                    texts = [t.text for t in p.findall(".//w:t", ns) if t.text]
                    if texts:
                        paragraphs.append("".join(texts))
                text = "\n".join(paragraphs).strip()
                if not text:
                    return []
                return [Document(page_content=text, metadata={"source": path})]
            except Exception:
                return []

        documents = []
        for file in os.listdir(folder_path):
            file_path = os.path.join(folder_path, file)
            if not os.path.isfile(file_path): continue
            ext = os.path.splitext(file)[-1].lower()
            try:
                if ext == ".pdf": docs = PyPDFLoader(file_path).load()
                elif ext == ".txt": docs = TextLoader(file_path, encoding="utf-8").load()
                elif ext in [".docx", ".doc"]:
                    docs = []
                    if ext == ".doc":
                        print(f"文件 {file} 加载失败: 不支持直接解析 .doc，请转换为 .docx 或 .pdf 后再放入知识库")
                        continue
                    try:
                        from langchain_community.document_loaders import UnstructuredWordDocumentLoader
                        docs = UnstructuredWordDocumentLoader(file_path).load()
                    except Exception as e:
                        docs = _load_docx_without_deps(file_path)
                        if not docs:
                            raise e
                else: continue
                for d in docs: d.metadata["filename"] = file
                documents.extend(docs)
            except Exception as e:
                print(f"文件 {file} 加载失败: {e}")
        return documents

    async def aquery(self, query: str, domain: str):
        ok = await self._aensure_domain(domain)
        if not ok:
            for fallback in self.available_domains():
                if await self._aensure_domain(fallback):
                    domain = fallback
                    ok = True
                    break
        if not ok:
            return []

        print(f"🔍 [RAG 路由] 正在从【{domain}】数据库中检索...")
        compressed_docs = await asyncio.to_thread(self.domain_retrievers[domain].invoke, query)
        return [(doc.page_content, doc.metadata) for doc in compressed_docs]

    def query(self, query: str, domain: str):
        if domain not in self.domain_retrievers and self.lazy_init:
            domain_folder = os.path.join(self.base_folder_path, domain)
            domain_index = os.path.join(self.index_base_path, domain)
            if os.path.isdir(domain_folder):
                self._setup_domain_retriever(domain, domain_folder, domain_index)

        if domain not in self.domain_retrievers:
            print(f"⚠️ 未找到匹配的领域知识库 [{domain}]，将尝试在全局或默认库中搜索（如需）。")
            if not self.domain_retrievers: return []
            domain = list(self.domain_retrievers.keys())[0] 
            
        print(f"🔍 [RAG 路由] 正在从【{domain}】数据库中检索...")
        compressed_docs = self.domain_retrievers[domain].invoke(query)
        return [(doc.page_content, doc.metadata) for doc in compressed_docs]

    async def aquery_all(self, query: str):
        domains = self.available_domains()
        if not domains:
            return []

        await asyncio.gather(*(self._aensure_domain(d) for d in domains), return_exceptions=True)

        merged: list[tuple[str, dict]] = []
        seen = set()
        for domain in domains:
            if domain not in self.domain_retrievers:
                continue
            try:
                docs = await asyncio.to_thread(self.domain_retrievers[domain].invoke, query)
            except Exception:
                continue
            for doc in docs:
                text = doc.page_content
                meta = dict(doc.metadata or {})
                meta.setdefault("domain", domain)
                key = (meta.get("filename", ""), meta.get("source", ""), text[:200])
                if key in seen:
                    continue
                seen.add(key)
                merged.append((text, meta))
        return merged

    async def prewarm(self, domains: list[str] | None = None, concurrency: int = 2) -> None:
        targets = domains or self.available_domains()
        if not targets:
            return

        sem = asyncio.Semaphore(max(1, int(concurrency)))

        async def _one(domain: str):
            async with sem:
                try:
                    await self._aensure_domain(domain)
                except Exception:
                    return

        await asyncio.gather(*(_one(d) for d in targets), return_exceptions=True)

    def query_all(self, query: str):
        if not self.domain_retrievers:
            return []

        merged: list[tuple[str, dict]] = []
        seen = set()
        for domain in self.available_domains():
            try:
                docs = self.domain_retrievers[domain].invoke(query)
            except Exception:
                continue
            for doc in docs:
                text = doc.page_content
                meta = dict(doc.metadata or {})
                meta.setdefault("domain", domain)
                key = (meta.get("filename", ""), meta.get("source", ""), text[:200])
                if key in seen:
                    continue
                seen.add(key)
                merged.append((text, meta))
        return merged