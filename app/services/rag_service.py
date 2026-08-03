from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.config import Settings
from app.models.schemas import ChatResponse, Source

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

    def answer(
        self,
        question: str,
        user: dict[str, str] | None = None,
        hybrid_search: bool | None = None,
        query_expansion: bool | None = None,
    ) -> ChatResponse:
        start = time.perf_counter()
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured. Add it to your .env file.")

        chunks = self._retrieve(
            question,
            user=user,
            hybrid_search=hybrid_search,
            query_expansion=query_expansion,
        )
        if not chunks:
            return ChatResponse(
                answer="I could not find sufficiently relevant information in the uploaded documents.",
                sources=[],
            )

        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        context = self._format_context(chunks)
        llm = ChatOpenAI(
            model=self.settings.openai_model,
            api_key=self.settings.openai_api_key,
            temperature=0,
        )
        response = llm.invoke(
            [
                SystemMessage(
                    content=(
                        "You answer questions using only the supplied document context. "
                        "If the context does not answer the question, say that clearly. "
                        "Do not invent facts or citations. Keep the answer concise."
                    )
                ),
                HumanMessage(content=f"Question: {question}\n\nDocument context:\n{context}"),
            ]
        )
        answer = response.content if isinstance(response.content, str) else str(response.content)
        duration_ms = round((time.perf_counter() - start) * 1000, 1)
        logger.info(
            "Answered in %.1fms with %d sources",
            duration_ms,
            len(chunks),
            extra={"duration_ms": duration_ms, "chunks": len(chunks)},
        )
        return ChatResponse(answer=answer, sources=self._sources(chunks))

    def _retrieve(
        self,
        question: str,
        user: dict[str, str] | None = None,
        hybrid_search: bool | None = None,
        query_expansion: bool | None = None,
    ) -> list[RetrievedChunk]:
        use_hybrid = self.settings.enable_hybrid_search if hybrid_search is None else hybrid_search
        use_expansion = self.settings.enable_query_expansion if query_expansion is None else query_expansion
        candidate_k = max(self.settings.top_k, self.settings.retrieval_candidate_k)

        if use_expansion:
            from app.services.hybrid_search import MultiQueryExpander
            queries = MultiQueryExpander.expand(question, self.settings, count=self.settings.query_expansion_count)
        else:
            queries = [question]

        all_candidates: dict[str, RetrievedChunk] = {}

        for q in queries:
            if use_hybrid:
                from app.services.hybrid_search import reciprocal_rank_fusion

                # 1. Dense retrieval
                dense_raw = self._vector_store().similarity_search_with_relevance_scores(q, k=candidate_k)
                dense_chunks = [
                    RetrievedChunk(document=doc, relevance_score=score)
                    for doc, score in dense_raw
                    if score >= self.settings.similarity_threshold and (user is None or user.get("role") == "admin" or getattr(doc, "metadata", {}).get("owner_id") in {user.get("username"), "legacy"})
                ]

                # 2. Sparse BM25 retrieval
                sparse_results = self._bm25_index().search(q, top_k=candidate_k, user=user)

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
                    if score >= self.settings.similarity_threshold and (user is None or user.get("role") == "admin" or getattr(document, "metadata", {}).get("owner_id") in {user.get("username"), "legacy"})
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

        logger.info(
            "Retrieved %d candidates (hybrid=%s, expansion=%s, queries=%d) above threshold %.2f",
            len(relevant),
            use_hybrid,
            use_expansion,
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
