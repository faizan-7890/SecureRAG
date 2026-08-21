from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.config import Settings
from app.models.schemas import ChatMessage, ChatResponse, Source

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from langchain_chroma import Chroma
    from langchain_community.embeddings import HuggingFaceEmbeddings
    from langchain_core.documents import Document


@dataclass(frozen=True)
class RetrievedChunk:
    document: Document
    relevance_score: float


class RAGService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._embeddings: HuggingFaceEmbeddings | None = None

    @property
    def embeddings(self) -> HuggingFaceEmbeddings:
        from langchain_community.embeddings import HuggingFaceEmbeddings

        if self._embeddings is None:
            self._embeddings = HuggingFaceEmbeddings(
                model_name="sentence-transformers/all-MiniLM-L6-v2",
                model_kwargs={"device": "cpu"},
                encode_kwargs={"normalize_embeddings": True},
            )
        return self._embeddings

    def _vector_store(self) -> Chroma:
        from langchain_chroma import Chroma

        return Chroma(
            collection_name=self.settings.chroma_collection,
            persist_directory=str(self.settings.chroma_path),
            embedding_function=self.embeddings,
        )

    def _bm25_index(self):
        from app.services.hybrid_search import BM25Index

        bm25_path = self.settings.bm25_index_path or (self.settings.chroma_path / "bm25_index.json")
        return BM25Index.load(bm25_path)

    def _create_chat_model(self, streaming: bool = False, temperature: float = 0.0):
        """Create a ChatOpenAI instance supporting OpenAI and Google Gemini via OpenAI-compatible endpoint."""
        from langchain_openai import ChatOpenAI

        api_key = self.settings.effective_api_key
        model = self.settings.openai_model
        base_url = self.settings.openai_base_url

        # Auto-detect Google Gemini API key or model
        if api_key and (api_key.startswith("AIzaSy") or "gemini" in model.lower() or bool(self.settings.gemini_api_key)):
            base_url = base_url or "https://generativelanguage.googleapis.com/v1beta/openai/"
            if model == "gpt-4o-mini" or not model.startswith("gemini"):
                model = "gemini-1.5-flash"

        kwargs: dict[str, object] = {
            "model": model,
            "api_key": api_key,
            "temperature": temperature,
        }
        if base_url:
            kwargs["base_url"] = base_url
        if streaming:
            kwargs["streaming"] = True

        return ChatOpenAI(**kwargs)

    def _recontextualize_query(self, question: str, history: list[ChatMessage] | None) -> str:
        """Condense dialogue history and follow-up question into a standalone query."""
        if not history or not self.settings.enable_query_recontextualization or not self.settings.effective_api_key:
            return question

        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        messages = [
            SystemMessage(
                content=(
                    "Given a chat history and the latest user question which might reference context in the chat history, "
                    "formulate a standalone question which can be understood without the chat history. "
                    "Do NOT answer the question, just reformulate it if needed and otherwise return it as is."
                )
            )
        ]
        for msg in history[-self.settings.max_history_messages:]:
            if msg.role == "user":
                messages.append(HumanMessage(content=msg.content))
            elif msg.role == "assistant":
                messages.append(AIMessage(content=msg.content))

        messages.append(HumanMessage(content=f"Follow-up question: {question}\nStandalone question:"))

        try:
            llm = self._create_chat_model(temperature=0.0)
            response = llm.invoke(messages)
            standalone = response.content.strip() if isinstance(response.content, str) else str(response.content).strip()
            if standalone:
                logger.debug("Recontextualized query '%s' -> '%s'", question, standalone)
                return standalone
        except Exception as error:
            logger.warning("Query recontextualization failed, falling back to original: %s", error)

        return question

    def _build_llm_messages(
        self,
        question: str,
        context: str,
        history: list[ChatMessage] | None,
    ) -> list:
        """Construct prompt messages including system instructions, prior dialogue, and grounded context."""
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        messages = [
            SystemMessage(
                content=(
                    "You answer questions using only the supplied document context. "
                    "If the context does not answer the question, say that clearly. "
                    "Do not invent facts or citations. Keep the answer concise."
                )
            )
        ]
        if history:
            for msg in history[-self.settings.max_history_messages:]:
                if msg.role == "user":
                    messages.append(HumanMessage(content=msg.content))
                elif msg.role == "assistant":
                    messages.append(AIMessage(content=msg.content))

        messages.append(HumanMessage(content=f"Question: {question}\n\nDocument context:\n{context}"))
        return messages

    def answer(
        self,
        question: str,
        user: dict[str, str] | None = None,
        history: list[ChatMessage] | None = None,
        session_id: str | None = None,
        hybrid_search: bool | None = None,
        query_expansion: bool | None = None,
        enable_reranker: bool | None = None,
        enable_semantic_cache: bool | None = None,
    ) -> ChatResponse:
        start = time.perf_counter()
        if not self.settings.effective_api_key:
            raise RuntimeError("API key is not configured. Add OPENAI_API_KEY or GEMINI_API_KEY to your .env file.")

        from app.core.session_store import SessionStore

        resolved_history = list(history) if history else []
        if session_id and not resolved_history:
            resolved_history = SessionStore.get_history(session_id, max_messages=self.settings.max_history_messages)

        # 1. Check Semantic Cache (only for standalone questions without prior dialogue dependency)
        use_cache = self.settings.enable_semantic_cache if enable_semantic_cache is None else enable_semantic_cache
        if use_cache and not resolved_history:
            try:
                from app.services.semantic_cache import SemanticCache

                query_emb = self.embeddings.embed_query(question)
                cache_hit = SemanticCache.get_instance(self.settings).lookup(question, query_emb)
                if cache_hit:
                    cache_hit.session_id = session_id
                    if session_id:
                        SessionStore.add_turn(session_id, question, cache_hit.answer, max_messages=self.settings.max_history_messages)
                    duration_ms = round((time.perf_counter() - start) * 1000, 1)
                    logger.info("Answered via semantic cache in %.1fms (session=%s)", duration_ms, session_id)
                    return cache_hit
            except Exception as cache_err:
                logger.warning("Semantic cache lookup failed: %s", cache_err)

        search_query = self._recontextualize_query(question, resolved_history)
        chunks = self._retrieve(
            search_query,
            user=user,
            hybrid_search=hybrid_search,
            query_expansion=query_expansion,
            enable_reranker=enable_reranker,
        )
        if not chunks:
            fallback_answer = "I could not find sufficiently relevant information in the uploaded documents."
            if session_id:
                SessionStore.add_turn(session_id, question, fallback_answer, max_messages=self.settings.max_history_messages)
            return ChatResponse(
                answer=fallback_answer,
                sources=[],
                session_id=session_id,
                cached=False,
            )

        context = self._format_context(chunks)
        messages = self._build_llm_messages(question, context, resolved_history)
        llm = self._create_chat_model(temperature=0.0)
        response = llm.invoke(messages)
        answer = response.content if isinstance(response.content, str) else str(response.content)

        sources = self._sources(chunks)

        if session_id:
            SessionStore.add_turn(session_id, question, answer, max_messages=self.settings.max_history_messages)

        # Store in Semantic Cache
        if use_cache and not resolved_history:
            try:
                from app.services.semantic_cache import SemanticCache

                query_emb = self.embeddings.embed_query(question)
                SemanticCache.get_instance(self.settings).store(question, query_emb, answer, sources)
            except Exception as cache_err:
                logger.warning("Semantic cache store failed: %s", cache_err)

        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        logger.info(
            "Answered in %.1fms with %d sources (session=%s)",
            duration_ms,
            len(chunks),
            session_id,
            extra={"duration_ms": duration_ms, "chunks": len(chunks), "session_id": session_id},
        )
        return ChatResponse(answer=answer, sources=sources, session_id=session_id, cached=False)

    def answer_stream(
        self,
        question: str,
        user: dict[str, str] | None = None,
        history: list[ChatMessage] | None = None,
        session_id: str | None = None,
        hybrid_search: bool | None = None,
        query_expansion: bool | None = None,
        enable_reranker: bool | None = None,
        enable_semantic_cache: bool | None = None,
    ):
        """Generator yielding SSE-formatted event objects for token-by-token streaming."""
        from app.core.session_store import SessionStore
        from app.models.schemas import (
            StreamDoneEvent,
            StreamErrorEvent,
            StreamSourceEvent,
            StreamTokenEvent,
        )

        if not self.settings.effective_api_key:
            yield StreamErrorEvent(error="API key is not configured. Add OPENAI_API_KEY or GEMINI_API_KEY to your .env file.")
            return

        resolved_history = list(history) if history else []
        if session_id and not resolved_history:
            resolved_history = SessionStore.get_history(session_id, max_messages=self.settings.max_history_messages)

        # 1. Check Semantic Cache
        use_cache = self.settings.enable_semantic_cache if enable_semantic_cache is None else enable_semantic_cache
        if use_cache and not resolved_history:
            try:
                from app.services.semantic_cache import SemanticCache

                query_emb = self.embeddings.embed_query(question)
                cache_hit = SemanticCache.get_instance(self.settings).lookup(question, query_emb)
                if cache_hit:
                    yield StreamSourceEvent(sources=cache_hit.sources)
                    yield StreamTokenEvent(token=cache_hit.answer)
                    if session_id:
                        SessionStore.add_turn(session_id, question, cache_hit.answer, max_messages=self.settings.max_history_messages)
                    yield StreamDoneEvent(done=True, total_tokens=1, session_id=session_id, cached=True)
                    return
            except Exception as cache_err:
                logger.warning("Semantic cache lookup failed in stream: %s", cache_err)

        search_query = self._recontextualize_query(question, resolved_history)
        chunks = self._retrieve(
            search_query,
            user=user,
            hybrid_search=hybrid_search,
            query_expansion=query_expansion,
            enable_reranker=enable_reranker,
        )

        # 1. Send retrieved citation sources immediately
        sources = self._sources(chunks)
        yield StreamSourceEvent(sources=sources)

        if not chunks:
            fallback = "I could not find sufficiently relevant information in the uploaded documents."
            yield StreamTokenEvent(token=fallback)
            if session_id:
                SessionStore.add_turn(session_id, question, fallback, max_messages=self.settings.max_history_messages)
            yield StreamDoneEvent(done=True, total_tokens=1, session_id=session_id, cached=False)
            return

        context = self._format_context(chunks)
        messages = self._build_llm_messages(question, context, resolved_history)
        llm = self._create_chat_model(streaming=True, temperature=0.0)

        collected_tokens: list[str] = []
        try:
            for chunk in llm.stream(messages):
                token_text = chunk.content if isinstance(chunk.content, str) else str(chunk.content)
                if token_text:
                    collected_tokens.append(token_text)
                    yield StreamTokenEvent(token=token_text)

            full_answer = "".join(collected_tokens)
            if session_id:
                SessionStore.add_turn(session_id, question, full_answer, max_messages=self.settings.max_history_messages)

            # Store in Semantic Cache
            if use_cache and not resolved_history:
                try:
                    from app.services.semantic_cache import SemanticCache

                    query_emb = self.embeddings.embed_query(question)
                    SemanticCache.get_instance(self.settings).store(question, query_emb, full_answer, sources)
                except Exception as cache_err:
                    logger.warning("Semantic cache store failed in stream: %s", cache_err)

            yield StreamDoneEvent(
                done=True,
                total_tokens=len(collected_tokens),
                session_id=session_id,
                cached=False,
            )
        except Exception as error:
            logger.error("Streaming error: %s", error)
            yield StreamErrorEvent(error=str(error))


    def _retrieve(
        self,
        question: str,
        user: dict[str, str] | None = None,
        hybrid_search: bool | None = None,
        query_expansion: bool | None = None,
        enable_reranker: bool | None = None,
    ) -> list[RetrievedChunk]:
        use_hybrid = self.settings.enable_hybrid_search if hybrid_search is None else hybrid_search
        use_expansion = self.settings.enable_query_expansion if query_expansion is None else query_expansion
        use_reranker = self.settings.enable_reranker if enable_reranker is None else enable_reranker
        candidate_k = max(self.settings.top_k, self.settings.retrieval_candidate_k)

        if use_expansion:
            from app.services.hybrid_search import MultiQueryExpander
            queries = MultiQueryExpander.expand(question, self.settings, count=self.settings.query_expansion_count)
        else:
            queries = [question]

        if self.settings.auth_secret and user is None:
            allowed_owners: set[str] | None = {"legacy"}
        elif user and user.get("role") != "admin":
            allowed_owners = {user.get("username"), "legacy"}
        else:
            allowed_owners = None

        all_candidates: dict[str, RetrievedChunk] = {}

        for q in queries:
            if use_hybrid:
                from app.services.hybrid_search import reciprocal_rank_fusion

                # 1. Dense retrieval
                dense_raw = self._vector_store().similarity_search_with_relevance_scores(q, k=candidate_k)
                dense_chunks = [
                    RetrievedChunk(document=doc, relevance_score=score)
                    for doc, score in dense_raw
                    if score >= self.settings.similarity_threshold
                    and (
                        allowed_owners is None
                        or (getattr(doc, "metadata", {}) or {}).get("owner_id", "legacy") in allowed_owners
                    )
                ]

                # 2. Sparse BM25 retrieval
                sparse_results = self._bm25_index().search(
                    q,
                    top_k=candidate_k,
                    user=user,
                    auth_enabled=bool(self.settings.auth_secret),
                )

                # 3. Fuse dense and sparse results
                fused = reciprocal_rank_fusion(
                    dense_results=dense_chunks,
                    sparse_results=sparse_results,
                    rrf_k=self.settings.rrf_k,
                    dense_weight=self.settings.dense_weight,
                    sparse_weight=self.settings.sparse_weight,
                )
            else:
                results = self._vector_store().similarity_search_with_relevance_scores(q, k=candidate_k)
                fused = [
                    RetrievedChunk(document=document, relevance_score=score)
                    for document, score in results
                    if score >= self.settings.similarity_threshold
                    and (
                        allowed_owners is None
                        or (getattr(document, "metadata", {}) or {}).get("owner_id", "legacy") in allowed_owners
                    )
                ]

            for chunk in fused:
                meta = getattr(chunk.document, "metadata", {})
                content_snippet = getattr(chunk.document, "page_content", "")[:100]
                doc_key = str(
                    meta.get("chunk_id")
                    or f"{meta.get('filename')}:{meta.get('chunk_index')}:{content_snippet}:{meta.get('owner_id')}"
                )
                if doc_key not in all_candidates or chunk.relevance_score > all_candidates[doc_key].relevance_score:
                    all_candidates[doc_key] = chunk

        # Filter by similarity threshold
        relevant = [
            chunk
            for chunk in all_candidates.values()
            if chunk.relevance_score >= self.settings.similarity_threshold
        ]
        relevant.sort(key=lambda c: c.relevance_score, reverse=True)

        # Apply Cross-Encoder Reranker if enabled
        if use_reranker and relevant:
            from app.services.reranker import CrossEncoderReranker

            reranker = CrossEncoderReranker(self.settings)
            relevant = reranker.rerank(question, relevant, top_k=self.settings.reranker_top_k or self.settings.top_k)

        logger.info(
            "Retrieved %d candidates (hybrid=%s, expansion=%s, reranker=%s, queries=%d) above threshold %.2f",
            len(relevant),
            use_hybrid,
            use_expansion,
            use_reranker,
            len(queries),
            self.settings.similarity_threshold,
        )
        return relevant[: self.settings.top_k]

    @staticmethod
    def _format_context(chunks: list[RetrievedChunk]) -> str:
        entries: list[str] = []
        for chunk in chunks:
            document = chunk.document
            filename = document.metadata.get("filename", "Unknown")
            page = document.metadata.get("page")
            page_label = f", page {page}" if page else ""
            entries.append(f"[Source: {filename}{page_label}]\n{document.page_content}")
        return "\n\n".join(entries)

    def _sources(self, chunks: list[RetrievedChunk]) -> list[Source]:
        seen: set[tuple[str, int | None, int | None, str]] = set()
        sources: list[Source] = []
        for chunk in chunks:
            document = chunk.document
            filename = str(document.metadata.get("filename", "Unknown"))
            page = document.metadata.get("page")
            chunk_index = document.metadata.get("chunk_index")
            excerpt = " ".join(document.page_content.split())[: self.settings.citation_excerpt_chars]
            key = (filename, page, chunk_index, excerpt)
            if key not in seen:
                seen.add(key)
                sources.append(
                    Source(
                        filename=filename,
                        excerpt=excerpt,
                        page=page,
                        chunk_index=chunk_index,
                        relevance_score=round(chunk.relevance_score, 3),
                    )
                )
        return sources

    def delete_document(self, document_id: str, user: dict[str, str] | None = None) -> bool:
        """Delete all chunks for a document from Chroma and BM25, and remove from DocumentRegistry.

        Returns True if the document existed and was deleted, False if not found.
        Raises PermissionError when the caller lacks access.
        """
        from app.services.ingestion import DocumentRegistry

        record = DocumentRegistry.get(document_id)
        if record is None:
            return False

        # RBAC: only admins or the owner may delete
        if self.settings.auth_secret:
            if not user:
                raise PermissionError("Authentication is required to delete documents.")
            if user.get("role") != "admin" and record.owner_id not in {user.get("username"), "legacy"}:
                raise PermissionError("You do not have permission to delete this document.")
        else:
            if user is not None:
                if user.get("role") != "admin" and record.owner_id not in {user.get("username"), "legacy"}:
                    raise PermissionError("You do not have permission to delete this document.")

        # 1. Remove from Chroma — find all chunk IDs with this document_id
        vs = self._vector_store()
        try:
            results = vs.get(where={"document_id": document_id})
            chunk_ids: list[str] = results.get("ids", [])
        except Exception as error:
            logger.warning("Could not query Chroma for document %s: %s", document_id, error)
            chunk_ids = []

        if chunk_ids:
            try:
                vs.delete(ids=chunk_ids)
                logger.info("Deleted %d Chroma chunks for document %s", len(chunk_ids), document_id)
            except Exception as error:
                logger.error("Failed to delete Chroma chunks for document %s: %s", document_id, error)

        # 2. Remove from BM25 sparse index
        bm25_path = self.settings.bm25_index_path or (self.settings.chroma_path / "bm25_index.json")
        try:
            from app.services.hybrid_search import BM25Index
            bm25 = BM25Index.load(bm25_path)
            bm25.remove_document(document_id)
            bm25.save(bm25_path)
        except Exception as error:
            logger.warning("BM25 index update failed for document %s: %s", document_id, error)

        # 3. Remove from registry
        DocumentRegistry.remove(document_id)
        logger.info("Document %s deleted from registry", document_id)
        return True

