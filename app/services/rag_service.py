from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.core.config import Settings
from app.models.schemas import ChatResponse, Source

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

    def answer(self, question: str) -> ChatResponse:
        if not self.settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured. Add it to your .env file.")

        chunks = self._retrieve(question)
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
        return ChatResponse(answer=answer, sources=self._sources(chunks))

    def _retrieve(self, question: str) -> list[RetrievedChunk]:
        candidate_k = max(self.settings.top_k, self.settings.retrieval_candidate_k)
        results = self._vector_store().similarity_search_with_relevance_scores(
            question, k=candidate_k
        )
        relevant = [
            RetrievedChunk(document=document, relevance_score=score)
            for document, score in results
            if score >= self.settings.similarity_threshold
        ]
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
